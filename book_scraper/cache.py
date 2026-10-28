"""SQLite-backed HTTP page cache supporting conditional ETag/Last-Modified requests."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class HttpCache:
    def __init__(self, path: str | Path = ".cache/http_cache.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS http_cache (
                    url TEXT PRIMARY KEY,
                    etag TEXT,
                    last_modified TEXT,
                    content TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                )
                """
            )

    def get(self, url: str) -> tuple[str | None, str | None, str | None]:
        """Return (content, etag, last_modified) if cached, else (None, None, None)."""
        row = self.db.execute("SELECT content, etag, last_modified FROM http_cache WHERE url = ?", (url,)).fetchone()
        if row:
            return row["content"], row["etag"], row["last_modified"]
        return None, None, None

    def set(
        self,
        url: str,
        content: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        """Store or update cached page content and conditional headers."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db:
            self.db.execute(
                """
                INSERT INTO http_cache(url, etag, last_modified, content, cached_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    etag = excluded.etag,
                    last_modified = excluded.last_modified,
                    content = excluded.content,
                    cached_at = excluded.cached_at
                """,
                (url, etag, last_modified, content, now),
            )

    def clear(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM http_cache")

    def close(self) -> None:
        self.db.close()
