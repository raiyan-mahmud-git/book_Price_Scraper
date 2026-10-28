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
        if not self.upc or not self.upc.strip():
            raise ValueError("Book requires a non-empty UPC")
        if not self.title or not self.title.strip():
            raise ValueError("Book requires a non-empty title")
        if not isinstance(self.price, Decimal) or self.price <= 0:
            raise ValueError(f"Price must be a positive Decimal, got {self.price!r}")
        if not self.currency or not self.currency.strip():
            raise ValueError("Currency must not be empty")
        if not 1 <= self.rating <= 5:
            raise ValueError(f"Rating must be from 1 to 5, got {self.rating}")
        if not (
            self.product_url.startswith("https://books.toscrape.com/")
            or self.product_url.startswith("http://books.toscrape.com/")
        ):
            raise ValueError("Product URL is not a Books to Scrape URL")
        if self.stock_quantity < 0:
            raise ValueError("Stock quantity cannot be negative")
        if self.number_of_reviews < 0:
            raise ValueError("Number of reviews cannot be negative")
        if not isinstance(self.tax, Decimal) or self.tax < 0:
            raise ValueError("Tax must be a non-negative Decimal")


@dataclass
class PricePoint:
    upc: str
    price: Decimal
    in_stock: bool
    scraped_at: str
