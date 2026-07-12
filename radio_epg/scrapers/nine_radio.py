"""Scraper for Nine Radio station websites.

Handles: 4BC (Brisbane), 2GB (Sydney), 3AW (Melbourne),
         5AA (Adelaide), 6PR (Perth), 9Radio.

Show pages typically list programme cards with a pattern like:
    "Weekdays 6am – 9am" / "Saturday 5am – 9am"
followed by a show title and host image.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urlparse

from ..models import DaySchedule, TimeSlot, WeeklySchedule
from .base import BaseScraper, ScraperError


_DOMAIN_TZ: dict[str, str] = {
    "4bc":    "Australia/Brisbane",
    "2gb":    "Australia/Sydney",
    "3aw":    "Australia/Melbourne",
    "5aa":    "Australia/Adelaide",
    "6pr":    "Australia/Perth",
    "9radio": "Australia/Sydney",
    "2ue":    "Australia/Sydney",
    "4bh":    "Australia/Brisbane",
    "6pb":    "Australia/Perth",
}

_DOMAIN_NAME: dict[str, str] = {
    "4bc":    "4BC",
    "2gb":    "2GB",
    "3aw":    "3AW",
    "5aa":    "5AA",
    "6pr":    "6PR",
    "9radio": "9Radio",
}

# "Weekdays", "Monday to Friday", "Daily", "Saturday", etc.
_DAY_RE = re.compile(
    r"(weekdays?|monday[\s\-–](?:to[\s]+)?friday|mon[\s\-–]fri"
    r"|weekends?|saturday|sunday|monday|tuesday|wednesday|thursday|friday"
    r"|daily|every\s+day|mon|tue|wed|thu|fri|sat|sun)",
    re.I,
)

# "6am – 9am", "6:00am – 9:00am", "6:00 AM – 9:00 AM", "6am-9am"
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?)\s*([aApP][mM])?\s*[-–—]\s*(\d{1,2}(?::\d{2})?)\s*([aApP][mM])",
    re.I,
)

_ALL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class NineRadioScraper(BaseScraper):
    """Scraper for Nine Radio network station websites."""

    def scrape(self, url: str) -> WeeklySchedule:
        slug = _station_slug(url)
        tz = _DOMAIN_TZ.get(slug, "Australia/Sydney")
        name = _DOMAIN_NAME.get(slug, slug.upper())

        errors: list[str] = []
        for strategy in (self._try_wp_json, self._try_next_data, self._try_show_cards):
            try:
                result = strategy(url, slug, tz, name)
                if result is not None and result.days:
                    return result
            except Exception as exc:
                errors.append(f"{strategy.__name__}: {exc}")
                continue

        raise ScraperError(
            f"Could not extract schedule from {url}. "
            + (" | ".join(errors) if errors else "No schedule data found.")
        )

    # ------------------------------------------------------------------
    # Strategy 1: WordPress REST API
    # ------------------------------------------------------------------

    def _try_wp_json(self, url: str, slug: str, tz: str, name: str) -> Optional[WeeklySchedule]:
        base = f"https://www.{slug}.com.au"
        for path in (
            "/wp-json/radio/v1/schedule",
            "/wp-json/shows/v1/all",
            "/wp-json/wp/v2/shows?per_page=50",
            "/wp-json/wp/v2/programs?per_page=50",
        ):
            try:
                resp = self.fetch(base + path, headers={"Accept": "application/json"})
                data = resp.json()
                if isinstance(data, list) and data:
                    result = _parse_wp_show_list(data, slug, tz, name, url)
                    if result and result.days:
                        return result
                elif isinstance(data, dict):
                    items = data.get("shows") or data.get("programs") or data.get("schedule") or []
                    if items:
                        result = _parse_wp_show_list(items, slug, tz, name, url)
                        if result and result.days:
                            return result
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Strategy 2: __NEXT_DATA__ (if site is Next.js)
    # ------------------------------------------------------------------

    def _try_next_data(self, url: str, slug: str, tz: str, name: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None
        from .abc_au import _find_programme_list, _parse_programme_list
        programmes = _find_programme_list(data)
        if not programmes:
            return None
        return _parse_programme_list(programmes, slug, tz, source_url=url)

    # ------------------------------------------------------------------
    # Strategy 3: HTML show-card parsing
    # ------------------------------------------------------------------

    def _try_show_cards(self, url: str, slug: str, tz: str, name: str) -> Optional[WeeklySchedule]:
        soup = self.fetch_soup(url)

        # Also scan <script type="application/json"> for embedded schedule data
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                from .abc_au import _find_programme_list, _parse_programme_list
                programmes = _find_programme_list(data)
                if programmes:
                    result = _parse_programme_list(programmes, slug, tz, source_url=url)
                    if result and result.days:
                        return result
            except Exception:
                continue

        # Parse show cards from HTML
        day_slots: dict[str, list[TimeSlot]] = {d: [] for d in _ALL_DAYS + ["weekdays", "weekend"]}

        # Candidate card containers — ordered most-specific first
        cards = (
            soup.find_all(class_=re.compile(r"show[-_]card|program[-_]card|schedule[-_]item", re.I))
            or soup.find_all(class_=re.compile(r"\bshow\b|\bprogram\b|\bsegment\b", re.I))
            or soup.find_all("article")
        )

        # If no cards, try extracting from raw text using the text parser
        if not cards:
            from .text_parser import parse_schedule_text
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
            info = _parse_show_card(card)
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

        # Sort each day and remove empties
        days: dict[str, DaySchedule] = {}
        for day_key, slots in day_slots.items():
            if slots:
                slots.sort(key=lambda s: s.start)
                # Deduplicate by start time (keep first occurrence)
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
# WordPress show list parser
# ---------------------------------------------------------------------------

def _parse_wp_show_list(
    items: list, slug: str, tz: str, name: str, source_url: str
) -> Optional[WeeklySchedule]:
    """Parse a list of WordPress show objects into a WeeklySchedule."""
    day_slots: dict[str, list[TimeSlot]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        title = (
            item.get("title", {}).get("rendered", "")
            or item.get("name", "")
            or item.get("title", "")
        ).strip()
        if not title:
            continue

        # Look for time/day schedule meta fields
        meta = item.get("meta") or item.get("acf") or item.get("schedule") or {}
        time_text = (
            meta.get("schedule_time") or meta.get("time") or
            meta.get("broadcast_time") or item.get("schedule_time") or ""
        )

        if not time_text:
            # Try to extract from rendered content
            content = (
                item.get("content", {}).get("rendered", "")
                or item.get("excerpt", {}).get("rendered", "")
                or ""
            )
            import re as _re
            m = _TIME_RANGE_RE.search(content)
            if m:
                time_text = m.group(0)

        info = _parse_time_day_text(str(time_text)) if time_text else None
        if not info:
            info = {"start": "00:00", "duration": None, "days": ["weekdays"]}

        image_url = None
        fi = item.get("_embedded", {}).get("wp:featuredmedia", [{}])
        if fi and isinstance(fi, list):
            img = fi[0]
            image_url = (
                img.get("source_url") or
                img.get("media_details", {}).get("sizes", {}).get("medium", {}).get("source_url")
            )

        for day_key in info["days"]:
            day_slots.setdefault(day_key, []).append(TimeSlot(
                start=info["start"],
                title=title,
                duration=info.get("duration"),
                image=image_url,
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

def _parse_show_card(el) -> Optional[dict]:
    """Extract schedule info from a single show card element."""
    text = el.get_text(separator=" ", strip=True)
    if len(text) < 3:
        return None

    info = _parse_time_day_text(text)
    if not info:
        return None

    # Title — prefer heading elements
    title_el = (
        el.find(re.compile(r"^h[2-5]$")) or
        el.find(class_=re.compile(r"title|name|heading", re.I))
    )
    title = title_el.get_text(strip=True) if title_el else ""

    if not title:
        # Strip the matched time/day portion from the text and use what's left
        stripped = _TIME_RANGE_RE.sub("", text).strip()
        stripped = _DAY_RE.sub("", stripped).strip()
        stripped = re.sub(r"^[-–—:,\s]+", "", stripped).strip()
        title = stripped.split("\n")[0].strip()[:120]

    if not title:
        return None

    # Presenter
    host_el = el.find(class_=re.compile(r"host|presenter|talent|anchor", re.I))
    presenter = host_el.get_text(strip=True) if host_el else ""

    # Image — prefer data-src (lazy loaded) then src
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

    return {
        **info,
        "title": title,
        "presenter": presenter,
        "description": description,
        "image": image,
    }


# ---------------------------------------------------------------------------
# Time / day text parser
# ---------------------------------------------------------------------------

def _parse_time_day_text(text: str) -> Optional[dict]:
    """Parse a string like 'Weekdays 6am – 9am' → {start, duration, days}."""
    m = _TIME_RANGE_RE.search(text)
    if not m:
        return None

    start_h = m.group(1)
    start_ampm = m.group(2)
    end_h = m.group(3)
    end_ampm = m.group(4) or start_ampm   # inherit AM/PM from end if start has none

    start = _to_24h(start_h, start_ampm)
    end   = _to_24h(end_h,   end_ampm)
    if start is None:
        return None

    duration: Optional[int] = None
    if end is not None:
        s_mins = _to_mins(start)
        e_mins = _to_mins(end)
        if e_mins > s_mins:
            duration = e_mins - s_mins
        elif e_mins < s_mins:
            # crosses midnight
            duration = (24 * 60 - s_mins) + e_mins

    # Look for day indicator in the text before the time match
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
    if "saturday" in text or "sat" == text:
        return ["saturday"]
    if "sunday" in text or "sun" == text:
        return ["sunday"]
    if "monday" == text or "mon" == text:
        return ["monday"]
    if "tuesday" in text or "tue" == text:
        return ["tuesday"]
    if "wednesday" in text or "wed" == text:
        return ["wednesday"]
    if "thursday" in text or "thu" == text:
        return ["thursday"]
    if "friday" in text or "fri" == text:
        return ["friday"]
    if any(k in text for k in ("daily", "every day", "everyday", "7 days")):
        return ["weekdays", "saturday", "sunday"]
    # default: weekdays / mon-fri
    return ["weekdays"]


def _station_slug(url: str) -> str:
    host = urlparse(url).hostname or ""
    for part in host.split("."):
        if part not in ("www", "com", "au", "radio", "net") and part:
            return part
    return host
