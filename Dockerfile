FROM python:3.12-slim

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if needed and create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser \
    && mkdir -p /data && chown -R appuser:appuser /data /app

# Copy dependency specifications first for caching
COPY pyproject.toml requirements.txt /app/

# Install dependencies including web dashboard extra
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e ".[web]"

# Copy source code
COPY book_scraper/ /app/book_scraper/
COPY book-scraper.toml scrape.py README.md /app/

RUN chown -R appuser:appuser /app

VOLUME ["/data"]

USER appuser

EXPOSE 8000

ENTRYPOINT ["book-scraper"]
CMD ["--help"]
