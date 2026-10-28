"""HTTP client with honest identification, robots checks, timeout, retries, and caching."""

import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from .cache import HttpCache

LOG = logging.getLogger(__name__)


def parse_retry_after(header_val: str | None) -> float | None:
    """Parse a Retry-After header value in seconds or HTTP-date format."""
    if not header_val:
        return None
    try:
        return max(0.0, float(header_val))
    except (ValueError, TypeError):
        pass
    try:
        dt = parsedate_to_datetime(header_val)
        delta = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


class SiteClient:
    def __init__(
        self,
        delay: float = 1.0,
        timeout: tuple[float, float] = (5, 20),
        retries: int = 3,
        max_backoff: float = 60.0,
        backoff_factor: float = 0.5,
        cache: HttpCache | None = None,
        no_cache: bool = False,
    ):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "BookPriceTracker/1.0 (educational scraper; contact: student@example.invalid)"}
        )
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.max_backoff = max_backoff
        self.backoff_factor = backoff_factor
        self.cache = cache if cache is not None else (None if no_cache else HttpCache())
        self.no_cache = no_cache
        self._last_request = 0.0
        self._robots: RobotFileParser | None = None

    def _check_robots(self, url: str) -> None:
        if self._robots is None:
            base = f"{urlparse(url).scheme}://{urlparse(url).netloc}/robots.txt"
            response = self.session.get(base, timeout=self.timeout)
            response.encoding = "utf-8"
            parser = RobotFileParser()
            parser.set_url(base)
            parser.parse(response.text.splitlines())
            self._robots = parser
        user_agent = str(self.session.headers.get("User-Agent", ""))
        if not self._robots.can_fetch(user_agent, url):
            raise RuntimeError(f"robots.txt disallows crawling {url}")

    def get(self, url: str) -> str:
        self._check_robots(url)
        cached_content: str | None = None
        etag: str | None = None
        last_modified: str | None = None

        if not self.no_cache and self.cache:
            cached_content, etag, last_modified = self.cache.get(url)

        headers: dict[str, str] = {}
        if cached_content is not None:
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

        for attempt in range(self.retries + 1):
            wait = self.delay + random.uniform(0, min(0.25, self.delay / 4)) - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                if headers:
                    response = self.session.get(url, headers=headers, timeout=self.timeout)
                else:
                    response = self.session.get(url, timeout=self.timeout)
                self._last_request = time.monotonic()

                resp_headers = getattr(response, "headers", {})

                # 304 Not Modified
                if response.status_code == 304 and cached_content is not None:
                    LOG.debug("Cached page unchanged (304): %s", url)
                    return cached_content

                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()

                response.raise_for_status()
                response.encoding = "utf-8"
                content = response.text

                if not self.no_cache and self.cache:
                    new_etag = resp_headers.get("ETag")
                    new_last_modified = resp_headers.get("Last-Modified")
                    self.cache.set(url, content, new_etag, new_last_modified)

                return content
            except (requests.RequestException, requests.Timeout) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Could not fetch {url} after {self.retries + 1} attempts: {exc}") from exc

                # Check Retry-After
                resp = getattr(exc, "response", None)
                r_headers = getattr(resp, "headers", {}) if resp else {}
                retry_after = parse_retry_after(r_headers.get("Retry-After"))

                if retry_after is not None:
                    pause = min(self.max_backoff, max(0.1, retry_after))
                else:
                    base = self.backoff_factor * (2**attempt)
                    jitter = random.uniform(0, min(0.5, base * 0.25))
                    pause = min(self.max_backoff, base + jitter)

                LOG.warning("Fetch failed for %s; retrying in %.2fs (%s)", url, pause, exc)
                time.sleep(pause)
        raise RuntimeError(f"Could not fetch {url}")
