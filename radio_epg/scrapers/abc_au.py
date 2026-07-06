"""Scraper for ABC Australia radio station EPG pages.

Supports URLs of the form:
    https://www.abc.net.au/{city}/station-epg
    https://www.abc.net.au/radio/{city}/programs

Tries multiple strategies in order:
  1. ABC internal JSON API (several known endpoint variants)
  2. __NEXT_DATA__ embedded JSON (recursive search)
  3. Raw HTML parsing
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from ..models import DaySchedule, TimeSlot, WeeklySchedule
from .base import BaseScraper, ScraperError


_ABC_API_PATTERNS = [
    "https://www.abc.net.au/api/public/programmes/station/{slug}",
    "https://www.abc.net.au/api/radio/schedule/{slug}",
    "https://www.abc.net.au/radio/{slug}/programs.json",
]

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

# Keys in a programme object that likely hold a start time
_START_KEYS = ("startTime", "start", "broadcastDateTime", "broadcast_time", "air_time",
               "scheduledStart", "scheduled_start", "timeFrom", "time_from")
_TITLE_KEYS = ("title", "programName", "name", "program_name", "programTitle", "program_title")
_END_KEYS   = ("endTime", "end", "scheduledEnd", "scheduled_end", "timeTo", "time_to")
_DESC_KEYS  = ("synopsis", "description", "shortSynopsis", "short_synopsis", "summary", "body")
_HOST_KEYS  = ("presenter", "presenterName", "host", "talent", "presenter_name")


class ABCScraper(BaseScraper):
    """Scraper for ABC Australia radio station EPG pages."""

    def scrape(self, url: str) -> WeeklySchedule:
        station_slug = _extract_station_slug(url)
        timezone = _STATION_TIMEZONE.get(station_slug.lower(), "Australia/Sydney")

        # Normalise URL: old station-epg URLs → new /radio/{slug}/programs
        normalised_url = _normalise_abc_url(url, station_slug)

        errors: list[str] = []

        for strategy in (self._try_api, self._try_next_data, self._try_html):
            try:
                result = strategy(normalised_url, station_slug, timezone)
                if result is not None and result.days:
                    return result
            except Exception as exc:
                errors.append(f"{strategy.__name__}: {exc}")
                continue

        raise ScraperError(
            f"All scraping strategies failed for {url}. Tried: "
            + " | ".join(errors) if errors else f"No schedule data found at {url}"
        )

    # ------------------------------------------------------------------
    # Strategy 1: undocumented JSON API (try several known endpoint forms)
    # ------------------------------------------------------------------

    def _try_api(self, url: str, slug: str, timezone: str) -> Optional[WeeklySchedule]:
        for pattern in _ABC_API_PATTERNS:
            api_url = pattern.format(slug=slug)
            try:
                resp = self.fetch(api_url, headers={"Accept": "application/json"})
                data = resp.json()
                result = _parse_api_response(data, slug, timezone, source_url=url)
                if result is not None:
                    return result
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Strategy 2: Next.js __NEXT_DATA__ (recursive search)
    # ------------------------------------------------------------------

    def _try_next_data(self, url: str, slug: str, timezone: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None

        # Recursively search the entire __NEXT_DATA__ object for any array
        # that looks like a list of programme dicts
        programmes = _find_programme_list(data)
        if not programmes:
            return None

        return _parse_programme_list(programmes, slug, timezone, source_url=url)

    # ------------------------------------------------------------------
    # Strategy 3: HTML parsing
    # ------------------------------------------------------------------

    def _try_html(self, url: str, slug: str, timezone: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)

        # Also look for any <script type="application/json"> blocks
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                programmes = _find_programme_list(data)
                if programmes:
                    result = _parse_programme_list(programmes, slug, timezone, source_url=url)
                    if result and result.days:
                        return result
            except Exception:
                continue

        days: dict[str, DaySchedule] = {}

        for day_name in _DAY_NAMES:
            slots = _scrape_day_slots(soup, day_name)
            if slots:
                days[day_name] = DaySchedule(slots=slots)

        if not days:
            flat = _scrape_flat_slots(soup)
            if flat:
                days["weekdays"] = DaySchedule(slots=flat)

        if not days:
            return None

        days = _collapse_weekdays(days)
        return WeeklySchedule(
            channel_id=f"abc.{slug}",
            channel_name=_slug_to_display_name(slug),
            timezone=timezone,
            source_url=url,
            days=days,
        )


# ---------------------------------------------------------------------------
# API / JSON response parsing
# ---------------------------------------------------------------------------

def _parse_api_response(data, slug: str, timezone: str, source_url: str) -> Optional[WeeklySchedule]:
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (
            data.get("items") or data.get("programs") or data.get("schedule") or
            data.get("data") or []
        )
        if isinstance(items, dict):
            # data.get("data") might be a nested dict
            items = _find_programme_list(items) or []
    else:
        return None

    if not items:
        return None
    return _parse_programme_list(items, slug, timezone, source_url)


def _parse_programme_list(items: list, slug: str, timezone: str, source_url: str) -> WeeklySchedule:
    day_slots: dict[str, list[TimeSlot]] = {d: [] for d in _DAY_NAMES}

    for item in items:
        if not isinstance(item, dict):
            continue

        title = _first(item, _TITLE_KEYS, "").strip()
        if not title:
            continue

        raw_start = _first(item, _START_KEYS, "")
        if not raw_start:
            continue

        try:
            dt = _parse_iso(str(raw_start))
        except ValueError:
            continue

        day_name = _DAY_NAMES[dt.weekday()]

        raw_end = _first(item, _END_KEYS, "")
        duration: Optional[int] = None
        if raw_end:
            try:
                end_dt = _parse_iso(str(raw_end))
                diff = int((end_dt - dt).total_seconds())
                if diff > 0:
                    duration = diff // 60
            except ValueError:
                pass

        synopsis = _first(item, _DESC_KEYS, "").strip()
        presenter = _first(item, _HOST_KEYS, "").strip()

        slot = TimeSlot(
            start=dt.strftime("%H:%M"),
            title=title,
            description=synopsis,
            presenter=presenter,
            duration=duration,
        )
        day_slots[day_name].append(slot)

    for slots in day_slots.values():
        slots.sort(key=lambda s: s.start)

    days = {name: DaySchedule(slots=slots) for name, slots in day_slots.items() if slots}
    days = _collapse_weekdays(days)

    return WeeklySchedule(
        channel_id=f"abc.{slug}",
        channel_name=_slug_to_display_name(slug),
        timezone=timezone,
        source_url=source_url,
        days=days,
    )


# ---------------------------------------------------------------------------
# Recursive programme-list finder
# ---------------------------------------------------------------------------

def _find_programme_list(obj, _depth: int = 0) -> Optional[list]:
    """Recursively search *obj* for an array that looks like programme dicts."""
    if _depth > 8:
        return None
    if isinstance(obj, list):
        if _looks_like_programmes(obj):
            return obj
        # Try each list element that is itself a dict/list
        for item in obj[:5]:
            result = _find_programme_list(item, _depth + 1)
            if result:
                return result
    elif isinstance(obj, dict):
        # Prefer known key names
        for key in ("programs", "programme", "schedule", "schedules", "items",
                    "slots", "shows", "broadcasts", "episodes"):
            val = obj.get(key)
            if isinstance(val, list) and _looks_like_programmes(val):
                return val
        # Recurse into all values
        for val in obj.values():
            if isinstance(val, (dict, list)):
                result = _find_programme_list(val, _depth + 1)
                if result:
                    return result
    return None


def _looks_like_programmes(lst: list) -> bool:
    """Heuristic: is this list likely a list of programme dicts?"""
    if len(lst) < 2:
        return False
    sample = lst[:3]
    hits = 0
    for item in sample:
        if not isinstance(item, dict):
            return False
        has_title = any(k in item for k in _TITLE_KEYS)
        has_time = any(k in item for k in _START_KEYS)
        if has_title and has_time:
            hits += 1
    return hits >= 1


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _scrape_day_slots(soup, day_name: str) -> list[TimeSlot]:
    slots: list[TimeSlot] = []

    section = (
        soup.find(attrs={"data-day": day_name}) or
        soup.find(attrs={"data-day": day_name.capitalize()}) or
        soup.find(attrs={"data-weekday": day_name})
    )

    if not section:
        heading = soup.find(re.compile(r"^h[2-4]$"), string=re.compile(day_name, re.I))
        if heading:
            section = heading.find_next_sibling()

    if not section:
        return slots

    for item in section.find_all(class_=re.compile(r"program|schedule|slot|broadcast", re.I)):
        slot = _parse_programme_item(item)
        if slot:
            slots.append(slot)

    return slots


def _scrape_flat_slots(soup) -> list[TimeSlot]:
    slots = []
    for item in soup.find_all(class_=re.compile(r"program|schedule-item|programme|broadcast", re.I)):
        slot = _parse_programme_item(item)
        if slot:
            slots.append(slot)
    return slots


def _parse_programme_item(el) -> Optional[TimeSlot]:
    time_el = (
        el.find(class_=re.compile(r"time|start", re.I)) or
        el.find("time")
    )
    if not time_el:
        return None
    time_text = (time_el.get("datetime") or time_el.get_text()).strip()
    time_str = _normalise_time(time_text)
    if not time_str:
        return None

    title_el = (
        el.find(class_=re.compile(r"title|name|heading", re.I)) or
        el.find(re.compile(r"^h[2-6]$"))
    )
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title:
        return None

    desc_el = el.find(class_=re.compile(r"desc|synopsis|summary", re.I)) or el.find("p")
    description = desc_el.get_text(strip=True) if desc_el else ""

    presenter_el = el.find(class_=re.compile(r"presenter|host|talent", re.I))
    presenter = presenter_el.get_text(strip=True) if presenter_el else ""

    return TimeSlot(start=time_str, title=title, description=description, presenter=presenter)


_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _normalise_time(raw: str) -> str:
    m = _TIME_RE.search(raw)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _extract_station_slug(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    # /radio/{slug}/...  or  /{slug}/station-epg
    if parts and parts[0] == "radio" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else "unknown"


def _normalise_abc_url(url: str, slug: str) -> str:
    """Rewrite old station-epg URLs to the current /radio/{slug}/programs form."""
    if "station-epg" in url:
        return f"https://www.abc.net.au/radio/{slug}/programs"
    return url


def _slug_to_display_name(slug: str) -> str:
    return "ABC " + slug.replace("-", " ").title()


def _collapse_weekdays(days: dict[str, DaySchedule]) -> dict[str, DaySchedule]:
    weekday_keys = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    present = [k for k in weekday_keys if k in days]
    if len(present) < 2:
        return days

    def key_slots(sched: DaySchedule):
        return [(s.start, s.title) for s in sched.slots]

    reference = key_slots(days[present[0]])
    if all(key_slots(days[k]) == reference for k in present[1:]):
        collapsed = {k: v for k, v in days.items() if k not in weekday_keys}
        collapsed["weekdays"] = days[present[0]]
        return collapsed
    return days


def _first(d: dict, keys: tuple, default="") -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return default


def _parse_iso(s: str) -> datetime:
    """Parse ISO 8601 datetime, compatible with Python 3.10."""
    s = s.strip()

    # Normalise Z suffix
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # Truncate fractional seconds to 6 digits (Python 3.10 fromisoformat limit)
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)

    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    # Try common strptime formats as last resort
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse datetime: {s!r}")


def _dig(obj, *keys):
    for k in keys:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(k)
        else:
            return None
    return obj
