# Changelog

All notable changes to the `book-price-tracker` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-10-28

### Added
- **HTTP Reliability**: Configurable retries with exponential backoff and random jitter for request timeouts, connection errors, and HTTP 429/5xx status codes.
- **Retry-After Header Support**: Automatically honors `Retry-After` header values in integer seconds or standard HTTP-date formats.
- **Conditional Requests & Page Caching**: Added SQLite-backed `HttpCache` for `ETag` and `Last-Modified` validation with HTTP 304 handling to avoid re-downloading unchanged pages. Added `--no-cache` CLI flag.
- **Data Validation & Malformed Row Handling**: Strict validation for `Book` dataclass models. Malformed rows during scraping are counted, logged, and skipped without saving corrupted data or halting crawling.
- **Database Schema Migration Runner**: Added automatic schema migration engine tracking versions via `schema_version` table. Automatically upgrades legacy unversioned databases without data loss.
- **TOML Configuration**: Added `book-scraper.toml` configuration support using standard library `tomllib` on Python 3.11+ and `tomli` on Python 3.10. CLI flags cleanly override config values.
- **Watchlist & Price Alerting**: Added `book-scraper watch add`, `watch list`, and `watch remove` commands stored in SQLite. Alerts evaluate against target price (`--below`) and percentage drops (`--drop-percent`).
- **Pluggable Alert Notifiers**: Dispatch price alerts through Console, Discord webhooks (`DISCORD_WEBHOOK_URL`), and Telegram bots (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- **Alert Deduplication & Dry-Run**: Prevents duplicate alerts for the same price point across runs. Added `--dry-run` to preview triggered alerts without sending notifications or modifying state.
- **Aggregate Charts**: Added `book-scraper chart --kind` supporting `category-avg`, `rating-vs-price`, `price-changes`, and `stock` alongside the existing per-book chart.
- **Legacy CSV Import**: Added `book-scraper import-csv <path>` to import historical `book_data.csv` snapshots into SQLite without creating duplicate records.
- **Comprehensive Statistics**: Enhanced `book-scraper stats` reporting price distribution buckets, category item counts, and top price increases/decreases between runs.
- **Web Dashboard**: Built a lightweight read-only dashboard with FastAPI and Jinja2 (`book-scraper serve --port 8000`). Features system overview, searchable/filterable books table, per-book price history charts, snapshot changes, and watchlist status.
- **Optional Web Extra**: Web dashboard dependencies packaged under `pip install -e ".[web]"`.
- **Docker Support**: Added production-ready `Dockerfile` (Python 3.12 slim, non-root user, `/data` volume) and `.dockerignore`.
- **Quality & CI Tooling**: Added `pytest-cov` with 80% coverage threshold enforcement, `.pre-commit-config.yaml` for Ruff and mypy, and GitHub Actions CI matrix for Python 3.10–3.13.

### Changed
- Refactored code formatting to adhere to standard line formatting and strict Ruff linting.
- Modernized type hints across `book_scraper` modules with full mypy strict compliance.

### Decisions & Compatibility Notes
- Maintained 100% backward compatibility with existing CLI commands, flags, database schema, and the `python scrape.py` entry point.
- Configured matplotlib to use the headless `Agg` backend to avoid native `Tcl/Tk` environment requirements in Docker, headless servers, and CI runners.
- Kept all test suites strictly offline without external network dependencies.
