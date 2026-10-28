from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest

from book_scraper import scraper
from book_scraper.http import SiteClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_crawl_offline_full_cycle(tmp_path, monkeypatch):
    listing_html = (FIXTURES / "listing.html").read_text(encoding="utf-8")
    last_page_html = (FIXTURES / "last_page.html").read_text(encoding="utf-8")
    detail_html = (FIXTURES / "detail.html").read_text(encoding="utf-8")

    db_path = str(tmp_path / "crawled.db")

    client = SiteClient(delay=0, no_cache=True)
    client._robots = RobotFileParser()
    client._robots.parse(["User-agent: *", "Allow: /"])

    def fake_get(url):
        if "sample" in url or "catalogue" in url and "page" not in url:
            return detail_html
        if "page-2" in url:
            return last_page_html
        return listing_html

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(scraper, "SiteClient", lambda **kwargs: client)

    books, run_time = scraper.crawl(
        max_pages=2,
        details=True,
        dry_run=False,
        output=db_path,
        delay=0,
        no_cache=True,
    )
    assert len(books) > 0
    assert run_time is not None

    # Test crawl with zero books raises RuntimeError
    def empty_listing(url):
        return "<html><body><article class='product_pod'></article></body></html>"

    monkeypatch.setattr(client, "get", empty_listing)
    with pytest.raises(RuntimeError, match="No books were scraped"):
        scraper.crawl(max_pages=1, details=False, dry_run=True, delay=0, no_cache=True)
