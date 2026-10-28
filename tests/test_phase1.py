import sqlite3
from decimal import Decimal
from urllib.robotparser import RobotFileParser

import pytest
import requests

from book_scraper import cli
from book_scraper.cache import HttpCache
from book_scraper.config import load_config
from book_scraper.http import SiteClient, parse_retry_after
from book_scraper.models import Book
from book_scraper.storage import Store, get_schema_version, migrate_database


def _mock_client(retries=2, max_backoff=60.0, cache=None, no_cache=False):
    client = SiteClient(delay=0, retries=retries, max_backoff=max_backoff, cache=cache, no_cache=no_cache)
    client._robots = RobotFileParser()
    client._robots.parse(["User-agent: *", "Allow: /"])
    return client


def test_parse_retry_after():
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("invalid") is None
    # HTTP date in the past should clamp to 0.0
    assert parse_retry_after("Fri, 31 Dec 1999 23:59:59 GMT") == 0.0


def test_http_retry_honors_retry_after(monkeypatch):
    client = _mock_client(retries=2, max_backoff=10.0, no_cache=True)
    sleeps = []

    class MockResponse:
        def __init__(self, status_code, headers):
            self.status_code = status_code
            self.headers = headers
            self.encoding = "utf-8"
            self.text = "ok"

        def raise_for_status(self):
            if self.status_code >= 400:
                err = requests.HTTPError(f"HTTP {self.status_code}")
                err.response = self  # type: ignore[attr-defined]
                raise err

    calls = 0

    def mock_get(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return MockResponse(429, {"Retry-After": "2.5"})
        return MockResponse(200, {})

    monkeypatch.setattr(client.session, "get", mock_get)
    monkeypatch.setattr("book_scraper.http.time.sleep", lambda s: sleeps.append(s))

    assert client.get("https://books.toscrape.com/catalogue/page-1.html") == "ok"
    assert calls == 2
    assert any(2.4 <= s <= 2.6 for s in sleeps)


def test_http_connection_error_exponential_backoff(monkeypatch):
    client = _mock_client(retries=3, max_backoff=5.0, no_cache=True)
    sleeps = []
    calls = 0

    class MockResponse:
        status_code = 200
        encoding = "utf-8"
        text = "content"
        headers: dict[str, str] = {}

        def raise_for_status(self):
            pass

    def mock_get(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise requests.ConnectionError("Connection reset")
        return MockResponse()

    monkeypatch.setattr(client.session, "get", mock_get)
    monkeypatch.setattr("book_scraper.http.time.sleep", lambda s: sleeps.append(s))

    assert client.get("https://books.toscrape.com/catalogue/page-1.html") == "content"
    assert calls == 3
    # Check that retry sleeps were executed
    assert len(sleeps) >= 2


def test_conditional_requests_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "test_cache.sqlite"
    cache = HttpCache(cache_file)
    client = _mock_client(retries=1, cache=cache, no_cache=False)

    class MockResponse:
        def __init__(self, status_code, text, headers):
            self.status_code = status_code
            self.text = text
            self.headers = headers
            self.encoding = "utf-8"

        def raise_for_status(self):
            pass

    req_headers_captured = []

    def mock_get(self, url, headers=None, **kwargs):
        req_headers_captured.append(headers or {})
        if headers and headers.get("If-None-Match") == '"xyz"':
            return MockResponse(304, "", {})
        return MockResponse(200, "original html", {"ETag": '"xyz"', "Last-Modified": "Wed, 21 Oct 2026 07:28:00 GMT"})

    monkeypatch.setattr(requests.Session, "get", mock_get)
    monkeypatch.setattr("book_scraper.http.time.sleep", lambda s: None)

    # First fetch: 200, saved in cache
    res1 = client.get("https://books.toscrape.com/catalogue/book1.html")
    assert res1 == "original html"
    assert req_headers_captured[0] == {}

    # Second fetch: sends conditional headers, gets 304, returns cached text
    res2 = client.get("https://books.toscrape.com/catalogue/book1.html")
    assert res2 == "original html"
    assert req_headers_captured[1].get("If-None-Match") == '"xyz"'

    # With no_cache: does not use cache
    client_nocache = _mock_client(retries=1, cache=cache, no_cache=True)
    res3 = client_nocache.get("https://books.toscrape.com/catalogue/book1.html")
    assert res3 == "original html"
    assert req_headers_captured[2] == {}
    cache.close()


def test_book_model_validation():
    # Valid book
    valid = Book(
        upc="abc12345",
        title="Valid Title",
        price=Decimal("12.99"),
        currency="GBP",
        in_stock=True,
        rating=4,
        product_url="https://books.toscrape.com/catalogue/book.html",
    )
    valid.validate()

    # Empty UPC
    with pytest.raises(ValueError, match="non-empty UPC"):
        Book("", "Title", Decimal("10"), "GBP", True, 3, "https://books.toscrape.com/b.html").validate()

    # Negative price
    with pytest.raises(ValueError, match="positive Decimal"):
        Book("upc", "Title", Decimal("-1"), "GBP", True, 3, "https://books.toscrape.com/b.html").validate()

    # Invalid rating
    with pytest.raises(ValueError, match="Rating must be from 1 to 5"):
        Book("upc", "Title", Decimal("10"), "GBP", True, 6, "https://books.toscrape.com/b.html").validate()

    # Invalid domain
    with pytest.raises(ValueError, match="Books to Scrape URL"):
        Book("upc", "Title", Decimal("10"), "GBP", True, 3, "https://other.com/b.html").validate()


def test_schema_migration_runner(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    # Create legacy v1 schema without watchlist
    conn.executescript(
        """
        CREATE TABLE books(id INTEGER PRIMARY KEY, upc TEXT UNIQUE NOT NULL, title TEXT,
          currency TEXT, product_url TEXT, image_url TEXT, category TEXT, description TEXT, rating INTEGER,
          stock_quantity INTEGER, number_of_reviews INTEGER, tax TEXT);
        CREATE TABLE price_history(id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
          price TEXT NOT NULL, in_stock INTEGER NOT NULL, scraped_at TEXT NOT NULL);
        INSERT INTO books(upc, title) VALUES('legacy1', 'Old Book');
        """
    )
    conn.commit()

    # Should detect as legacy v1
    assert get_schema_version(conn) == 1

    # Run migration
    new_version = migrate_database(conn)
    assert new_version == 2
    assert get_schema_version(conn) == 2

    # Check that data was preserved and watchlist table exists
    row = conn.execute("SELECT title FROM books WHERE upc = 'legacy1'").fetchone()
    assert row[0] == "Old Book"
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "watchlist" in tables
    assert "schema_version" in tables
    conn.close()

    # Store handles it seamlessly
    store = Store(db_path)
    assert store.get_watchlist() == []
    store.close()


def test_config_file_and_cli_overrides(tmp_path, monkeypatch):
    cfg_file = tmp_path / "test-config.toml"
    cfg_file.write_text(
        """
[scraper]
delay = 3.5
retries = 5
max_backoff = 45.0
category = "Poetry"
no_cache = true

[database]
path = "from_config.db"
""",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    assert config["scraper"]["delay"] == 3.5
    assert config["database"]["path"] == "from_config.db"

    # Test CLI using config with override
    calls = []

    def mock_crawl(**kwargs):
        calls.append(kwargs)
        return [], "2026-01-01T00:00:00+00:00"

    monkeypatch.setattr(cli, "crawl", mock_crawl)

    # Scrape with config, no overrides: gets values from config
    cli.main(["--config", str(cfg_file), "scrape"])
    assert calls[0]["delay"] == 3.5
    assert calls[0]["retries"] == 5
    assert calls[0]["category"] == "Poetry"
    assert calls[0]["no_cache"] is True
    assert calls[0]["output"] == "from_config.db"

    # Scrape with CLI overrides: CLI wins
    cli.main(["--config", str(cfg_file), "--db", "cli_override.db", "scrape", "--delay", "0.5", "--category", "Music"])
    assert calls[1]["delay"] == 0.5
    assert calls[1]["category"] == "Music"
    assert calls[1]["output"] == "cli_override.db"
