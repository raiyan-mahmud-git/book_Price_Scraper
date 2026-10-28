from decimal import Decimal

import requests

from book_scraper import cli
from book_scraper.alerts import (
    Alert,
    ConsoleNotifier,
    DiscordNotifier,
    TelegramNotifier,
    evaluate_watchlist,
)
from book_scraper.models import Book
from book_scraper.storage import Store


def _save_sample_book(store: Store, upc: str, title: str, price: str, timestamp: str):
    book = Book(
        upc=upc,
        title=title,
        price=Decimal(price),
        currency="GBP",
        in_stock=True,
        rating=4,
        product_url="https://books.toscrape.com/catalogue/sample.html",
    )
    store.save_page([book], timestamp)


def test_watch_add_list_remove(tmp_path):
    db_path = tmp_path / "test_watch.db"
    store = Store(db_path)

    # Add watch
    store.add_watch("upc123", below_price=Decimal("25.00"), drop_percent=10.0)
    items = store.get_watchlist()
    assert len(items) == 1
    assert items[0]["upc"] == "upc123"
    assert items[0]["below_price"] == "25.00"
    assert items[0]["drop_percent"] == 10.0

    # Update watch
    store.add_watch("upc123", below_price=Decimal("20.00"), drop_percent=15.0)
    items = store.get_watchlist()
    assert len(items) == 1
    assert items[0]["below_price"] == "20.00"

    # Remove watch
    assert store.remove_watch("upc123") is True
    assert store.remove_watch("upc123") is False
    assert len(store.get_watchlist()) == 0
    store.close()


def test_cli_watch_commands(tmp_path, capsys):
    db_path = str(tmp_path / "cli_watch.db")

    # Add
    rc = cli.main(["--db", db_path, "watch", "add", "--upc", "book-1", "--below", "15.50", "--drop-percent", "20"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Added watch for UPC book-1" in out

    # List
    rc = cli.main(["--db", db_path, "watch", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "book-1" in out
    assert "15.50" in out

    # Remove
    rc = cli.main(["--db", db_path, "watch", "remove", "--upc", "book-1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Removed watch for UPC book-1" in out

    # List empty
    rc = cli.main(["--db", db_path, "watch", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Watchlist is empty" in out


def test_console_notifier(capsys):
    notifier = ConsoleNotifier()
    alert = Alert(
        upc="abc",
        title="Test Book",
        current_price=Decimal("19.99"),
        currency="GBP",
        reason="Below 20.00",
        previous_price=Decimal("25.00"),
    )
    assert notifier.notify(alert) is True
    out = capsys.readouterr().out
    assert "Price Alert for 'Test Book'" in out
    assert "19.99" in out


def test_discord_notifier_mocked(monkeypatch):
    posted_payloads = []

    class MockResp:
        status_code = 204

        def raise_for_status(self):
            pass

    def mock_post(url, json=None, timeout=None):
        posted_payloads.append((url, json))
        return MockResp()

    monkeypatch.setattr(requests, "post", mock_post)

    notifier = DiscordNotifier("https://discord.com/api/webhooks/123/xyz")
    alert = Alert(
        upc="abc",
        title="Discord Book",
        current_price=Decimal("10.00"),
        currency="GBP",
        reason="Target met",
    )
    assert notifier.notify(alert) is True
    assert len(posted_payloads) == 1
    assert "Discord Book" in posted_payloads[0][1]["content"]


def test_telegram_notifier_mocked(monkeypatch):
    posted_payloads = []

    class MockResp:
        status_code = 200

        def raise_for_status(self):
            pass

    def mock_post(url, json=None, timeout=None):
        posted_payloads.append((url, json))
        return MockResp()

    monkeypatch.setattr(requests, "post", mock_post)

    notifier = TelegramNotifier(bot_token="test-token", chat_id="123456")
    alert = Alert(
        upc="abc",
        title="Telegram Book",
        current_price=Decimal("12.50"),
        currency="GBP",
        reason="Target met",
    )
    assert notifier.notify(alert) is True
    assert len(posted_payloads) == 1
    assert posted_payloads[0][0] == "https://api.telegram.org/bottest-token/sendMessage"
    assert posted_payloads[0][1]["chat_id"] == "123456"
    assert "Telegram Book" in posted_payloads[0][1]["text"]


def test_watchlist_alert_conditions_and_duplicate_suppression(tmp_path):
    db_path = tmp_path / "alerts.db"
    store = Store(db_path)

    # Save initial price 30.00
    _save_sample_book(store, "upc1", "Book 1", "30.00", "2026-01-01T00:00:00+00:00")
    # Add watch below 25.00 or drop 20%
    store.add_watch("upc1", below_price=Decimal("25.00"), drop_percent=20.0)

    # First check: price is 30.00, does not meet below 25.00 and no drop yet
    alerts = evaluate_watchlist(store, dry_run=False, notifiers=[])
    assert len(alerts) == 0

    # Scrape 2: price drops to 24.00 (meets below 25.00 and 20% drop from 30.00)
    _save_sample_book(store, "upc1", "Book 1", "24.00", "2026-01-02T00:00:00+00:00")
    alerts = evaluate_watchlist(store, dry_run=False, notifiers=[])
    assert len(alerts) == 1
    assert alerts[0].upc == "upc1"
    assert alerts[0].current_price == Decimal("24.00")

    # Scrape 3: price is still 24.00 -> duplicate alert suppressed!
    _save_sample_book(store, "upc1", "Book 1", "24.00", "2026-01-03T00:00:00+00:00")
    alerts = evaluate_watchlist(store, dry_run=False, notifiers=[])
    assert len(alerts) == 0

    # Scrape 4: price drops further to 18.00 -> new alert triggered!
    _save_sample_book(store, "upc1", "Book 1", "18.00", "2026-01-04T00:00:00+00:00")
    alerts = evaluate_watchlist(store, dry_run=False, notifiers=[])
    assert len(alerts) == 1
    assert alerts[0].current_price == Decimal("18.00")
    store.close()


def test_watchlist_dry_run(tmp_path, capsys):
    db_path = tmp_path / "dry_run_alerts.db"
    store = Store(db_path)
    _save_sample_book(store, "upc99", "Special Book", "10.00", "2026-01-01T00:00:00+00:00")
    store.add_watch("upc99", below_price=Decimal("15.00"))

    # Dry-run: evaluates alert, prints it, but does NOT update last_alerted_price
    alerts = evaluate_watchlist(store, dry_run=True, notifiers=[])
    assert len(alerts) == 1
    out = capsys.readouterr().out
    assert "[DRY RUN ALERT] Would send" in out

    # Verify last_alerted_price is still None in DB
    watch = store.get_watchlist()[0]
    assert watch["last_alerted_price"] is None
    store.close()
