"""Abstract base class for station schedule scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import requests
from bs4 import BeautifulSoup

from ..models import WeeklySchedule


class ScraperError(Exception):
    """Raised when a scraper cannot retrieve or parse a schedule."""


class BaseScraper(ABC):
    """Base class for all station schedule scrapers."""

    DEFAULT_TIMEOUT = 30
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.5",
    }

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.DEFAULT_HEADERS)

    def fetch(self, url: str, **kwargs) -> requests.Response:
        try:
            resp = self._session.get(url, timeout=self.DEFAULT_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            raise ScraperError(f"Failed to fetch {url}: {exc}") from exc

    def fetch_soup(self, url: str, **kwargs) -> BeautifulSoup:
        resp = self.fetch(url, **kwargs)
        return BeautifulSoup(resp.text, "lxml")

    @abstractmethod
    def scrape(self, url: str) -> WeeklySchedule:
        """Scrape *url* and return a WeeklySchedule."""
