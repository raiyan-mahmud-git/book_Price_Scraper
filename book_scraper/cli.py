"""Command-line interface for scraping and exploring saved price history."""

import argparse
import logging
from pathlib import Path

from .config import load_config
from .reports import changes, chart_history
from .scraper import crawl
from .storage import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-scraper", description="Track Books to Scrape prices")
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--config", default="book-scraper.toml", help="Path to TOML config file")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--log-file")
    sub = parser.add_subparsers(dest="command")

    scrape = sub.add_parser("scrape")
    scrape.add_argument("--max-pages", type=int)
    scrape.add_argument("--category")
    scrape.add_argument("--delay", type=float)
    scrape.add_argument("--no-details", action="store_true")
    scrape.add_argument("--dry-run", action="store_true")
    scrape.add_argument("--no-cache", action="store_true", help="Bypass HTTP response cache")
    scrape.add_argument("--retries", type=int, help="HTTP request retry attempts")
    scrape.add_argument("--max-backoff", type=float, help="Max retry backoff in seconds")

    export = sub.add_parser("export")
    export.add_argument("--format", choices=["csv", "json", "xlsx"], default=None)
    export.add_argument("--output")
    export.add_argument("--category")
    export.add_argument("--max-price", type=float)
    export.add_argument("--rating", type=int)
    export.add_argument("--in-stock", action="store_true")

    sub.add_parser("changes")
    sub.add_parser("stats")

    chart = sub.add_parser("chart")
    chart.add_argument("--upc", required=True)
    chart.add_argument("--output", default="price_history.png")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        filename=args.log_file,
    )

    config = load_config(args.config)
    db_path = args.db or config.get("database", {}).get("path") or "book_data.db"

    try:
        if args.command in (None, "scrape"):
            raw_delay = getattr(args, "delay", None)
            delay = float(raw_delay if raw_delay is not None else config.get("scraper", {}).get("delay", 1.0))

            raw_retries = getattr(args, "retries", None)
            retries = int(raw_retries if raw_retries is not None else config.get("scraper", {}).get("retries", 3))

            raw_max_backoff = getattr(args, "max_backoff", None)
            max_backoff = float(
                raw_max_backoff if raw_max_backoff is not None else config.get("scraper", {}).get("max_backoff", 60.0)
            )
            no_cache = getattr(args, "no_cache", False) or config.get("scraper", {}).get("no_cache", False)
            max_pages = (
                getattr(args, "max_pages", None)
                if getattr(args, "max_pages", None) is not None
                else config.get("scraper", {}).get("max_pages")
            )
            category = getattr(args, "category", None) or config.get("scraper", {}).get("category")
            no_details = getattr(args, "no_details", False) or config.get("scraper", {}).get("no_details", False)

            books, _ = crawl(
                max_pages=max_pages,
                details=not no_details,
                dry_run=getattr(args, "dry_run", False),
                output=db_path,
                delay=delay,
                category=category,
                no_cache=no_cache,
                retries=retries,
                max_backoff=max_backoff,
            )
            if getattr(args, "dry_run", False):
                import csv

                path = Path("book_data.csv")
                with path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["upc", "title", "price", "currency", "in_stock"])
                    writer.writeheader()
                    writer.writerows(
                        {
                            "upc": b.upc,
                            "title": b.title,
                            "price": str(b.price),
                            "currency": b.currency,
                            "in_stock": b.in_stock,
                        }
                        for b in books
                    )
                logging.info("Dry run results written to %s", path)
            else:
                store = Store(db_path)
                try:
                    store.export("csv", "book_data.csv")
                finally:
                    store.close()
                logging.info("Scrape complete; CSV exported to book_data.csv")
        elif args.command == "export":
            fmt = args.format or config.get("export", {}).get("default_format", "csv")
            category = args.category or config.get("export", {}).get("category")
            max_price = args.max_price if args.max_price is not None else config.get("export", {}).get("max_price")
            in_stock = args.in_stock or config.get("export", {}).get("in_stock", False)

            store = Store(db_path)
            try:
                path = store.export(
                    fmt,
                    args.output or f"book_data.{fmt}",
                    category,
                    max_price,
                    args.rating,
                    in_stock,
                )
                logging.info("Exported %s", path)
            finally:
                store.close()
        elif args.command == "changes":
            store = Store(db_path)
            try:
                for key, value in changes(store).items():
                    logging.info("%s: %s", key.replace("_", " "), value)
            finally:
                store.close()
        elif args.command == "stats":
            store = Store(db_path)
            try:
                rows = store.all_latest()
                logging.info("Books tracked: %d", len(rows))
                if rows:
                    prices = [float(r["price"]) for r in rows]
                    logging.info("Current price range: %.2f to %.2f", min(prices), max(prices))
            finally:
                store.close()
        elif args.command == "chart":
            store = Store(db_path)
            try:
                logging.info("Saved chart to %s", chart_history(store, args.upc, args.output))
            finally:
                store.close()
        return 0
    except Exception as exc:
        logging.error("Run failed: %s", exc)
        return 1
