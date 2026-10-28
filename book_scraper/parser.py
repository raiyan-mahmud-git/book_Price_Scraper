"""Pure HTML parsing functions. These functions never make network requests."""

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Book

BASE_URL = "https://books.toscrape.com/"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def parse_price(value: str) -> tuple[Decimal, str]:
    cleaned = value.strip().replace("Â", "")
    match = re.search(r"([£$€])\s*([\d,]+(?:\.\d{1,2})?)", cleaned)
    if not match:
        raise ValueError(f"Cannot parse price: {value!r}")
    try:
        amount = Decimal(match.group(2).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse price: {value!r}") from exc
    if amount <= 0:
        raise ValueError(f"Price must be positive: {value!r}")
    return amount, {"£": "GBP", "$": "USD", "€": "EUR"}[match.group(1)]


def parse_listing(html: str, page_url: str = BASE_URL) -> tuple[list[dict], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.product_pod")
    if not cards:
        raise ValueError(f"Listing selector article.product_pod missing at {page_url}")
    rows = []
    for card in cards:
        link = card.select_one("h3 a")
        price_node = card.select_one(".price_color")
        stock_node = card.select_one(".availability")
        if not link or not price_node or not stock_node:
            continue
        price, currency = parse_price(price_node.get_text())
        rating_node = card.select_one(".star-rating")
        rating = next((RATINGS[c] for c in rating_node.get("class", []) if c in RATINGS), 0) if rating_node else 0
        rows.append(
            {
                "title": str(link.get("title") or "").strip(),
                "url": urljoin(page_url, str(link.get("href", ""))),
                "price": price,
                "currency": currency,
                "in_stock": "in stock" in stock_node.get_text().lower(),
                "rating": rating,
            }
        )
    nxt = soup.select_one("li.next a")
    return rows, urljoin(page_url, str(nxt.get("href"))) if nxt and nxt.get("href") else None


def parse_detail(html: str, listing: dict, page_url: str) -> Book:
    soup = BeautifulSoup(html, "html.parser")
    table = {}
    for row in soup.select("table tr"):
        th = row.select_one("th")
        td = row.select_one("td")
        if th and td:
            table[th.get_text(strip=True)] = td.get_text(strip=True)

    def required(key: str) -> str:
        if key not in table:
            raise ValueError(f"Product detail field {key!r} missing at {page_url}")
        return table[key]

    image = soup.select_one(".item active img") or soup.select_one(".product_main img")
    description_node = soup.select_one("#product_description + p")
    breadcrumb = soup.select("ul.breadcrumb li a")
    availability = soup.select_one(".availability")
    stock_match = re.search(
        r"\((\d+)\s+available\)", availability.get_text(" ", strip=True) if availability else "", re.IGNORECASE
    )
    price_elem = soup.select_one(".price_color")
    price, currency = parse_price(price_elem.get_text(" ", strip=True) if price_elem else "")
    tax_text = table.get("Tax", "£0.00").replace("Â", "").replace("£", "").replace("$", "").replace("€", "")
    try:
        tax = Decimal(tax_text.strip())
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse tax: {table.get('Tax')!r}") from exc
    book = Book(
        upc=required("UPC"),
        title=listing["title"],
        price=price,
        currency=currency,
        in_stock=bool(availability and "in stock" in availability.get_text().lower()),
        rating=listing["rating"],
        product_url=page_url,
        image_url=urljoin(page_url, str(image.get("src", ""))) if image else "",
        category=breadcrumb[-1].get_text(strip=True) if len(breadcrumb) >= 3 else "",
        description=description_node.get_text(" ", strip=True) if description_node else "",
        stock_quantity=int(stock_match.group(1)) if stock_match else 0,
        number_of_reviews=int(table.get("Number of reviews", "0")),
        tax=tax,
    )
    book.validate()
    return book
