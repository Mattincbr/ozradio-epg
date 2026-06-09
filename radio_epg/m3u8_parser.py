"""Parse IPTV M3U8 playlists and extract radio channel metadata."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from .models import Channel


_EXTINF_RE = re.compile(
    r'#EXTINF:-?\d+(?:\.\d+)?(?:\s+(?P<attrs>[^,]*))?(?:,(?P<name>.*))?'
)
_ATTR_RE = re.compile(r'(\S+?)="([^"]*)"')


def _parse_attrs(attr_str: str) -> dict[str, str]:
    return {k: v for k, v in _ATTR_RE.findall(attr_str or "")}


def parse_m3u8_file(path: str | Path) -> list[Channel]:
    """Parse an M3U8 file and return a list of Channel objects."""
    text = Path(path).read_text(encoding="utf-8")
    return list(_iter_channels(text))


def parse_m3u8_text(text: str) -> list[Channel]:
    """Parse M3U8 content from a string."""
    return list(_iter_channels(text))


def _iter_channels(text: str) -> Iterator[Channel]:
    lines = iter(text.splitlines())
    for line in lines:
        line = line.strip()
        if not line.startswith("#EXTINF:"):
            continue

        m = _EXTINF_RE.match(line)
        if not m:
            continue

        attrs = _parse_attrs(m.group("attrs"))
        display_name = (m.group("name") or "").strip()

        # Find the URL line (skip blank lines and comment lines)
        url = ""
        for next_line in lines:
            next_line = next_line.strip()
            if next_line and not next_line.startswith("#"):
                url = next_line
                break

        if not url:
            continue

        tvg_id = attrs.get("tvg-id") or _slugify(display_name)
        name = attrs.get("tvg-name") or display_name

        yield Channel(
            tvg_id=tvg_id,
            name=name,
            url=url,
            logo=attrs.get("tvg-logo") or None,
            group=attrs.get("group-title") or None,
        )


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", text.lower()).strip(".")
