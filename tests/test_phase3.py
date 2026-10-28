from decimal import Decimal

from book_scraper import cli
from book_scraper.models import Book
from book_scraper.reports import chart_aggregate, format_stats, get_stats
from book_scraper.storage import Store


def _create_sample_db(path):
    store = Store(path)
    b1 = Book(
        "b1", "Book One", Decimal("10.00"), "GBP", True, 5, "https://books.toscrape.com/b1.html", category="Travel"
    )
    b2 = Book(
        "b2", "Book Two", Decimal("20.00"), "GBP", False, 3, "https://books.toscrape.com/b2.html", category="Travel"
    )
    b3 = Book(
        "b3", "Book Three", Decimal("35.00"), "GBP", True, 4, "https://books.toscrape.com/b3.html", category="Mystery"
    )
    store.save_page([b1, b2, b3], "2026-01-01T00:00:00+00:00")

    # Second run with price change
    b1_new = Book(
        "b1", "Book One", Decimal("15.00"), "GBP", True, 5, "https://books.toscrape.com/b1.html", category="Travel"
    )
    b3_new = Book(
        "b3", "Book Three", Decimal("25.00"), "GBP", True, 4, "https://books.toscrape.com/b3.html", category="Mystery"
    )
    store.save_page([b1_new, b3_new], "2026-01-02T00:00:00+00:00")
    return store


def test_chart_aggregate_kinds(tmp_path):
    db_path = tmp_path / "chart_test.db"
    store = _create_sample_db(db_path)

    for kind in ["category-avg", "rating-vs-price", "price-changes", "stock"]:
        out = tmp_path / f"test_{kind}.png"
        path = chart_aggregate(store, kind, out)
        assert path.exists()
        assert path.stat().st_size > 0

    store.close()


def test_cli_chart_commands(tmp_path, capsys):
    db_path = str(tmp_path / "cli_chart.db")
    store = _create_sample_db(db_path)
    store.close()

    # Aggregate chart
    out_cat = tmp_path / "out_cat.png"
    rc = cli.main(["--db", db_path, "chart", "--kind", "category-avg", "--output", str(out_cat)])
    assert rc == 0
    assert out_cat.exists()

    # Per-book chart
    out_book = tmp_path / "out_book.png"
    rc = cli.main(["--db", db_path, "chart", "--upc", "b1", "--output", str(out_book)])
    assert rc == 0
    assert out_book.exists()

    # Neither upc nor kind -> fails
    rc = cli.main(["--db", db_path, "chart"])
    assert rc == 1


def test_import_csv(tmp_path, capsys):
    db_path = str(tmp_path / "import_test.db")
    store = Store(db_path)

    # Create a legacy CSV
    csv_path = tmp_path / "legacy_data.csv"
    csv_path.write_text(
        "upc,title,price,currency,in_stock,category,rating\n"
        "leg1,Legacy Alpha,12.50,GBP,True,Fiction,4\n"
        "leg2,Legacy Beta,24.00,GBP,False,History,2\n",
        encoding="utf-8",
    )

    imported = store.import_csv(csv_path)
    assert imported == 2
    assert len(store.all_latest()) == 2

    # Second import of identical data must not create duplicates
    imported_again = store.import_csv(csv_path)
    assert imported_again == 0
    assert len(store.all_latest()) == 2
    store.close()

    # Test via CLI
    rc = cli.main(["--db", db_path, "import-csv", str(csv_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "imported 0 records" in out.lower() or "0" in out


def test_improved_stats(tmp_path, capsys):
    db_path = str(tmp_path / "stats_test.db")
    store = _create_sample_db(db_path)

    stats = get_stats(store)
    assert stats["total_books"] == 3
    assert stats["in_stock"] == 2
    assert stats["out_of_stock"] == 1
    assert stats["distribution"]["£10 - £20"] == 1
    assert stats["distribution"]["£20 - £30"] == 2
    assert "Travel" in stats["categories"]
    assert "Mystery" in stats["categories"]
    assert len(stats["largest_increases"]) == 1
    assert stats["largest_increases"][0]["upc"] == "b1"
    assert len(stats["largest_decreases"]) == 1
    assert stats["largest_decreases"][0]["upc"] == "b3"

    formatted = format_stats(stats)
    assert "Price Tracker Statistics" in formatted
    assert "Books Tracked: 3" in formatted
    assert "Largest Price Increases" in formatted
    assert "Largest Price Decreases" in formatted
    store.close()

    # Test via CLI
    rc = cli.main(["--db", db_path, "stats"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Price Tracker Statistics" in out
