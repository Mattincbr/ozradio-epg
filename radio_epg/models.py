"""Core data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Channel:
    """A radio channel from an M3U8 playlist."""

    tvg_id: str
    name: str
    url: str
    logo: Optional[str] = None
    group: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.name} ({self.tvg_id})"


@dataclass
class TimeSlot:
    """One programme slot in a daily schedule."""

    start: str          # "HH:MM" 24-hour
    title: str
    description: str = ""
    presenter: str = ""
    duration: Optional[int] = None   # minutes; if None, runs until next slot
    image: Optional[str] = None      # programme artwork URL
    url: Optional[str] = None        # episode library / catch-up page URL


@dataclass
class DaySchedule:
    """An ordered list of slots for one day type."""

    slots: list[TimeSlot] = field(default_factory=list)


@dataclass
class WeeklySchedule:
    """A repeating weekly schedule for a single channel."""

    channel_id: str         # matches Channel.tvg_id
    channel_name: str
    timezone: str           # e.g. "Australia/Brisbane"
    source_url: Optional[str] = None

    # Keyed by day pattern: "weekdays", "monday"–"sunday", "saturday", "sunday"
    days: dict[str, DaySchedule] = field(default_factory=dict)

    def get_day_schedule(self, weekday: int) -> DaySchedule:
        """Return the DaySchedule for a Python weekday (0=Mon … 6=Sun)."""
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        name = day_names[weekday]

        # Most specific first, then group names
        for key in [name, "weekdays" if weekday < 5 else "weekend", "default"]:
            if key in self.days:
                return self.days[key]

        return DaySchedule()


@dataclass
class Programme:
    """A fully resolved EPG programme with concrete start/stop datetimes."""

    channel_id: str
    start: datetime
    stop: datetime
    title: str
    description: str = ""
    presenter: str = ""
    image: Optional[str] = None
    url: Optional[str] = None        # episode library / catch-up page URL


@dataclass
class ProgramOverride:
    """A one-off override that replaces, adds to, or cancels a scheduled slot."""

    id: str
    channel_id: str
    date: str           # "YYYY-MM-DD"
    start: str          # "HH:MM"
    end: str            # "HH:MM"
    title: str
    description: str = ""
    override_type: str = "event"    # "event" | "sports" | "cancellation"
    image: Optional[str] = None
