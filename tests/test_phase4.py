from decimal import Decimal

import pytest

try:
    from fastapi.testclient import TestClient
    from book_scraper.web.app import create_app

    HAS_WEB = True
except ImportError:
    HAS_WEB = False

from book_scraper.models import Book
from book_scraper.storage import Store


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "web_test.db"
    store = Store(db_file)
    b1 = Book(
        "web-upc-1",
        "Web Journey",
        Decimal("14.99"),
        "GBP",
        True,
        5,
        "https://books.toscrape.com/catalogue/web1.html",
        category="Travel",
    )
    b2 = Book(
        "web-upc-2",
        "Python Secrets",
        Decimal("29.99"),
        "GBP",
        False,
        4,
        "https://books.toscrape.com/catalogue/web2.html",
        category="Computers",
    )
    store.save_page([b1, b2], "2026-01-01T12:00:00+00:00")
    store.add_watch("web-upc-1", below_price=Decimal("15.00"), drop_percent=10.0)
    store.close()
    return str(db_file)


@pytest.mark.skipif(not HAS_WEB, reason="FastAPI web dependencies not installed")
def test_web_overview_page(test_db):
    app = create_app(test_db)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert "System Overview" in response.text
    assert "Total Books" in response.text
    assert "2026-01-01T12:00:00+00:00" in response.text


@pytest.mark.skipif(not HAS_WEB, reason="FastAPI web dependencies not installed")
def test_web_books_page_and_filtering(test_db):
    app = create_app(test_db)
    client = TestClient(app)

    # All books
    r1 = client.get("/books")
    assert r1.status_code == 200
    assert "Web Journey" in r1.text
    assert "Python Secrets" in r1.text

    # Search filter
    r2 = client.get("/books?q=Journey")
    assert r2.status_code == 200
    assert "Web Journey" in r2.text
    assert "Python Secrets" not in r2.text

    # Category filter
    r3 = client.get("/books?category=Computers")
    assert r3.status_code == 200
    assert "Python Secrets" in r3.text
    assert "Web Journey" not in r3.text

    # In stock filter
    r4 = client.get("/books?in_stock=true")
    assert r4.status_code == 200
    assert "Web Journey" in r4.text
    assert "Python Secrets" not in r4.text


@pytest.mark.skipif(not HAS_WEB, reason="FastAPI web dependencies not installed")
def test_web_book_detail_and_chart(test_db):
    app = create_app(test_db)
    client = TestClient(app)

    # Valid book detail
    r = client.get("/book/web-upc-1")
    assert r.status_code == 200
    assert "Web Journey" in r.text
    assert "14.99" in r.text

    # Nonexistent book
    r_404 = client.get("/book/nonexistent")
    assert r_404.status_code == 404

    # Chart image API
    r_img = client.get("/api/chart/web-upc-1")
    assert r_img.status_code == 200
    assert r_img.headers["content-type"] == "image/png"
    assert len(r_img.content) > 0


@pytest.mark.skipif(not HAS_WEB, reason="FastAPI web dependencies not installed")
def test_web_changes_and_watchlist(test_db):
    app = create_app(test_db)
    client = TestClient(app)

    # Changes
    r_chg = client.get("/changes")
    assert r_chg.status_code == 200
    assert "Recent Snapshot Changes" in r_chg.text

    # Watchlist
    r_wl = client.get("/watchlist")
    assert r_wl.status_code == 200
    assert "Price Watchlist" in r_wl.text
    assert "web-upc-1" in r_wl.text
    assert "Target Met!" in r_wl.text


@pytest.mark.skipif(not HAS_WEB, reason="FastAPI web dependencies not installed")
def test_web_json_api(test_db):
    app = create_app(test_db)
    client = TestClient(app)

    r_over = client.get("/api/overview")
    assert r_over.status_code == 200
    data = r_over.json()
    assert data["total_books"] == 2
    assert data["in_stock"] == 1

    r_books = client.get("/api/books")
    assert r_books.status_code == 200
    assert len(r_books.json()) == 2

    r_wl = client.get("/api/watchlist")
    assert r_wl.status_code == 200
    assert len(r_wl.json()) == 1
    assert r_wl.json()[0]["upc"] == "web-upc-1"
