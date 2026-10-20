# Book Price Tracker

A small, cross-platform price history tool for [Books to Scrape](https://books.toscrape.com/), a site intended for scraping practice. It follows pagination, checks `robots.txt`, identifies itself honestly, and waits between requests.

## Install

Requires Python 3.10–3.13. Create and activate a virtual environment, then install:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install development tools with `python -m pip install -e ".[dev]"`. The package supports `python -m book_scraper` and the `book-scraper` console command. The original `python scrape.py` entry point remains available.

## Commands

```sh
book-scraper scrape                         # all pages, detail pages, SQLite history
book-scraper scrape --max-pages 5 --delay 1 --category Travel
book-scraper scrape --no-details            # quicker overview with listing data
book-scraper scrape --dry-run               # no database writes; writes a CSV preview
book-scraper changes                        # compare the most recent two runs
book-scraper export --format csv --category Travel --max-price 20
book-scraper export --format json --rating 5 --in-stock
book-scraper export --format xlsx --output current.xlsx
book-scraper stats
book-scraper chart --upc <UPC> --output history.png
```

The database defaults to `book_data.db`; set another path with the global `--db` option before the subcommand, such as `book-scraper --db data/prices.db scrape --max-pages 2`. A CSV snapshot named `book_data.csv` is also produced after each successful normal scrape. Use `--verbose` and `--log-file run.log` before the subcommand to enable debug logs and a log file. `--max-pages` is optional; without it, the scraper follows the site's next link.

Prices are saved as decimal strings in SQLite to avoid floating point rounding. Each run has a shared UTC timestamp, each listing page commits independently, and UPC is unique in the books table. A failed page stops the crawl with a logged failure; a run that found zero usable books exits non-zero.

## Tests and tools

Run the offline test suite with `pytest`. Tests use saved HTML and an in-memory database. Run quality tools with `ruff check .`, `ruff format --check .`, and `mypy book_scraper`. The GitHub Actions workflow runs lint, type checks, and tests on Python 3.10–3.13. No test makes a network request.

## Current scope

The reports include basic snapshot change detection, filtered exports, current price range statistics, and a per-book history chart. CSV/JSON/XLSX exports are generated from the latest stored snapshot. Notifications, a web dashboard, aggregate chart suite, and automatic legacy CSV import are not enabled in this release; no credentials or paid services are needed. Scheduled scraping is intentionally omitted: a scheduled workflow would need a deliberate policy for retaining and protecting the growing database artifact, and committing that data into the source branch can create noisy history.

This project targets a practice site. Before scraping any other site, check its `robots.txt`, terms of service, and applicable rules, and keep request rates low. This tool does not attempt to bypass access controls or rate limits.
