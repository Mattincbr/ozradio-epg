"""Generic schedule scraper — works on any website.

Tries, in order:
  1. __NEXT_DATA__ embedded JSON (Next.js SSR pages)
  2. <script type="application/json"> blocks
  3. Visible page text → text_parser heuristics
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..models import DaySchedule, TimeSlot, WeeklySchedule
from .abc_au import _find_programme_list, _parse_programme_list
from .base import BaseScraper, ScraperError
from .text_parser import parse_schedule_text


class GenericScraper(BaseScraper):
    """Best-effort schedule scraper for arbitrary station websites."""

    def scrape(self, url: str) -> WeeklySchedule:
        errors: list[str] = []
        for strategy in (self._try_next_data, self._try_json_scripts, self._try_text):
            try:
                result = strategy(url)
                if result is not None and result.days:
                    return result
            except Exception as exc:
                errors.append(f"{strategy.__name__}: {exc}")
                continue

        raise ScraperError(
            "Could not extract schedule data from that URL. "
            + (" | ".join(errors) if errors else "No schedule data found.")
        )

    def _try_next_data(self, url: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None
        programmes = _find_programme_list(data)
        if not programmes:
            return None
        slug = _slug_from_url(url)
        return _parse_programme_list(programmes, slug, "UTC", source_url=url)

    def _try_json_scripts(self, url: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                programmes = _find_programme_list(data)
                if programmes:
                    slug = _slug_from_url(url)
                    result = _parse_programme_list(programmes, slug, "UTC", source_url=url)
                    if result and result.days:
                        return result
            except Exception:
                continue
        return None

    def _try_text(self, url: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)
        # Remove nav/footer/script noise before extracting text
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        days_dict = parse_schedule_text(text)
        if not days_dict:
            return None

        slug = _slug_from_url(url)
        days = {
            day: DaySchedule(slots=[
                TimeSlot(
                    start=s["start"],
                    title=s["title"],
                    description=s.get("description", ""),
                    presenter=s.get("presenter", ""),
                )
                for s in slots
            ])
            for day, slots in days_dict.items()
        }

        return WeeklySchedule(
            channel_id=slug,
            channel_name=slug.replace("-", " ").title(),
            timezone="UTC",
            source_url=url,
            days=days,
        )


def _slug_from_url(url: str) -> str:
    from urllib.parse import urlparse
    parts = urlparse(url)
    path_parts = [p for p in parts.path.strip("/").split("/") if p]
    return path_parts[-1] if path_parts else parts.netloc.split(".")[0]
