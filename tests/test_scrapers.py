"""Tests for station schedule scrapers (HTTP mocked with responses library)."""

import json
import pytest

try:
    import responses as responses_lib
    HAS_RESPONSES = True
except ImportError:
    HAS_RESPONSES = False

from radio_epg.scrapers.abc_au import ABCScraper, _extract_station_slug, _collapse_weekdays
from radio_epg.models import DaySchedule, TimeSlot


pytestmark = pytest.mark.skipif(not HAS_RESPONSES, reason="responses library not installed")


_API_URL = "https://www.abc.net.au/api/public/programmes/station/brisbane"
_EPG_URL = "https://www.abc.net.au/brisbane/station-epg"


def _sample_api_payload():
    return {
        "items": [
            {
                "title": "Brisbane Mornings",
                "startTime": "2026-06-08T08:30:00+10:00",
                "endTime": "2026-06-08T10:00:00+10:00",
                "synopsis": "Morning show with Craig and Loretta.",
                "presenter": "Craig Zonca",
            },
            {
                "title": "Focus",
                "startTime": "2026-06-08T10:00:00+10:00",
                "endTime": "2026-06-08T12:00:00+10:00",
                "synopsis": "In-depth interviews.",
                "presenter": "Steve Austin",
            },
            # Saturday entry — should be filed under "saturday"
            {
                "title": "Saturday Morning",
                "startTime": "2026-06-13T06:00:00+10:00",
                "endTime": "2026-06-13T10:00:00+10:00",
                "synopsis": "Saturday show.",
                "presenter": "Rebecca Levingston",
            },
        ]
    }


@responses_lib.activate
def test_api_strategy_parses_schedule():
    responses_lib.add(
        responses_lib.GET, _API_URL, json=_sample_api_payload(), status=200
    )
    scraper = ABCScraper()
    schedule = scraper.scrape(_EPG_URL)

    assert schedule.channel_id == "abc.brisbane"
    assert schedule.timezone == "Australia/Brisbane"
    assert "monday" in schedule.days or "weekdays" in schedule.days


@responses_lib.activate
def test_api_returns_slots_with_correct_times():
    responses_lib.add(
        responses_lib.GET, _API_URL, json=_sample_api_payload(), status=200
    )
    scraper = ABCScraper()
    schedule = scraper.scrape(_EPG_URL)

    day_sched = schedule.get_day_schedule(0)  # Monday
    assert any(s.start == "08:30" for s in day_sched.slots)


@responses_lib.activate
def test_api_returns_presenter():
    responses_lib.add(
        responses_lib.GET, _API_URL, json=_sample_api_payload(), status=200
    )
    scraper = ABCScraper()
    schedule = scraper.scrape(_EPG_URL)

    day_sched = schedule.get_day_schedule(0)
    morning = next(s for s in day_sched.slots if s.start == "08:30")
    assert morning.presenter == "Craig Zonca"


@responses_lib.activate
def test_api_computes_duration():
    responses_lib.add(
        responses_lib.GET, _API_URL, json=_sample_api_payload(), status=200
    )
    scraper = ABCScraper()
    schedule = scraper.scrape(_EPG_URL)

    day_sched = schedule.get_day_schedule(0)
    morning = next(s for s in day_sched.slots if s.start == "08:30")
    assert morning.duration == 90  # 08:30 to 10:00 = 90 minutes


@responses_lib.activate
def test_saturday_filed_correctly():
    responses_lib.add(
        responses_lib.GET, _API_URL, json=_sample_api_payload(), status=200
    )
    scraper = ABCScraper()
    schedule = scraper.scrape(_EPG_URL)

    sat_sched = schedule.get_day_schedule(5)  # Saturday
    assert any(s.title == "Saturday Morning" for s in sat_sched.slots)


def test_extract_station_slug():
    assert _extract_station_slug("https://www.abc.net.au/brisbane/station-epg") == "brisbane"
    assert _extract_station_slug("https://www.abc.net.au/sydney/station-epg") == "sydney"
    assert _extract_station_slug("https://www.abc.net.au/radio/brisbane/programs") == "brisbane"


def test_collapse_weekdays_identical():
    slot = TimeSlot(start="06:00", title="Morning", duration=120)
    days = {
        "monday": DaySchedule(slots=[slot]),
        "tuesday": DaySchedule(slots=[slot]),
        "wednesday": DaySchedule(slots=[slot]),
        "thursday": DaySchedule(slots=[slot]),
        "friday": DaySchedule(slots=[slot]),
    }
    result = _collapse_weekdays(days)
    assert "weekdays" in result
    assert "monday" not in result


def test_collapse_weekdays_different():
    days = {
        "monday": DaySchedule(slots=[TimeSlot(start="06:00", title="Monday Show")]),
        "tuesday": DaySchedule(slots=[TimeSlot(start="07:00", title="Tuesday Show")]),
    }
    result = _collapse_weekdays(days)
    assert "monday" in result
    assert "tuesday" in result
    assert "weekdays" not in result
