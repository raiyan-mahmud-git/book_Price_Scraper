"""Watchlist alert evaluation and pluggable notifiers (Console, Discord, Telegram)."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests

from .storage import Store

LOG = logging.getLogger(__name__)


@dataclass
class Alert:
    upc: str
    title: str
    current_price: Decimal
    currency: str
    reason: str
    previous_price: Decimal | None = None

    def format_message(self) -> str:
        if self.previous_price is not None:
            return (
                f"🚨 Price Alert for '{self.title}' (UPC: {self.upc}): "
                f"Dropped to {self.currency} {self.current_price:.2f} "
                f"(was {self.currency} {self.previous_price:.2f}). Reason: {self.reason}"
            )
        return (
            f"🚨 Price Alert for '{self.title}' (UPC: {self.upc}): "
            f"Price is {self.currency} {self.current_price:.2f}. Reason: {self.reason}"
        )


class BaseNotifier(ABC):
    @abstractmethod
    def notify(self, alert: Alert) -> bool:
        """Send notification. Return True if successful."""
        raise NotImplementedError


class ConsoleNotifier(BaseNotifier):
    def notify(self, alert: Alert) -> bool:
        message = alert.format_message()
        print(message)
        LOG.info("Alert dispatched to Console: %s", message)
        return True


class DiscordNotifier(BaseNotifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, alert: Alert) -> bool:
        if not self.webhook_url:
            return False
        payload = {"content": alert.format_message()}
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            LOG.info("Alert dispatched to Discord for UPC %s", alert.upc)
            return True
        except Exception as exc:
            LOG.error("Failed to dispatch Discord alert: %s", exc)
            return False


class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def notify(self, alert: Alert) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": alert.format_message()}
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            LOG.info("Alert dispatched to Telegram for UPC %s", alert.upc)
            return True
        except Exception as exc:
            LOG.error("Failed to dispatch Telegram alert: %s", exc)
            return False


def get_notifiers(config: dict[str, Any] | None = None) -> list[BaseNotifier]:
    """Build list of active notifiers from environment variables and config."""
    notifiers: list[BaseNotifier] = [ConsoleNotifier()]
    cfg = config or {}
    alerts_cfg = cfg.get("alerts", {})

    discord_url = os.environ.get("DISCORD_WEBHOOK_URL") or alerts_cfg.get("discord_webhook_url")
    if discord_url:
        notifiers.append(DiscordNotifier(discord_url))

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN") or alerts_cfg.get("telegram_bot_token")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or alerts_cfg.get("telegram_chat_id")
    if tg_token and tg_chat_id:
        notifiers.append(TelegramNotifier(tg_token, str(tg_chat_id)))

    return notifiers


def evaluate_watchlist(
    store: Store,
    dry_run: bool = False,
    config: dict[str, Any] | None = None,
    notifiers: list[BaseNotifier] | None = None,
) -> list[Alert]:
    """Check current prices against watchlist and send alerts."""
    items = store.get_watchlist()
    if not items:
        return []

    if notifiers is None:
        notifiers = get_notifiers(config)

    triggered_alerts: list[Alert] = []

    for item in items:
        upc = item["upc"]
        book_row = store.db.execute("SELECT id, title, currency FROM books WHERE upc = ?", (upc,)).fetchone()
        if not book_row:
            continue
        book_id, title, currency = book_row["id"], book_row["title"], book_row["currency"] or "GBP"

        # Get latest price points (up to 2 for drop percent calculation)
        history = store.db.execute(
            "SELECT price, scraped_at FROM price_history WHERE book_id = ? ORDER BY id DESC LIMIT 2",
            (book_id,),
        ).fetchall()
        if not history:
            continue

        current_price = Decimal(history[0]["price"])
        prev_price = Decimal(history[1]["price"]) if len(history) > 1 else None

        # Check duplicate suppression: do not re-alert for same price
        if item["last_alerted_price"] is not None and Decimal(item["last_alerted_price"]) == current_price:
            continue

        reasons = []
        # Check below price
        if item["below_price"] is not None:
            target = Decimal(item["below_price"])
            if current_price <= target:
                reasons.append(f"Price {currency} {current_price:.2f} <= target {currency} {target:.2f}")

        # Check drop percent
        if item["drop_percent"] is not None and prev_price is not None and prev_price > 0:
            drop_pct = float((prev_price - current_price) / prev_price * Decimal(100))
            if drop_pct >= float(item["drop_percent"]):
                reasons.append(f"Price dropped {drop_pct:.1f}% (threshold {item['drop_percent']}%)")

        if reasons:
            alert = Alert(
                upc=upc,
                title=title or upc,
                current_price=current_price,
                currency=currency,
                reason="; ".join(reasons),
                previous_price=prev_price,
            )
            triggered_alerts.append(alert)

            if dry_run:
                print(f"[DRY RUN ALERT] Would send: {alert.format_message()}")
                LOG.info("[DRY RUN ALERT] Would send: %s", alert.format_message())
            else:
                for notifier in notifiers:
                    notifier.notify(alert)
                store.update_watch_alerted(upc, str(current_price))

    return triggered_alerts
