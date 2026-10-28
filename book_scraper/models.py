"""Validated data models used by the scraper and database."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Book:
    upc: str
    title: str
    price: Decimal
    currency: str
    in_stock: bool
    rating: int
    product_url: str
    image_url: str = ""
    category: str = ""
    description: str = ""
    stock_quantity: int = 0
    number_of_reviews: int = 0
    tax: Decimal = Decimal(0)

    def validate(self) -> None:
        if not self.upc or not self.title:
            raise ValueError("Book requires a UPC and title")
        if self.price <= 0:
            raise ValueError("Price must be greater than zero")
        if not 1 <= self.rating <= 5:
            raise ValueError("Rating must be from 1 to 5")
        if not self.product_url.startswith("https://books.toscrape.com/"):
            raise ValueError("Product URL is not a Books to Scrape URL")


@dataclass
class PricePoint:
    upc: str
    price: Decimal
    in_stock: bool
    scraped_at: str
