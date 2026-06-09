"""Load weekly schedules from YAML and expand them into Programme objects."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import pytz
import yaml

from .models import DaySchedule, ProgramOverride, Programme, TimeSlot, WeeklySchedule


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def load_schedule_yaml(path: str | Path) -> WeeklySchedule:
    """Load a WeeklySchedule from a YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return _parse_schedule_dict(data)


def load_schedule_dict(data: dict) -> WeeklySchedule:
    """Build a WeeklySchedule from a pre-parsed dict (e.g. from a scraper)."""
    return _parse_schedule_dict(data)


def _parse_schedule_dict(data: dict) -> WeeklySchedule:
    ch = data.get("channel", {})
    schedule = WeeklySchedule(
        channel_id=ch.get("id", "unknown"),
        channel_name=ch.get("name", "Unknown"),
        timezone=ch.get("timezone", "UTC"),
        source_url=ch.get("website"),
    )

    for day_key, slots_data in data.get("schedule", {}).items():
        slots = []
        for s in slots_data or []:
            slots.append(TimeSlot(
                start=str(s["start"]),
                title=s.get("title", ""),
                description=s.get("description", ""),
                presenter=s.get("presenter", ""),
                duration=s.get("duration"),
            ))
        schedule.days[day_key] = DaySchedule(slots=slots)

    return schedule


# ---------------------------------------------------------------------------
# Schedule expansion
# ---------------------------------------------------------------------------

def expand_schedule(
    schedule: WeeklySchedule,
    start_date: date,
    days: int,
) -> list[Programme]:
    """Expand a WeeklySchedule into concrete Programme objects for *days* days."""
    tz = pytz.timezone(schedule.timezone)
    programmes: list[Programme] = []

    for offset in range(days):
        day = start_date + timedelta(days=offset)
        day_sched = schedule.get_day_schedule(day.weekday())
        programmes.extend(_expand_day(schedule.channel_id, day, day_sched, tz))

    return programmes


def _expand_day(
    channel_id: str,
    day: date,
    day_sched: DaySchedule,
    tz: pytz.BaseTzInfo,
) -> Iterator[Programme]:
    """Yield Programme objects for a single day."""
    slots = day_sched.slots
    if not slots:
        return

    resolved: list[tuple[datetime, datetime, TimeSlot]] = []

    for i, slot in enumerate(slots):
        start_dt = _make_dt(day, slot.start, tz)

        if slot.duration is not None:
            stop_dt = start_dt + timedelta(minutes=slot.duration)
        elif i + 1 < len(slots):
            # End when the next slot begins (may roll into next calendar day)
            next_start = _make_dt(day, slots[i + 1].start, tz)
            if next_start <= start_dt:
                next_start += timedelta(days=1)
            stop_dt = next_start
        else:
            # Last slot with no explicit duration: run to midnight
            stop_dt = _make_dt(day + timedelta(days=1), "00:00", tz)

        resolved.append((start_dt, stop_dt, slot))

    for start_dt, stop_dt, slot in resolved:
        yield Programme(
            channel_id=channel_id,
            start=start_dt,
            stop=stop_dt,
            title=slot.title,
            description=slot.description,
            presenter=slot.presenter,
        )


# ---------------------------------------------------------------------------
# Override application
# ---------------------------------------------------------------------------

def apply_overrides(
    programmes: list[Programme],
    overrides: list[ProgramOverride],
    channel_timezones: dict[str, str],
) -> list[Programme]:
    """Apply a list of ProgramOverride objects to an expanded programme list.

    - "cancellation": removes all slots that overlap the override window
    - "event" / "sports": removes overlapping slots and inserts the override
    """
    if not overrides:
        return programmes

    result = list(programmes)

    for ov in overrides:
        tz_name = channel_timezones.get(ov.channel_id, "UTC")
        tz = pytz.timezone(tz_name)
        ov_date = date.fromisoformat(ov.date)
        start_dt = _make_dt(ov_date, ov.start, tz)
        end_dt = _make_dt(ov_date, ov.end, tz)

        # Remove overlapping regular programmes for this channel
        result = [
            p for p in result
            if not (p.channel_id == ov.channel_id and _overlaps(p.start, p.stop, start_dt, end_dt))
        ]

        if ov.override_type != "cancellation":
            result.append(Programme(
                channel_id=ov.channel_id,
                start=start_dt,
                stop=end_dt,
                title=ov.title,
                description=ov.description,
                image=ov.image,
            ))

    return sorted(result, key=lambda p: (p.channel_id, p.start))


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    return s1 < e2 and e1 > s2


def _make_dt(day: date, time_str: str, tz: pytz.BaseTzInfo) -> datetime:
    h, m = map(int, time_str.split(":"))
    naive = datetime(day.year, day.month, day.day, h, m)
    return tz.localize(naive)
