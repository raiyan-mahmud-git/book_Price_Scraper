"""Backward-compatible entry point: python scrape.py [scrape options]."""
from book_scraper.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
