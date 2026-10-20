"""Crawl listing and product pages, saving each completed page as it finishes."""
from datetime import datetime, timezone
import logging
from urllib.parse import urljoin
from .http import SiteClient
from .models import Book
from .parser import parse_listing, parse_detail
from .storage import Store

LOG = logging.getLogger(__name__)
START_URL = "https://books.toscrape.com/"


def crawl(max_pages: int | None = None, details: bool = True, dry_run: bool = False,
          output: str = "book_data.db", delay: float = 1.0, category: str | None = None) -> tuple[list[Book], str]:
    client = SiteClient(delay=delay)
    store = None if dry_run else Store(output)
    run_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seen: set[str] = set(); all_books: list[Book] = []; page_url = urljoin(START_URL, "catalogue/page-1.html")
    page_count = failed = skipped = 0
    try:
        while page_url and (max_pages is None or page_count < max_pages):
            page_count += 1
            try:
                rows, next_url = parse_listing(client.get(page_url), page_url)
                # Detail pages expose stable UPC identifiers and the remaining fields.
                current: list[Book] = []
                for row in rows:
                    try:
                        book = parse_detail(client.get(row["url"]), row, row["url"]) if details else Book(
                            upc=row["url"], title=row["title"], price=row["price"], currency=row["currency"],
                            in_stock=row["in_stock"], rating=row["rating"] or 1, product_url=row["url"])
                        if book.upc in seen:
                            LOG.warning("Duplicate UPC %s skipped", book.upc); continue
                        if category and book.category.lower() != category.lower(): continue
                        seen.add(book.upc); current.append(book)
                    except (ValueError, RuntimeError) as exc:
                        skipped += 1; LOG.warning("Skipping product %s: %s", row["url"], exc)
                all_books.extend(current)
                if store: store.save_page(current, run_time)
                LOG.info("Saved page %d (%d books)", page_count, len(current))
                page_url = next_url
            except (RuntimeError, ValueError) as exc:
                failed += 1; LOG.error("Page %d failed: %s", page_count, exc)
                # Stop on an inaccessible listing page; later pages may be linked from it.
                break
    finally:
        if store: store.close()
    LOG.info("Run summary: pages ok=%d failed=%d, books=%d, skipped=%d", page_count-failed, failed, len(all_books), skipped)
    if not all_books: raise RuntimeError("No books were scraped; no export was written")
    if failed: raise RuntimeError(f"Scrape incomplete: {failed} listing page(s) failed; completed pages remain saved")
    return all_books, run_time
