import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time

BASE_URL = "https://books.toscrape.com/catalogue/page-{}.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def scrape_books(pages=3):
    all_data = []

    for page in range(1, pages + 1):
        print(f"Scraping page {page}...")
        url = BASE_URL.format(page)

        response = requests.get(url, headers=HEADERS)

        if response.status_code != 200:
            print(f"Failed to retrieve page {page}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        books = soup.find_all("article", class_="product_pod")

        for book in books:
            title = book.h3.a["title"]
            price = book.find("p", class_="price_color").text.strip()
            availability = book.find("p", class_="instock availability").text.strip()

            all_data.append({
                "Book Title": title,
                "Price": price,
                "Availability Status": availability,
                "Scraped At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        time.sleep(1)

    return all_data


def save_to_csv(data):
    df = pd.DataFrame(data)
    df.to_csv("book_data.csv", index=False)
    print("Data saved to book_data.csv")


if __name__ == "__main__":
    print("Starting Book Price Scraper...")
    scraped_data = scrape_books(pages=5)
    save_to_csv(scraped_data)
    print("Scraping completed successfully.")