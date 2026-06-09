"""Tests for M3U8 parser."""

import pytest
from radio_epg.m3u8_parser import parse_m3u8_text


SAMPLE_M3U8 = """\
#EXTM3U x-tvg-url="epg.xml"

#EXTINF:-1 tvg-id="abc.brisbane" tvg-name="ABC Radio Brisbane" tvg-logo="https://example.com/logo.png" group-title="Radio",ABC Radio Brisbane
http://stream.example.com/abc-brisbane

#EXTINF:-1 tvg-id="triple.j" tvg-name="triple j" group-title="Radio",triple j
http://stream.example.com/triple-j

#EXTINF:-1 tvg-name="No ID Station" group-title="Radio",No ID Station
http://stream.example.com/no-id
"""


def test_basic_parse():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert len(channels) == 3


def test_tvg_id():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert channels[0].tvg_id == "abc.brisbane"
    assert channels[1].tvg_id == "triple.j"


def test_name():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert channels[0].name == "ABC Radio Brisbane"


def test_logo():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert channels[0].logo == "https://example.com/logo.png"
    assert channels[1].logo is None


def test_group():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert channels[0].group == "Radio"


def test_url():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert channels[0].url == "http://stream.example.com/abc-brisbane"


def test_no_tvg_id_falls_back_to_slug():
    channels = parse_m3u8_text(SAMPLE_M3U8)
    assert channels[2].tvg_id == "no.id.station"


def test_empty_m3u8():
    channels = parse_m3u8_text("#EXTM3U\n")
    assert channels == []


def test_missing_url_skipped():
    content = "#EXTM3U\n#EXTINF:-1 tvg-id=\"x\",Station\n"
    channels = parse_m3u8_text(content)
    assert channels == []
