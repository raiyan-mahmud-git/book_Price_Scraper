from decimal import Decimal
from pathlib import Path
import pytest
from book_scraper.parser import parse_price, parse_listing, parse_detail
from book_scraper.storage import Store
from book_scraper.reports import changes

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name): return (FIXTURES / name).read_text(encoding="utf-8")


def test_price_and_encoding():
    assert parse_price("Â£51.77") == (Decimal("51.77"), "GBP")
    with pytest.raises(ValueError): parse_price("unknown")


def test_listing_rating_pagination_and_last_page():
    rows, nxt = parse_listing(fixture("listing.html"), "https://books.toscrape.com/catalogue/page-1.html")
    assert rows[0]["rating"] == 3 and rows[0]["price"] == Decimal("51.77")
    assert nxt.endswith("page-2.html")
    rows, nxt = parse_listing(fixture("last_page.html"), "https://books.toscrape.com/page.html")
    assert rows[0]["rating"] == 5 and nxt is None and not rows[0]["in_stock"]


def test_malformed_listing_is_clear():
    with pytest.raises(ValueError, match="article.product_pod"):
        parse_listing(fixture("malformed.html"))


def test_detail_fields():
    listing = {"title": "A Sample Book", "price": Decimal("51.77"), "currency": "GBP", "in_stock": True,
               "rating": 3, "url": "https://books.toscrape.com/catalogue/sample.html"}
    book = parse_detail(fixture("detail.html"), listing, listing["url"])
    assert book.upc == "123456789abc" and book.category == "Travel" and book.stock_quantity == 22


def test_sqlite_round_trip_and_changes():
    store = Store(":memory:")
    store.save_page([_book("one", "10", True)], "2026-01-01T00:00:00+00:00")
    store.save_page([_book("one", "8", False), _book("two", "4", True)], "2026-01-02T00:00:00+00:00")
    assert store.all_latest()[0]["upc"] == "one"
    result = changes(store)
    assert result["new"] == ["two"] and result["drops"][0][0] == "one" and result["out_of_stock"] == ["one"]
    store.close()


def test_http_retry_timeout_and_429(monkeypatch):
    import requests
    from urllib.robotparser import RobotFileParser
    from book_scraper.http import SiteClient
    client = SiteClient(delay=0, retries=2)
    client._robots = RobotFileParser()
    client._robots.parse(["User-agent: *", "Allow: /"])
    calls = []
    class Response:
        def __init__(self, status): self.status_code = status; self.encoding = None
        @property
        def text(self): return "£2.50"
        def raise_for_status(self):
            if self.status_code >= 400: raise requests.HTTPError(f"HTTP {self.status_code}")
    def fake_get(url, timeout):
        calls.append(timeout)
        return Response(429 if len(calls) == 1 else 200)
    monkeypatch.setattr(client.session, "get", fake_get)
    monkeypatch.setattr("book_scraper.http.time.sleep", lambda seconds: None)
    assert client.get("https://books.toscrape.com/page.html") == "£2.50"
    assert len(calls) == 2 and calls[0] == (5, 20)


def test_cli_all_pages_failed_exits_nonzero(monkeypatch):
    from book_scraper import cli
    def fail(**kwargs): raise RuntimeError("No books were scraped")
    monkeypatch.setattr(cli, "crawl", fail)
    assert cli.main(["scrape"]) == 1


def _book(upc, price, stock):
    from book_scraper.models import Book
    return Book(upc, upc, Decimal(price), "GBP", stock, 3, "https://books.toscrape.com/book.html")
