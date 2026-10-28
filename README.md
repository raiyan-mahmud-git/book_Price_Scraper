# Book Price Tracker

A polite, robust, and extensible price history tracking tool and dashboard for [Books to Scrape](https://books.toscrape.com/) (an educational site intended for scraping practice). It respects `robots.txt`, identifies itself honestly with a descriptive User-Agent, enforces configurable delays, caches unmodified pages, and stores price history in SQLite using decimal string representations for currency accuracy.

## Architecture

The system is organized into decoupled, modular components:

- **`book_scraper.http`**: `SiteClient` manages polite HTTP requests with `robots.txt` enforcement, exponential backoff with random jitter, `Retry-After` header parsing, and integration with `HttpCache`.
- **`book_scraper.cache`**: SQLite-backed conditional request cache storing `ETag` and `Last-Modified` headers to avoid redundant page transfers with HTTP 304 Not Modified.
- **`book_scraper.models`**: Strictly validated dataclass domain models (`Book`, `PricePoint`) ensuring data integrity before persistence.
- **`book_scraper.parser`**: Pure, deterministic HTML parsing functions (`parse_listing`, `parse_detail`, `parse_price`) using BeautifulSoup.
- **`book_scraper.storage`**: SQLite storage engine (`Store`) with an automatic migration runner (`schema_version`), atomic per-page commits, deduplicated imports, and data export facilities.
- **`book_scraper.alerts`**: Pluggable notification engine evaluating price drop thresholds and target price alerts across Console, Discord webhooks, and Telegram bots, with deduplication and dry-run support.
- **`book_scraper.reports`**: Snapshot diff analysis, aggregate statistics, and headless Matplotlib visualization charts.
- **`book_scraper.web`**: Lightweight FastAPI + Jinja2 dashboard serving overview metrics, searchable book tables, price charts, snapshot diffs, and watchlist tracking.
- **`book_scraper.cli` & `scrape.py`**: Rich CLI entry points (`book-scraper`, `python -m book_scraper`, `python scrape.py`).

---

## Install

Requires Python 3.10–3.13. Create and activate a virtual environment, then install dependencies:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# Core scraper dependencies:
python -m pip install -r requirements.txt
python -m pip install -e .

# Development & test tools:
python -m pip install -e ".[dev]"

# Web dashboard extra:
python -m pip install -e ".[web]"
```

---

## Configuration (`book-scraper.toml`)

Default settings can be configured via `book-scraper.toml` in the working directory (or specified with `--config <file>`). CLI flags always override file values:

```toml
[scraper]
delay = 1.0
retries = 3
max_backoff = 60.0
no_cache = false
category = "Travel"

[database]
path = "book_data.db"

[export]
default_format = "csv"

[alerts]
discord_webhook_url = ""  # Or use DISCORD_WEBHOOK_URL env var
telegram_bot_token = ""   # Or use TELEGRAM_BOT_TOKEN env var
telegram_chat_id = ""     # Or use TELEGRAM_CHAT_ID env var
```

---

## Commands and Usage

### 1. Scrape
```sh
# Normal crawl: follows pagination, stores in SQLite, exports book_data.csv snapshot
book-scraper scrape

# Filter by category with custom delay and page limits
book-scraper scrape --max-pages 5 --delay 1.0 --category Travel

# Bypass page cache, or customize HTTP retries and max backoff
book-scraper scrape --no-cache --retries 5 --max-backoff 30.0

# Quicker overview with listing data only
book-scraper scrape --no-details

# Dry run: previews crawl and writes CSV without saving to database
book-scraper scrape --dry-run
```

*Example Output:*
```
2026-10-28 22:00:00 INFO Saved page 1 (20 books)
2026-10-28 22:00:02 INFO Saved page 2 (20 books)
2026-10-28 22:00:03 INFO Run summary: pages ok=2 failed=0, books=40, malformed=0, skipped=0
2026-10-28 22:00:03 INFO Scrape complete; CSV exported to book_data.csv
```

### 2. Watchlist and Price Alerts
Track books by UPC and trigger notifications when prices drop below a threshold or fall by a percentage:

```sh
# Add an alert when a book price drops to or below £20.00
book-scraper watch add --upc a897fe39b1053632 --below 20.00

# Add an alert when price drops by 15% or more
book-scraper watch add --upc a897fe39b1053632 --drop-percent 15

# View current watchlist
book-scraper watch list

# Remove a book from the watchlist
book-scraper watch remove --upc a897fe39b1053632
```

*Example Output (`watch list`):*
```
UPC                  Target Price   Drop %     Last Alerted   Created At
---------------------------------------------------------------------------
a897fe39b1053632     20.00          15.0%      -              2026-10-28T22:00:00
```

Notifications dispatch automatically after each scrape. Set notification endpoints via environment variables:
```sh
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="987654321"
```

### 3. Comprehensive Statistics
View summary stats, price distribution buckets, category breakdowns, and top price changes between runs:

```sh
book-scraper stats
```

*Example Output:*
```
======================= Price Tracker Statistics =======================
Books Tracked: 40 (In Stock: 38, Out of Stock: 2)
Price Range:   £10.00 to £58.00 (Average: £35.42)

Price Distribution:
  < £10           2 books ( 5.0%) █
  £10 - £20       8 books (20.0%) █████
  £20 - £30      10 books (25.0%) ██████
  £30 - £40      12 books (30.0%) ███████
  £40 - £50       6 books (15.0%) ███
  £50+            2 books ( 5.0%) █

Top Categories:
  Travel                   :   11 books
  Mystery                  :    8 books
  Fiction                  :    7 books

Largest Price Decreases (Between Runs):
  ↓ A Light in the Attic                     £51.77 -> £45.00 (-£6.77, -13.1%)
========================================================================
```

### 4. Charts
Generate per-book price histories or aggregate visualizations:

```sh
# Per-book price history chart
book-scraper chart --upc a897fe39b1053632 --output history.png

# Aggregate charts:
book-scraper chart --kind category-avg     # Top categories by average price
book-scraper chart --kind rating-vs-price  # Star rating vs average price
book-scraper chart --kind price-changes    # Top price increases and drops
book-scraper chart --kind stock            # In stock vs Out of stock breakdown
```

### 5. Snapshot Changes
Compare differences between the most recent two crawl runs:

```sh
book-scraper changes
```

### 6. Filtered Exports
Export current database state to CSV, JSON, or Excel format with custom filters:

```sh
book-scraper export --format csv --category Travel --max-price 25.00
book-scraper export --format json --rating 5 --in-stock
book-scraper export --format xlsx --output books.xlsx
```

### 7. Legacy CSV Import
Load existing historical CSV files into the SQLite database without generating duplicate price points:

```sh
book-scraper import-csv legacy_book_data.csv
```

### 8. Web Dashboard
Start the local read-only web dashboard powered by FastAPI and Jinja2:

```sh
book-scraper serve --port 8000
```
Open `http://127.0.0.1:8000` in your browser to view:
- **Overview**: Crawl status, total counts, and summary metrics.
- **Books**: Searchable, filterable table with links to individual price histories.
- **Book Details**: Full specifications, historical price snapshots, and history charts.
- **Changes**: Inventory and price changes between runs.
- **Watchlist**: Real-time status of monitored items.

---

## Docker Usage

A lightweight Dockerfile based on `python:3.12-slim` runs the scraper securely as a non-root user (`appuser`) with a mounted volume for data persistence:

```sh
# Build image
docker build -t book-price-tracker .

# Run scrape with volume mounted at /data
docker run --rm -v $(pwd)/data:/data book-price-tracker --db /data/book_data.db scrape --max-pages 5

# Start web dashboard on port 8000
docker run -d --name book-tracker -p 8000:8000 -v $(pwd)/data:/data book-price-tracker --db /data/book_data.db serve --host 0.0.0.0 --port 8000
```

---

## Scheduling and Database Backups

Scheduled scraping is intentionally kept out of repository CI workflows to avoid repository bloat and credential exposure. Use standard OS schedulers locally:

### Linux / macOS (cron)
Run the scraper daily at 02:00 UTC and save logs:
```sh
crontab -e
```
Add the entry:
```cron
0 2 * * * cd /home/user/book_price_scraper && /home/user/book_price_scraper/.venv/bin/book-scraper --db /home/user/book_price_scraper/data/book_data.db scrape --log-file /home/user/book_price_scraper/data/cron.log
```

### Windows (Task Scheduler)
Use PowerShell to create a daily scheduled task:
```powershell
$Action = New-ScheduledTaskAction -Execute "C:\Users\Username\book_price_scraper\.venv\Scripts\book-scraper.exe" -Argument "scrape --log-file C:\Users\Username\book_price_scraper\data\scrape.log" -WorkingDirectory "C:\Users\Username\book_price_scraper"
$Trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
Register-ScheduledTask -TaskName "BookPriceScraperDaily" -Action $Action -Trigger $Trigger -Description "Daily run of Book Price Scraper"
```

### Database Backups
SQLite databases can be backed up safely while running using SQLite's online backup API or CLI command:
```sh
# Safe online backup
sqlite3 book_data.db ".backup 'backups/book_data_$(date +%Y%m%d_%H%M%S).db'"

# On Windows PowerShell:
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
sqlite3.exe book_data.db ".backup 'backups/book_data_$timestamp.db'"
```

---

## Tests and Quality Tools

All test suites are fully offline (using saved HTML fixtures, mocked HTTP, and in-memory or temporary SQLite databases):

```sh
# Run tests with coverage threshold (minimum 80% enforced)
pytest --cov=book_scraper --cov-report=term-missing --cov-fail-under=80

# Check formatting and linting
ruff check .
ruff format --check .

# Type checking
mypy book_scraper
```

Pre-commit hooks are configured in `.pre-commit-config.yaml` to run Ruff and mypy automatically before commits:
```sh
pre-commit install
```

---

## Current Scope

This tool is designed to crawl the [Books to Scrape](https://books.toscrape.com/) sandbox site. It includes complete price history tracking, conditional request caching, price drop alerts (Console, Discord, Telegram), aggregate and individual charts, filtered data exports, legacy CSV migration, and an interactive web dashboard. Before scraping any other site, review its `robots.txt`, terms of service, and rate limits.
