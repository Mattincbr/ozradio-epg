"""Scraper for ABC Australia radio station EPG pages.

Supports URLs of the form:
    https://www.abc.net.au/{city}/station-epg
    https://www.abc.net.au/radio/brisbane/programs (alternative path)

The ABC site renders EPG data in two ways depending on the page:
  1. Embedded JSON in a <script id="__NEXT_DATA__"> tag (Next.js SSR)
  2. An undocumented JSON API endpoint that the page XHRs

We try the API endpoint first, then fall back to parsing __NEXT_DATA__,
and finally fall back to HTML parsing.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from ..models import DaySchedule, TimeSlot, WeeklySchedule
from .base import BaseScraper, ScraperError


# ABC internal API used by the EPG page
_ABC_API = "https://www.abc.net.au/api/public/programmes/station/{station_id}"
_STATION_TIMEZONE: dict[str, str] = {
    "brisbane":   "Australia/Brisbane",
    "sydney":     "Australia/Sydney",
    "melbourne":  "Australia/Melbourne",
    "perth":      "Australia/Perth",
    "adelaide":   "Australia/Adelaide",
    "hobart":     "Australia/Hobart",
    "darwin":     "Australia/Darwin",
    "canberra":   "Australia/Sydney",
    "newcastle":  "Australia/Sydney",
    "wollongong": "Australia/Sydney",
    "goldcoast":  "Australia/Brisbane",
    "sunshine":   "Australia/Brisbane",
    "tropical":   "Australia/Brisbane",
    "northwest":  "Australia/Perth",
    "great":      "Australia/Perth",
    "ballarat":   "Australia/Melbourne",
    "bendigo":    "Australia/Melbourne",
    "gippsland":  "Australia/Melbourne",
    "shepparton": "Australia/Melbourne",
}

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class ABCScraper(BaseScraper):
    """Scraper for ABC Australia radio station EPG pages."""

    def scrape(self, url: str) -> WeeklySchedule:
        """Scrape an ABC station EPG page and return a WeeklySchedule.

        Tries three strategies in order:
          1. ABC internal JSON API
          2. __NEXT_DATA__ embedded JSON
          3. Raw HTML table parsing
        """
        station_slug = _extract_station_slug(url)
        timezone = _STATION_TIMEZONE.get(station_slug.lower(), "Australia/Sydney")

        for strategy in (self._try_api, self._try_next_data, self._try_html):
            try:
                result = strategy(url, station_slug, timezone)
                if result is not None:
                    return result
            except ScraperError:
                raise
            except Exception:
                continue

        raise ScraperError(f"All scraping strategies failed for {url}")

    # ------------------------------------------------------------------
    # Strategy 1: undocumented JSON API
    # ------------------------------------------------------------------

    def _try_api(self, url: str, slug: str, timezone: str) -> Optional[WeeklySchedule]:
        station_id = _slug_to_station_id(slug)
        api_url = _ABC_API.format(station_id=station_id)

        resp = self.fetch(api_url, headers={"Accept": "application/json"})
        data = resp.json()
        return _parse_api_response(data, slug, timezone, source_url=url)

    # ------------------------------------------------------------------
    # Strategy 2: Next.js __NEXT_DATA__
    # ------------------------------------------------------------------

    def _try_next_data(self, url: str, slug: str, timezone: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return None

        data = json.loads(script.string)
        # Navigate into the page props — the path varies by ABC page version
        programmes = _dig(data, "props", "pageProps", "programs") or \
                     _dig(data, "props", "pageProps", "schedule") or \
                     _dig(data, "props", "pageProps", "data", "programs")

        if not programmes:
            return None

        return _parse_programme_list(programmes, slug, timezone, source_url=url)

    # ------------------------------------------------------------------
    # Strategy 3: HTML parsing
    # ------------------------------------------------------------------

    def _try_html(self, url: str, slug: str, timezone: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)

        # The ABC EPG page typically uses a tabbed/sectioned layout.
        # Each day is labelled with a heading and a list of programme blocks.
        days: dict[str, DaySchedule] = {}

        # Look for day-labelled sections (h2/h3 containing a day name, or
        # elements with data-day attributes)
        for day_name in _DAY_NAMES:
            slots = _scrape_day_slots(soup, day_name)
            if slots:
                days[day_name] = DaySchedule(slots=slots)

        # If we found no day-specific data, try reading a flat programme list
        # and assume it represents a single weekday schedule
        if not days:
            flat = _scrape_flat_slots(soup)
            if flat:
                days["weekdays"] = DaySchedule(slots=flat)

        if not days:
            return None

        # Collapse Monday–Friday into "weekdays" if they're identical
        days = _collapse_weekdays(days)

        station_name = _slug_to_display_name(slug)
        return WeeklySchedule(
            channel_id=f"abc.{slug}",
            channel_name=station_name,
            timezone=timezone,
            source_url=url,
            days=days,
        )


# ---------------------------------------------------------------------------
# Helpers — API / Next.js response parsing
# ---------------------------------------------------------------------------

def _parse_api_response(
    data: dict,
    slug: str,
    timezone: str,
    source_url: str,
) -> Optional[WeeklySchedule]:
    items = data.get("items") or data.get("programs") or []
    if not items:
        return None
    return _parse_programme_list(items, slug, timezone, source_url)


def _parse_programme_list(
    items: list,
    slug: str,
    timezone: str,
    source_url: str,
) -> WeeklySchedule:
    """Build a WeeklySchedule from a flat list of programme dicts.

    ABC programme dicts typically contain keys like:
      - title / programName / name
      - startTime / start / broadcastDateTime
      - endTime / end
      - synopsis / description / shortSynopsis
      - presenter / presenterName
    """
    day_slots: dict[str, list[TimeSlot]] = {d: [] for d in _DAY_NAMES}

    for item in items:
        title = (
            item.get("title") or item.get("programName") or item.get("name") or ""
        ).strip()
        if not title:
            continue

        raw_start = item.get("startTime") or item.get("start") or item.get("broadcastDateTime", "")
        if not raw_start:
            continue

        # Parse ISO 8601 datetime to extract weekday and HH:MM
        try:
            dt = _parse_iso(str(raw_start))
        except ValueError:
            continue

        day_name = _DAY_NAMES[dt.weekday()]

        raw_end = item.get("endTime") or item.get("end") or ""
        duration: Optional[int] = None
        if raw_end:
            try:
                end_dt = _parse_iso(str(raw_end))
                duration = int((end_dt - dt).total_seconds() // 60)
            except ValueError:
                pass

        synopsis = (
            item.get("synopsis") or item.get("description") or item.get("shortSynopsis") or ""
        ).strip()
        presenter = (item.get("presenter") or item.get("presenterName") or "").strip()

        slot = TimeSlot(
            start=dt.strftime("%H:%M"),
            title=title,
            description=synopsis,
            presenter=presenter,
            duration=duration,
        )
        day_slots[day_name].append(slot)

    # Sort slots by start time within each day
    for name, slots in day_slots.items():
        slots.sort(key=lambda s: s.start)

    days = {
        name: DaySchedule(slots=slots)
        for name, slots in day_slots.items()
        if slots
    }
    days = _collapse_weekdays(days)

    return WeeklySchedule(
        channel_id=f"abc.{slug}",
        channel_name=_slug_to_display_name(slug),
        timezone=timezone,
        source_url=source_url,
        days=days,
    )


# ---------------------------------------------------------------------------
# Helpers — HTML parsing
# ---------------------------------------------------------------------------

def _scrape_day_slots(soup, day_name: str) -> list[TimeSlot]:
    """Find slots for a specific day in the BeautifulSoup tree."""
    slots: list[TimeSlot] = []

    # Try data-day attributes
    section = soup.find(attrs={"data-day": day_name}) or \
              soup.find(attrs={"data-day": day_name.capitalize()})

    if not section:
        # Try heading that contains the day name
        heading = soup.find(
            re.compile(r"^h[2-4]$"),
            string=re.compile(day_name, re.I)
        )
        if heading:
            # Collect sibling/child programme items until the next heading
            section = heading.find_next_sibling()

    if not section:
        return slots

    for item in section.find_all(class_=re.compile(r"program|schedule|slot", re.I)):
        slot = _parse_programme_item(item)
        if slot:
            slots.append(slot)

    return slots


def _scrape_flat_slots(soup) -> list[TimeSlot]:
    """Last-resort: collect all programme-like elements from the page."""
    slots = []
    for item in soup.find_all(class_=re.compile(r"program|schedule-item|programme", re.I)):
        slot = _parse_programme_item(item)
        if slot:
            slots.append(slot)
    return slots


def _parse_programme_item(el) -> Optional[TimeSlot]:
    """Extract a TimeSlot from a single programme HTML element."""
    # Time
    time_el = el.find(class_=re.compile(r"time|start", re.I)) or \
              el.find("time")
    if not time_el:
        return None
    time_text = (time_el.get("datetime") or time_el.get_text()).strip()
    time_str = _normalise_time(time_text)
    if not time_str:
        return None

    # Title
    title_el = el.find(class_=re.compile(r"title|name|heading", re.I)) or \
               el.find(re.compile(r"^h[2-6]$"))
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title:
        return None

    # Description
    desc_el = el.find(class_=re.compile(r"desc|synopsis|summary", re.I)) or \
              el.find("p")
    description = desc_el.get_text(strip=True) if desc_el else ""

    # Presenter
    presenter_el = el.find(class_=re.compile(r"presenter|host|talent", re.I))
    presenter = presenter_el.get_text(strip=True) if presenter_el else ""

    return TimeSlot(
        start=time_str,
        title=title,
        description=description,
        presenter=presenter,
    )


_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _normalise_time(raw: str) -> str:
    """Return "HH:MM" from various time string formats, or empty string."""
    m = _TIME_RE.search(raw)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


# ---------------------------------------------------------------------------
# Helpers — misc
# ---------------------------------------------------------------------------

def _extract_station_slug(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    # abc.net.au/{slug}/station-epg  or  abc.net.au/radio/{slug}/...
    if parts and parts[0] == "radio" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else "unknown"


def _slug_to_station_id(slug: str) -> str:
    # ABC internal IDs tend to be numeric; we expose the slug as-is for the API
    # path and let the server resolve it.  Known slugs match URL paths directly.
    return slug


def _slug_to_display_name(slug: str) -> str:
    return "ABC " + slug.replace("-", " ").title()


def _collapse_weekdays(days: dict[str, DaySchedule]) -> dict[str, DaySchedule]:
    """Replace Monday-Friday entries with a single 'weekdays' key if they match."""
    weekday_keys = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    present = [k for k in weekday_keys if k in days]

    if len(present) < 2:
        return days

    # Compare slot lists by title+start — if identical across all present weekdays
    def key_slots(sched: DaySchedule):
        return [(s.start, s.title) for s in sched.slots]

    reference = key_slots(days[present[0]])
    if all(key_slots(days[k]) == reference for k in present[1:]):
        collapsed = {k: v for k, v in days.items() if k not in weekday_keys}
        collapsed["weekdays"] = days[present[0]]
        return collapsed

    return days


def _dig(obj, *keys):
    """Safely navigate nested dicts/lists."""
    for k in keys:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(k)
        else:
            return None
    return obj


def _parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 datetime string."""
    # Python 3.11 handles most ISO 8601 variants natively
    s = s.rstrip("Z")
    if "+" not in s and len(s) > 10:
        s += "+00:00"
    return datetime.fromisoformat(s)
