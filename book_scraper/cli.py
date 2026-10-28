"""Command-line interface for scraping and exploring saved price history."""

import argparse
import logging
from decimal import Decimal
from pathlib import Path

from .alerts import evaluate_watchlist
from .config import load_config
from .reports import changes, chart_aggregate, chart_history, format_stats, get_stats
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

    chart = sub.add_parser("chart", help="Generate price history or aggregate charts")
    chart.add_argument("--upc", help="Book UPC identifier for single-book price history chart")
    chart.add_argument(
        "--kind",
        choices=["category-avg", "rating-vs-price", "price-changes", "stock"],
        help="Aggregate chart kind",
    )
    chart.add_argument("--output", default="price_history.png", help="Output image file path")

    import_csv_parser = sub.add_parser("import-csv", help="Import legacy book_data.csv into database")
    import_csv_parser.add_argument("path", help="Path to CSV file to import")

    watch = sub.add_parser("watch", help="Manage price alerts and watchlist")
    watch_sub = watch.add_subparsers(dest="watch_action")
    watch_add = watch_sub.add_parser("add", help="Add or update a watched book")
    watch_add.add_argument("--upc", required=True, help="Book UPC identifier")
    watch_add.add_argument("--below", type=float, help="Alert when price is below or equal to this threshold")
    watch_add.add_argument("--drop-percent", type=float, help="Alert when price drops by this percentage")
    watch_sub.add_parser("list", help="List all watched books")
    watch_remove = watch_sub.add_parser("remove", help="Remove a book from watchlist")
    watch_remove.add_argument("--upc", required=True, help="Book UPC identifier")

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
                # In dry-run mode, also check watchlist if database exists
                if Path(db_path).exists():
                    store = Store(db_path)
                    try:
                        evaluate_watchlist(store, dry_run=True, config=config)
                    finally:
                        store.close()
            else:
                store = Store(db_path)
                try:
                    store.export("csv", "book_data.csv")
                    evaluate_watchlist(store, dry_run=False, config=config)
                finally:
                    store.close()
                logging.info("Scrape complete; CSV exported to book_data.csv")
        elif args.command == "watch":
            store = Store(db_path)
            try:
                if args.watch_action == "add":
                    below = Decimal(str(args.below)) if args.below is not None else None
                    store.add_watch(args.upc, below_price=below, drop_percent=args.drop_percent)
                    print(f"Added watch for UPC {args.upc} (below={below}, drop_percent={args.drop_percent})")
                elif args.watch_action == "remove":
                    removed = store.remove_watch(args.upc)
                    if removed:
                        print(f"Removed watch for UPC {args.upc}")
                    else:
                        print(f"UPC {args.upc} not found in watchlist")
                elif args.watch_action == "list":
                    items = store.get_watchlist()
                    if not items:
                        print("Watchlist is empty.")
                    else:
                        print(f"{'UPC':<20} {'Target Price':<14} {'Drop %':<10} {'Last Alerted':<14} {'Created At'}")
                        print("-" * 75)
                        for it in items:
                            below_val = f"{Decimal(it['below_price']):.2f}" if it["below_price"] is not None else "-"
                            drop_val = f"{it['drop_percent']}%" if it["drop_percent"] is not None else "-"
                            alerted_val = it["last_alerted_price"] or "-"
                            print(
                                f"{it['upc']:<20} {below_val:<14} {drop_val:<10} {alerted_val:<14} {it['created_at']}"
                            )
            finally:
                store.close()
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
                stats_data = get_stats(store)
                print(format_stats(stats_data))
                logging.info("Books tracked: %d", stats_data["total_books"])
                if stats_data["total_books"]:
                    logging.info("Current price range: %.2f to %.2f", stats_data["price_min"], stats_data["price_max"])
            finally:
                store.close()
        elif args.command == "chart":
            store = Store(db_path)
            try:
                if getattr(args, "kind", None):
                    out_name = args.output if args.output != "price_history.png" else f"{args.kind}.png"
                    path = chart_aggregate(store, args.kind, out_name)
                    logging.info("Saved chart to %s", path)
                    print(f"Saved {args.kind} chart to {path}")
                elif getattr(args, "upc", None):
                    path = chart_history(store, args.upc, args.output)
                    logging.info("Saved chart to %s", path)
                    print(f"Saved price history chart to {path}")
                else:
                    raise ValueError("chart requires either --upc <UPC> or --kind <kind>")
            finally:
                store.close()
        elif args.command == "import-csv":
            store = Store(db_path)
            try:
                count = store.import_csv(args.path)
                logging.info("Imported %d records from %s", count, args.path)
                print(f"Successfully imported {count} records from {args.path}")
            finally:
                store.close()
        return 0
    except Exception as exc:
        logging.error("Run failed: %s", exc)
        return 1
