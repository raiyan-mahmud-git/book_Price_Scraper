"""HTTP client with honest identification, robots checks, timeout and retries."""
import logging
import random
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

LOG = logging.getLogger(__name__)


class SiteClient:
    def __init__(self, delay: float = 1.0, timeout: tuple[float, float] = (5, 20), retries: int = 3):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BookPriceTracker/1.0 (educational scraper; contact: student@example.invalid)"})
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self._last_request = 0.0
        self._robots: RobotFileParser | None = None

    def _check_robots(self, url: str) -> None:
        if self._robots is None:
            base = f"{urlparse(url).scheme}://{urlparse(url).netloc}/robots.txt"
            response = self.session.get(base, timeout=self.timeout)
            response.encoding = "utf-8"
            parser = RobotFileParser(); parser.set_url(base); parser.parse(response.text.splitlines())
            self._robots = parser
        if not self._robots.can_fetch(self.session.headers["User-Agent"], url):
            raise RuntimeError(f"robots.txt disallows crawling {url}")

    def get(self, url: str) -> str:
        self._check_robots(url)
        for attempt in range(self.retries + 1):
            wait = self.delay + random.uniform(0, min(0.25, self.delay / 4)) - (time.monotonic() - self._last_request)
            if wait > 0: time.sleep(wait)
            try:
                response = self.session.get(url, timeout=self.timeout)
                self._last_request = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                response.encoding = "utf-8"
                return response.text
            except (requests.RequestException, requests.Timeout) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Could not fetch {url} after {self.retries + 1} attempts: {exc}") from exc
                pause = 0.5 * (2 ** attempt)
                LOG.warning("Fetch failed for %s; retrying in %.1fs", url, pause)
                time.sleep(pause)
        raise RuntimeError(f"Could not fetch {url}")
