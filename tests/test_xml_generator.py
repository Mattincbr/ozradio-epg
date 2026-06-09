"""Tests for XMLTV XML generation."""

import io
import pytest
from datetime import date, datetime
import pytz
from xml.etree import ElementTree as ET

from radio_epg.models import Channel, Programme
from radio_epg.schedule import expand_schedule, load_schedule_dict
from radio_epg.xml_generator import generate_xmltv, write_xmltv


def _make_programmes():
    data = {
        "channel": {"id": "test.radio", "name": "Test Radio", "timezone": "UTC"},
        "schedule": {
            "weekdays": [
                {"start": "06:00", "title": "Morning Show", "presenter": "DJ Dave",
                 "description": "Wake up!", "duration": 180},
                {"start": "09:00", "title": "Mid Morning", "duration": 180},
            ],
        },
    }
    sched = load_schedule_dict(data)
    return expand_schedule(sched, date(2026, 6, 8), days=1)


def _make_channels():
    return [Channel(tvg_id="test.radio", name="Test Radio", url="http://example.com/stream")]


def test_generates_xml():
    xml = generate_xmltv(_make_channels(), _make_programmes())
    assert "<?xml" in xml
    assert "<tv" in xml


def test_channel_element():
    xml = generate_xmltv(_make_channels(), _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    channels = root.findall("channel")
    assert len(channels) == 1
    assert channels[0].get("id") == "test.radio"
    assert channels[0].find("display-name").text == "Test Radio"


def test_programme_elements():
    xml = generate_xmltv(_make_channels(), _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    progs = root.findall("programme")
    assert len(progs) == 2
    titles = [p.find("title").text for p in progs]
    assert "Morning Show" in titles
    assert "Mid Morning" in titles


def test_programme_start_stop():
    xml = generate_xmltv(_make_channels(), _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    prog = root.find("programme")
    # UTC offset: +0000
    assert "20260608060000" in prog.get("start")
    assert "+0000" in prog.get("start")


def test_presenter_in_credits():
    xml = generate_xmltv(_make_channels(), _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    morning = next(p for p in root.findall("programme")
                   if p.find("title").text == "Morning Show")
    credits = morning.find("credits")
    assert credits is not None
    assert credits.find("presenter").text == "DJ Dave"


def test_description_in_desc():
    xml = generate_xmltv(_make_channels(), _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    morning = next(p for p in root.findall("programme")
                   if p.find("title").text == "Morning Show")
    desc = morning.find("desc")
    assert desc is not None
    assert "Wake up!" in desc.text


def test_channels_without_programmes_omitted():
    channels = _make_channels() + [
        Channel(tvg_id="no.schedule", name="No Schedule", url="http://example.com/x")
    ]
    xml = generate_xmltv(channels, _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    ids = [c.get("id") for c in root.findall("channel")]
    assert "test.radio" in ids
    assert "no.schedule" not in ids


def test_write_to_file(tmp_path):
    output = tmp_path / "epg.xml"
    write_xmltv(_make_channels(), _make_programmes(), str(output))
    assert output.exists()
    content = output.read_text()
    assert "<tv" in content


def test_logo_icon_element():
    channels = [Channel(
        tvg_id="test.radio", name="Test Radio",
        url="http://example.com/stream",
        logo="http://example.com/logo.png"
    )]
    xml = generate_xmltv(channels, _make_programmes())
    root = ET.fromstring(xml.split("?>", 1)[-1])
    icon = root.find("channel/icon")
    assert icon is not None
    assert icon.get("src") == "http://example.com/logo.png"
