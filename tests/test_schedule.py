"""Tests for schedule loading and expansion."""

import pytest
from datetime import date, datetime
import pytz

from radio_epg.models import DaySchedule, TimeSlot, WeeklySchedule
from radio_epg.schedule import expand_schedule, load_schedule_dict


SAMPLE_DICT = {
    "channel": {
        "id": "test.radio",
        "name": "Test Radio",
        "timezone": "Australia/Brisbane",
    },
    "schedule": {
        "weekdays": [
            {"start": "06:00", "title": "Morning Show", "presenter": "DJ Dave", "duration": 180},
            {"start": "09:00", "title": "Mid Morning", "duration": 180},
            {"start": "12:00", "title": "Lunch", "duration": 120},
        ],
        "saturday": [
            {"start": "08:00", "title": "Saturday Special", "duration": 240},
        ],
        "sunday": [
            {"start": "09:00", "title": "Sunday Session", "duration": 180},
        ],
    },
}


def test_load_schedule_dict():
    sched = load_schedule_dict(SAMPLE_DICT)
    assert sched.channel_id == "test.radio"
    assert sched.timezone == "Australia/Brisbane"
    assert "weekdays" in sched.days
    assert len(sched.days["weekdays"].slots) == 3


def test_weekday_expansion():
    sched = load_schedule_dict(SAMPLE_DICT)
    # Monday 2026-06-08 is a Monday
    start = date(2026, 6, 8)
    progs = expand_schedule(sched, start, days=1)
    assert len(progs) == 3
    assert progs[0].title == "Morning Show"


def test_weekend_expansion():
    sched = load_schedule_dict(SAMPLE_DICT)
    # 2026-06-13 is a Saturday
    start = date(2026, 6, 13)
    progs = expand_schedule(sched, start, days=1)
    assert len(progs) == 1
    assert progs[0].title == "Saturday Special"


def test_programme_datetimes():
    sched = load_schedule_dict(SAMPLE_DICT)
    start = date(2026, 6, 8)
    progs = expand_schedule(sched, start, days=1)

    tz = pytz.timezone("Australia/Brisbane")
    expected_start = tz.localize(datetime(2026, 6, 8, 6, 0))
    expected_stop = tz.localize(datetime(2026, 6, 8, 9, 0))

    assert progs[0].start == expected_start
    assert progs[0].stop == expected_stop


def test_presenter_carried():
    sched = load_schedule_dict(SAMPLE_DICT)
    start = date(2026, 6, 8)
    progs = expand_schedule(sched, start, days=1)
    assert progs[0].presenter == "DJ Dave"
    assert progs[1].presenter == ""


def test_implicit_duration_from_next_slot():
    """When no duration given, slot ends when the next one begins."""
    data = {
        "channel": {"id": "x", "name": "X", "timezone": "UTC"},
        "schedule": {
            "weekdays": [
                {"start": "09:00", "title": "A"},
                {"start": "12:00", "title": "B"},
            ]
        },
    }
    sched = load_schedule_dict(data)
    progs = expand_schedule(sched, date(2026, 6, 8), days=1)
    assert progs[0].stop == progs[1].start


def test_last_slot_runs_to_midnight():
    """Last slot with no duration should run to midnight."""
    data = {
        "channel": {"id": "x", "name": "X", "timezone": "UTC"},
        "schedule": {
            "weekdays": [
                {"start": "22:00", "title": "Late Night"},
            ]
        },
    }
    sched = load_schedule_dict(data)
    progs = expand_schedule(sched, date(2026, 6, 8), days=1)
    assert progs[0].stop.hour == 0
    assert progs[0].stop.day == 9  # next day midnight


def test_multi_day_expansion():
    sched = load_schedule_dict(SAMPLE_DICT)
    progs = expand_schedule(sched, date(2026, 6, 8), days=7)
    # Mon-Fri: 3 slots each (5 days) + 1 Saturday + 1 Sunday = 16
    assert len(progs) == 17


def test_empty_day_produces_no_programmes():
    data = {
        "channel": {"id": "x", "name": "X", "timezone": "UTC"},
        "schedule": {},
    }
    sched = load_schedule_dict(data)
    progs = expand_schedule(sched, date(2026, 6, 8), days=1)
    assert progs == []
