"""Scraper for Nova Entertainment radio station websites.

Handles: Nova FM (novafm.com.au) and Smooth FM (smoothfm.com.au) stations.

URL format: https://novafm.com.au/station/{slug}
            https://smoothfm.com.au/station/{slug}

Schedules are typically rendered via Next.js or as embedded JSON.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urlparse

from ..models import DaySchedule, TimeSlot, WeeklySchedule
from .base import BaseScraper, ScraperError
from .text_parser import parse_schedule_text


# Map station URL slugs → timezone
_SLUG_TZ: dict[str, str] = {
    # Nova FM
    "nova969":        "Australia/Sydney",
    "nova96":         "Australia/Sydney",
    "nova100":        "Australia/Melbourne",
    "nova1069":       "Australia/Brisbane",
    "nova919":        "Australia/Adelaide",
    "nova961":        "Australia/Perth",
    "nova937":        "Australia/Perth",
    # Smooth FM
    "smooth953":      "Australia/Sydney",
    "smooth915":      "Australia/Melbourne",
    "smoothfmsydney": "Australia/Sydney",
    "smoothfmmelbourne": "Australia/Melbourne",
}

_SLUG_NAME: dict[str, str] = {
    "nova969":        "Nova 96.9",
    "nova96":         "Nova 96.9",
    "nova100":        "Nova 100",
    "nova1069":       "Nova 106.9",
    "nova919":        "Nova 91.9",
    "nova961":        "Nova 96.1",
    "nova937":        "Nova 93.7",
    "smooth953":      "Smooth FM 95.3",
    "smooth915":      "Smooth FM 91.5",
    "smoothfmsydney": "Smooth FM Sydney",
    "smoothfmmelbourne": "Smooth FM Melbourne",
}

_ALL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# "5:30am – 9am", "5:30am-9am", "9am – 12pm"
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?)\s*([aApP][mM])?\s*[-–—]\s*(\d{1,2}(?::\d{2})?)\s*([aApP][mM])",
    re.I,
)
_DAY_RE = re.compile(
    r"(weekdays?|monday[\s\-–](?:to[\s]+)?friday|mon[\s\-–]fri"
    r"|weekends?|saturday|sunday|monday|tuesday|wednesday|thursday|friday"
    r"|daily|every\s+day|mon|tue|wed|thu|fri|sat|sun)",
    re.I,
)


class NovaEntertainmentScraper(BaseScraper):
    """Scraper for Nova FM and Smooth FM websites."""

    def scrape(self, url: str) -> WeeklySchedule:
        slug = _station_slug(url)
        tz = _slug_to_tz(slug, url)
        name = _SLUG_NAME.get(slug, _slug_to_display(slug))

        errors: list[str] = []
        for strategy in (
            self._try_api,
            self._try_next_data,
            self._try_show_cards,
        ):
            try:
                result = strategy(url, slug, tz, name)
                if result is not None and result.days:
                    return result
            except Exception as exc:
                errors.append(f"{strategy.__name__}: {exc}")

        raise ScraperError(
            f"Could not extract schedule from {url}. "
            + (" | ".join(errors) if errors else "No schedule data found.")
        )

    # ------------------------------------------------------------------
    # Strategy 1: JSON API
    # ------------------------------------------------------------------

    def _try_api(self, url: str, slug: str, tz: str, name: str) -> Optional[WeeklySchedule]:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        for api_path in (
            f"/api/schedule/{slug}",
            f"/api/shows/{slug}",
            f"/api/station/{slug}/schedule",
            f"/wp-json/radio/v1/schedule",
            f"/wp-json/wp/v2/shows?per_page=50",
        ):
            try:
                resp = self.fetch(base + api_path, headers={"Accept": "application/json"})
                data = resp.json()
                result = _parse_show_list(data, slug, tz, name, url)
                if result and result.days:
                    return result
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Strategy 2: __NEXT_DATA__ / embedded JSON
    # ------------------------------------------------------------------

    def _try_next_data(self, url: str, slug: str, tz: str, name: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)

        # __NEXT_DATA__ first
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                data = json.loads(script.string)
                from .abc_au import _find_programme_list, _parse_programme_list
                programmes = _find_programme_list(data)
                if programmes:
                    return _parse_programme_list(programmes, slug, tz, source_url=url)
            except Exception:
                pass

        # Any application/json scripts
        for tag in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(tag.string or "")
                result = _parse_show_list(data, slug, tz, name, url)
                if result and result.days:
                    return result
            except Exception:
                continue

        # Also look for inline window.__INITIAL_STATE__ or similar
        for tag in soup.find_all("script"):
            src = tag.string or ""
            for var in ("__INITIAL_STATE__", "__APP_STATE__", "window.scheduleData"):
                if var not in src:
                    continue
                m = re.search(r"(?:window\.)?" + re.escape(var.replace("window.", "")) +
                              r"\s*=\s*(\{.*?\});", src, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        result = _parse_show_list(data, slug, tz, name, url)
                        if result and result.days:
                            return result
                    except Exception:
                        pass

        return None

    # ------------------------------------------------------------------
    # Strategy 3: HTML show-card / text parsing
    # ------------------------------------------------------------------

    def _try_show_cards(self, url: str, slug: str, tz: str, name: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)

        day_slots: dict[str, list[TimeSlot]] = {d: [] for d in _ALL_DAYS + ["weekdays", "weekend"]}

        cards = (
            soup.find_all(class_=re.compile(r"show[-_]card|program[-_]card|schedule[-_]item", re.I))
            or soup.find_all(class_=re.compile(r"\bshow\b|\bprogram\b|\bsegment\b", re.I))
            or soup.find_all("article")
        )

        if not cards:
            # Fall back to raw text
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            days_dict = parse_schedule_text(text)
            if days_dict:
                days = {
                    day: DaySchedule(slots=[
                        TimeSlot(start=s["start"], title=s["title"],
                                 description=s.get("description", ""),
                                 presenter=s.get("presenter", ""))
                        for s in slots
                    ])
                    for day, slots in days_dict.items()
                }
                return WeeklySchedule(
                    channel_id=slug, channel_name=name,
                    timezone=tz, source_url=url, days=days,
                )
            return None

        for card in cards:
            info = _parse_card(card)
            if not info:
                continue
            for day_key in info["days"]:
                if day_key in day_slots:
                    day_slots[day_key].append(TimeSlot(
                        start=info["start"],
                        title=info["title"],
                        presenter=info.get("presenter", ""),
                        description=info.get("description", ""),
                        duration=info.get("duration"),
                        image=info.get("image"),
                    ))

        days: dict[str, DaySchedule] = {}
        for day_key, slots in day_slots.items():
            if slots:
                slots.sort(key=lambda s: s.start)
                seen: set[str] = set()
                unique = []
                for s in slots:
                    if s.start not in seen:
                        seen.add(s.start)
                        unique.append(s)
                days[day_key] = DaySchedule(slots=unique)

        if not days:
            return None

        return WeeklySchedule(
            channel_id=slug, channel_name=name,
            timezone=tz, source_url=url, days=days,
        )


# ---------------------------------------------------------------------------
# JSON parser (handles list of show objects or nested dicts)
# ---------------------------------------------------------------------------

def _parse_show_list(data, slug: str, tz: str, name: str, source_url: str) -> Optional[WeeklySchedule]:
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("shows", "programs", "schedule", "items", "data", "results"):
            val = data.get(key)
            if isinstance(val, list) and val:
                items = val
                break
        if not items:
            # try one level deeper
            for v in data.values():
                if isinstance(v, dict):
                    for key in ("shows", "programs", "schedule", "items"):
                        val = v.get(key)
                        if isinstance(val, list) and val:
                            items = val
                            break
                if items:
                    break

    if not items:
        return None

    day_slots: dict[str, list[TimeSlot]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        title = (
            _first(item, ("title", "name", "showName", "show_name", "programme"))
            or ""
        ).strip()
        if isinstance(title, dict):
            title = title.get("rendered", "") or ""
        if not title:
            continue

        time_text = _first(item, ("schedule_time", "time", "broadcast_time", "air_time",
                                  "timeslot", "schedule", "on_air")) or ""
        info = _parse_time_day_text(str(time_text)) if time_text else None
        if not info:
            info = {"start": "00:00", "duration": None, "days": ["weekdays"]}

        image = (
            _first(item, ("image", "image_url", "thumbnail", "cover", "artwork", "logo"))
            or None
        )
        if isinstance(image, dict):
            image = image.get("url") or image.get("src") or image.get("source_url")

        presenter = _first(item, ("presenter", "host", "dj", "talent")) or ""

        for day_key in info["days"]:
            day_slots.setdefault(day_key, []).append(TimeSlot(
                start=info["start"],
                title=str(title),
                presenter=str(presenter) if presenter else "",
                duration=info.get("duration"),
                image=str(image) if image else None,
            ))

    if not day_slots:
        return None

    for slots in day_slots.values():
        slots.sort(key=lambda s: s.start)

    return WeeklySchedule(
        channel_id=slug, channel_name=name,
        timezone=tz, source_url=source_url,
        days={k: DaySchedule(slots=v) for k, v in day_slots.items()},
    )


# ---------------------------------------------------------------------------
# HTML show-card parser
# ---------------------------------------------------------------------------

def _parse_card(el) -> Optional[dict]:
    text = el.get_text(separator=" ", strip=True)
    if len(text) < 3:
        return None

    info = _parse_time_day_text(text)
    if not info:
        return None

    title_el = (
        el.find(re.compile(r"^h[2-5]$"))
        or el.find(class_=re.compile(r"title|name|heading", re.I))
    )
    title = title_el.get_text(strip=True) if title_el else ""

    if not title:
        stripped = _TIME_RANGE_RE.sub("", text).strip()
        stripped = _DAY_RE.sub("", stripped).strip()
        stripped = re.sub(r"^[-–—:,\s]+", "", stripped).strip()
        title = stripped.split("\n")[0].strip()[:120]

    if not title:
        return None

    host_el = el.find(class_=re.compile(r"host|presenter|talent|dj|anchor", re.I))
    presenter = host_el.get_text(strip=True) if host_el else ""

    img = el.find("img")
    image = None
    if img:
        src = img.get("data-src") or img.get("src", "")
        if src and src.startswith("http") and not any(
            skip in src for skip in ("placeholder", "blank", "spacer", "logo")
        ):
            image = src

    desc_el = el.find(class_=re.compile(r"desc|synopsis|summary|excerpt", re.I)) or el.find("p")
    description = desc_el.get_text(strip=True) if desc_el else ""

    return {**info, "title": title, "presenter": presenter, "description": description, "image": image}


# ---------------------------------------------------------------------------
# Time / day helpers
# ---------------------------------------------------------------------------

def _parse_time_day_text(text: str) -> Optional[dict]:
    m = _TIME_RANGE_RE.search(text)
    if not m:
        return None

    start_h, start_ampm = m.group(1), m.group(2)
    end_h, end_ampm = m.group(3), m.group(4) or start_ampm

    start = _to_24h(start_h, start_ampm)
    end = _to_24h(end_h, end_ampm)
    if start is None:
        return None

    duration: Optional[int] = None
    if end is not None:
        s_mins, e_mins = _to_mins(start), _to_mins(end)
        if e_mins > s_mins:
            duration = e_mins - s_mins
        elif e_mins < s_mins:
            duration = (24 * 60 - s_mins) + e_mins

    prefix = text[:m.start()].strip()
    suffix = text[m.end():].strip()
    day_search = _DAY_RE.search(prefix) or _DAY_RE.search(suffix)
    day_text = day_search.group(0).lower() if day_search else "weekdays"
    days = _day_text_to_keys(day_text)

    return {"start": start, "duration": duration, "days": days}


def _to_24h(h_str: str, ampm: Optional[str]) -> Optional[str]:
    try:
        if ":" in h_str:
            h, m = map(int, h_str.split(":"))
        else:
            h, m = int(h_str), 0
        if ampm:
            a = ampm.lower()
            if a == "pm" and h != 12:
                h += 12
            elif a == "am" and h == 12:
                h = 0
        return f"{h % 24:02d}:{m:02d}"
    except (ValueError, TypeError):
        return None


def _to_mins(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _day_text_to_keys(text: str) -> list[str]:
    text = text.lower().strip()
    if any(k in text for k in ("weekend", "sat-sun", "sat – sun")):
        return ["saturday", "sunday"]
    if "saturday" in text or text == "sat":
        return ["saturday"]
    if "sunday" in text or text == "sun":
        return ["sunday"]
    if text in ("monday", "mon"):
        return ["monday"]
    if "tuesday" in text or text == "tue":
        return ["tuesday"]
    if "wednesday" in text or text == "wed":
        return ["wednesday"]
    if "thursday" in text or text == "thu":
        return ["thursday"]
    if "friday" in text or text == "fri":
        return ["friday"]
    if any(k in text for k in ("daily", "every day", "everyday", "7 days")):
        return ["weekdays", "saturday", "sunday"]
    return ["weekdays"]


def _first(d: dict, keys, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return default


# ---------------------------------------------------------------------------
# URL / slug helpers
# ---------------------------------------------------------------------------

def _station_slug(url: str) -> str:
    """Extract station slug from URL, e.g. 'nova1069' from /station/nova1069."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if "station" in parts:
        idx = parts.index("station")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    # fall back to subdomain or domain part
    host = parsed.hostname or ""
    for part in host.split("."):
        if part not in ("www", "com", "au", "novafm", "smoothfm", "nova", "smooth"):
            return part
    return host.split(".")[0] if host else "nova"


def _slug_to_tz(slug: str, url: str) -> str:
    if slug in _SLUG_TZ:
        return _SLUG_TZ[slug]
    # Infer from frequency digits in slug
    digits = re.sub(r"\D", "", slug)
    tz_by_freq = {
        "969": "Australia/Sydney",
        "100": "Australia/Melbourne",
        "1069": "Australia/Brisbane",
        "919": "Australia/Adelaide",
        "961": "Australia/Perth",
        "937": "Australia/Perth",
        "953": "Australia/Sydney",
        "915": "Australia/Melbourne",
    }
    for freq, tz in tz_by_freq.items():
        if digits.endswith(freq):
            return tz
    return "Australia/Sydney"


def _slug_to_display(slug: str) -> str:
    # "nova1069" → "Nova 106.9", "smooth953" → "Smooth 95.3"
    digits = re.sub(r"\D", "", slug)
    brand = "Nova" if "nova" in slug.lower() else "Smooth FM" if "smooth" in slug.lower() else slug.upper()
    if len(digits) >= 3:
        freq = digits[:-1] + "." + digits[-1]
        return f"{brand} {freq}"
    return brand
