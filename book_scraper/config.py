"""Configuration file loading and parsing with tomllib/tomli."""

import logging
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

LOG = logging.getLogger(__name__)
DEFAULT_CONFIG_FILE = "book-scraper.toml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from TOML file if it exists, otherwise return empty dict."""
    config_path = Path(path) if path else Path(DEFAULT_CONFIG_FILE)
    if not config_path.is_file():
        return {}
    try:
        with config_path.open("rb") as f:
            return tomllib.load(f)
    except Exception as exc:
        LOG.warning("Could not read configuration from %s: %s", config_path, exc)
        return {}
