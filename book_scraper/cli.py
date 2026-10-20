"""Command-line interface for scraping and exploring saved price history."""
import argparse
import logging
from pathlib import Path

from .reports import changes, chart_history
from .scraper import crawl
from .storage import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-scraper", description="Track Books to Scrape prices")
    parser.add_argument("--db", default="book_data.db", help="SQLite database path")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--log-file")
    sub = parser.add_subparsers(dest="command")
    scrape = sub.add_parser("scrape"); scrape.add_argument("--max-pages", type=int); scrape.add_argument("--category")
    scrape.add_argument("--delay", type=float, default=1.0); scrape.add_argument("--no-details", action="store_true")
    scrape.add_argument("--dry-run", action="store_true")
    export = sub.add_parser("export"); export.add_argument("--format", choices=["csv", "json", "xlsx"], default="csv")
    export.add_argument("--output"); export.add_argument("--category"); export.add_argument("--max-price", type=float)
    export.add_argument("--rating", type=int); export.add_argument("--in-stock", action="store_true")
    sub.add_parser("changes"); sub.add_parser("stats")
    chart = sub.add_parser("chart"); chart.add_argument("--upc", required=True); chart.add_argument("--output", default="price_history.png")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", filename=args.log_file)
    try:
        if args.command in (None, "scrape"):
            books, _ = crawl(max_pages=getattr(args, "max_pages", None), details=not getattr(args, "no_details", False),
                             dry_run=getattr(args, "dry_run", False), output=args.db,
                             delay=getattr(args, "delay", 1.0), category=getattr(args, "category", None))
            if getattr(args, "dry_run", False):
                import csv
                path = Path("book_data.csv")
                with path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["upc", "title", "price", "currency", "in_stock"]); writer.writeheader()
                    writer.writerows({"upc": b.upc, "title": b.title, "price": str(b.price), "currency": b.currency, "in_stock": b.in_stock} for b in books)
                logging.info("Dry run results written to %s", path)
            else:
                store = Store(args.db)
                try: store.export("csv", "book_data.csv")
                finally: store.close()
                logging.info("Scrape complete; CSV exported to book_data.csv")
        elif args.command == "export":
            store = Store(args.db)
            try:
                path = store.export(args.format, args.output or f"book_data.{args.format}", args.category, args.max_price, args.rating, args.in_stock)
                logging.info("Exported %s", path)
            finally: store.close()
        elif args.command == "changes":
            store = Store(args.db)
            try:
                for key, value in changes(store).items(): logging.info("%s: %s", key.replace("_", " "), value)
            finally: store.close()
        elif args.command == "stats":
            store = Store(args.db)
            try:
                rows = store.all_latest(); logging.info("Books tracked: %d", len(rows))
                if rows:
                    prices = [float(r["price"]) for r in rows]; logging.info("Current price range: %.2f to %.2f", min(prices), max(prices))
            finally: store.close()
        elif args.command == "chart":
            store = Store(args.db)
            try: logging.info("Saved chart to %s", chart_history(store, args.upc, args.output))
            finally: store.close()
        return 0
    except Exception as exc:
        logging.error("Run failed: %s", exc); return 1
