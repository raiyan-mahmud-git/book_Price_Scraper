FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser \
    && mkdir -p /data && chown -R appuser:appuser /data /app

COPY pyproject.toml requirements.txt /app/
COPY book_scraper/ /app/book_scraper/
COPY book-scraper.toml scrape.py README.md /app/

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e ".[web]"

RUN chown -R appuser:appuser /app

VOLUME ["/data"]

USER appuser

EXPOSE 8000

ENTRYPOINT ["book-scraper"]
CMD ["--db", "/data/book_data.db", "serve", "--host", "0.0.0.0", "--port", "8000"]
