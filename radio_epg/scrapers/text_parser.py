"""Parse pasted schedule text into structured slot data.

Handles common formats found when copying from station websites:

  6:00 AM Morning Show
  6:00am - Breakfast with Jane Smith
  06:00 Morning Show — Description here
  09:00 - 12:00 Mid Morning

Lines that look like day headers (Monday, Tuesday, Weekdays …) switch
the current day context for subsequent lines.
"""

from __future__ import annotations

import re
from typing import Optional

_DAY_MAP: dict[str, str] = {
    "monday": "monday", "mon": "monday",
    "tuesday": "tuesday", "tue": "tuesday", "tues": "tuesday",
    "wednesday": "wednesday", "wed": "wednesday",
    "thursday": "thursday", "thu": "thursday", "thur": "thursday", "thurs": "thursday",
    "friday": "friday", "fri": "friday",
    "saturday": "saturday", "sat": "saturday",
    "sunday": "sunday", "sun": "sunday",
    "weekday": "weekdays", "weekdays": "weekdays",
    "weekend": "weekend", "weekends": "weekend",
    "daily": "default", "everyday": "default",
}

# Matches: 06:00, 6:00, 6:00am, 6:00 AM, 6.00, 06h00, 6am
_TIME_RE = re.compile(
    r"(?<!\d)(\d{1,2})[:h\.](\d{2})(?::\d{2})?\s*([aApP][mM])?(?!\d)"
    r"|"
    r"(?<!\d)(\d{1,2})\s*([aApP][mM])(?!\w)",
    re.IGNORECASE,
)

# Dash or arrow between times: "6:00 - 9:00", "6:00 – 9:00", "6:00 to 9:00"
_END_TIME_RE = re.compile(
    r"^[-–—]?\s*(?:to\s+)?\d{1,2}[:h\.]\d{2}(?::\d{2})?\s*(?:[aApP][mM])?\s*[-–—]?\s*",
    re.IGNORECASE,
)


def _to_24h(h: int, m: int, ampm: Optional[str]) -> str:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and h != 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
    return f"{h % 24:02d}:{m:02d}"


def _detect_day(line: str) -> Optional[str]:
    """Return the day key if the line is a day-name header, else None."""
    if _TIME_RE.search(line):
        return None  # contains a time — treat as schedule line
    clean = re.sub(r"[:\-–—,\s]+", " ", line.strip()).strip().lower()
    if clean in _DAY_MAP:
        return _DAY_MAP[clean]
    first = clean.split()[0] if clean.split() else ""
    # Only accept the first-word match if the line is short (< 40 chars)
    if first in _DAY_MAP and len(line.strip()) < 40:
        return _DAY_MAP[first]
    return None


def _parse_time_line(line: str) -> Optional[dict]:
    """Extract {start, title, description?} from a schedule line."""
    m = _TIME_RE.search(line)
    if not m:
        return None

    if m.group(1) is not None:
        h, mins, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    else:
        h, mins, ampm = int(m.group(4)), 0, m.group(5)

    start = _to_24h(h, mins, ampm)
    rest = line[m.end():].strip()

    # Strip optional end time
    rest = _END_TIME_RE.sub("", rest).strip()
    # Strip leading dash/colon
    rest = re.sub(r"^[-–—:]+\s*", "", rest).strip()

    if not rest:
        return None

    # Split on " - " or " – " for description
    parts = re.split(r"\s+[-–—]\s+", rest, maxsplit=1)
    title = parts[0].strip()
    description = parts[1].strip() if len(parts) > 1 else ""

    if not title:
        return None

    slot: dict = {"start": start, "title": title}
    if description:
        slot["description"] = description
    return slot


def parse_schedule_text(text: str, default_day: str = "weekdays") -> dict[str, list[dict]]:
    """Parse multi-line schedule text into {day_key: [slot, ...]} dict.

    Each slot is {"start": "HH:MM", "title": "...", "description"?: "..."}.
    Day keys follow the same convention as the YAML schedule files:
    weekdays, saturday, sunday, monday … friday, weekend, default.
    """
    result: dict[str, list[dict]] = {}
    current_day = default_day

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        day = _detect_day(line)
        if day:
            current_day = day
            continue

        slot = _parse_time_line(line)
        if slot:
            result.setdefault(current_day, []).append(slot)

    for slots in result.values():
        slots.sort(key=lambda s: s["start"])

    return result
