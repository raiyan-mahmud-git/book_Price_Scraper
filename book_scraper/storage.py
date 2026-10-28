"""SQLite persistence, migration runner, and simple schema versioning."""

import json
import logging
import sqlite3
from decimal import Decimal
from pathlib import Path

from .models import Book

LOG = logging.getLogger(__name__)

LATEST_SCHEMA_VERSION = 2


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version of the SQLite database."""
    has_version_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not has_version_table:
        # Check if books table exists (legacy unversioned database)
        has_books = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='books'").fetchone()
        return 1 if has_books else 0
    row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return int(row[0]) if row else 0


def migrate_database(conn: sqlite3.Connection) -> int:
    """Run all necessary migrations up to LATEST_SCHEMA_VERSION."""
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
    current = get_schema_version(conn)
    if current < 1:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS books(
                    id INTEGER PRIMARY KEY,
                    upc TEXT UNIQUE NOT NULL,
                    title TEXT,
                    currency TEXT,
                    product_url TEXT,
                    image_url TEXT,
                    category TEXT,
                    description TEXT,
                    rating INTEGER,
                    stock_quantity INTEGER,
                    number_of_reviews INTEGER,
                    tax TEXT
                );
                CREATE TABLE IF NOT EXISTS price_history(
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL REFERENCES books(id),
                    price TEXT NOT NULL,
                    in_stock INTEGER NOT NULL,
                    scraped_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS history_book_time ON price_history(book_id, scraped_at);
                DELETE FROM schema_version;
                INSERT INTO schema_version(version) VALUES(1);
                """
            )
        current = 1
        LOG.info("Database migrated to schema version 1")

    if current < 2:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS watchlist(
                    id INTEGER PRIMARY KEY,
                    upc TEXT UNIQUE NOT NULL,
                    below_price TEXT,
                    drop_percent REAL,
                    last_alerted_price TEXT,
                    created_at TEXT NOT NULL
                );
                DELETE FROM schema_version;
                INSERT INTO schema_version(version) VALUES(2);
                """
            )
        current = 2
        LOG.info("Database migrated to schema version 2")

    return current


class Store:
    def __init__(self, path: str | Path = "book_data.db"):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        migrate_database(self.db)

    def save_page(self, books: list[Book], scraped_at: str) -> None:
        # One commit per listing page lets an interrupted crawl keep completed work.
        with self.db:
            for book in books:
                book.validate()
                self.db.execute(
                    """INSERT INTO books(upc,title,currency,product_url,image_url,category,description,rating,
                    stock_quantity,number_of_reviews,tax) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(upc) DO UPDATE SET
                    title=excluded.title, product_url=excluded.product_url, image_url=excluded.image_url,
                    category=excluded.category, description=excluded.description, rating=excluded.rating,
                    stock_quantity=excluded.stock_quantity, number_of_reviews=excluded.number_of_reviews,tax=excluded.tax""",
                    (
                        book.upc,
                        book.title,
                        book.currency,
                        book.product_url,
                        book.image_url,
                        book.category,
                        book.description,
                        book.rating,
                        book.stock_quantity,
                        book.number_of_reviews,
                        str(book.tax),
                    ),
                )
                book_id = self.db.execute("SELECT id FROM books WHERE upc=?", (book.upc,)).fetchone()[0]
                self.db.execute(
                    "INSERT INTO price_history(book_id,price,in_stock,scraped_at) VALUES(?,?,?,?)",
                    (book_id, str(book.price), int(book.in_stock), scraped_at),
                )

    def snapshots(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT scraped_at FROM price_history ORDER BY scraped_at")]

    def snapshot(self, timestamp: str) -> dict[str, dict]:
        rows = self.db.execute(
            """SELECT b.*, h.price,h.in_stock FROM price_history h JOIN books b ON b.id=h.book_id
            WHERE h.scraped_at=?""",
            (timestamp,),
        )
        return {r["upc"]: dict(r) for r in rows}

    def all_latest(self) -> list[dict]:
        return [
            dict(r)
            for r in self.db.execute("""SELECT b.*,h.price,h.in_stock,h.scraped_at FROM books b JOIN
          price_history h ON h.book_id=b.id WHERE h.id=(SELECT MAX(id) FROM price_history WHERE book_id=b.id) ORDER BY b.title""")
        ]

    def export(
        self,
        fmt: str,
        output: str | Path,
        category: str | None = None,
        max_price: float | None = None,
        rating: int | None = None,
        in_stock: bool = False,
    ) -> Path:
        import csv

        rows = self.all_latest()
        rows = [
            r
            for r in rows
            if (not category or (r["category"] and r["category"].lower() == category.lower()))
            and (max_price is None or Decimal(r["price"]) <= Decimal(str(max_price)))
            and (rating is None or r["rating"] == rating)
            and (not in_stock or r["in_stock"])
        ]
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        elif fmt == "csv":
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["upc", "title", "price"])
                writer.writeheader()
                writer.writerows(rows)
        elif fmt == "xlsx":
            import pandas as pd

            pd.DataFrame(rows).to_excel(path, index=False)
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
        return path

    # Watchlist methods
    def add_watch(
        self,
        upc: str,
        below_price: Decimal | None = None,
        drop_percent: float | None = None,
    ) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        below_str = str(below_price) if below_price is not None else None
        with self.db:
            self.db.execute(
                """
                INSERT INTO watchlist(upc, below_price, drop_percent, last_alerted_price, created_at)
                VALUES(?, ?, ?, NULL, ?)
                ON CONFLICT(upc) DO UPDATE SET
                    below_price = excluded.below_price,
                    drop_percent = excluded.drop_percent,
                    created_at = excluded.created_at
                """,
                (upc, below_str, drop_percent, now),
            )

    def remove_watch(self, upc: str) -> bool:
        with self.db:
            cursor = self.db.execute("DELETE FROM watchlist WHERE upc = ?", (upc,))
            return cursor.rowcount > 0

    def get_watchlist(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM watchlist ORDER BY upc")]

    def update_watch_alerted(self, upc: str, price: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE watchlist SET last_alerted_price = ? WHERE upc = ?",
                (price, upc),
            )

    def close(self) -> None:
        self.db.close()
