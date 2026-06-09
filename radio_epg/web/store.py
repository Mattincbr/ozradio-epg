"""JSON-file backed data store for the web UI."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional


# Default playlist sources pre-loaded on first run
DEFAULT_SOURCES = [
    {
        "id": "abc_australia_aac",
        "name": "ABC Australia (AAC)",
        "url": "https://raw.githubusercontent.com/fhdm-dev/radio/master/pl/ABC-Radio-(Australia)-AAC.m3u",
        "description": "Australian Broadcasting Corporation radio stations (AAC streams)",
    },
    {
        "id": "mjh_australia",
        "name": "Matt Huisman – Australian Radio",
        "url": "https://i.mjh.nz/au/all/kodi-radio.m3u8",
        "description": "Comprehensive Australian radio playlist by Matt Huisman",
    },
    {
        "id": "bbc_nonuk",
        "name": "BBC (Non-UK)",
        "url": "https://raw.githubusercontent.com/fhdm-dev/radio/master/pl/BBC%20(Non-UK).m3u",
        "description": "BBC radio stations accessible outside the UK",
    },
    {
        "id": "iprd_global",
        "name": "IPRD Global Catalogue",
        "url": "https://iprd-org.github.io/iprd/site_data/all_stations.m3u",
        "description": "Internet Protocol Radio Directory — global station catalogue",
    },
]


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self, name: str, default=None):
        path = self.data_dir / f"{name}.json"
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _write(self, name: str, data: dict) -> None:
        path = self.data_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def get_channels(self) -> list[dict]:
        return self._read("channels", {"channels": []})["channels"]

    def save_channels(self, channels: list[dict]) -> None:
        self._write("channels", {"channels": channels})

    def get_channel(self, tvg_id: str) -> Optional[dict]:
        return next((c for c in self.get_channels() if c["tvg_id"] == tvg_id), None)

    def upsert_channel(self, channel: dict) -> None:
        channels = self.get_channels()
        idx = next((i for i, c in enumerate(channels) if c["tvg_id"] == channel["tvg_id"]), None)
        if idx is not None:
            channels[idx] = {**channels[idx], **channel}
        else:
            channel.setdefault("enabled", True)
            channels.append(channel)
        self.save_channels(channels)

    def delete_channel(self, tvg_id: str) -> None:
        self.save_channels([c for c in self.get_channels() if c["tvg_id"] != tvg_id])

    def toggle_channel(self, tvg_id: str) -> bool:
        channels = self.get_channels()
        for ch in channels:
            if ch["tvg_id"] == tvg_id:
                ch["enabled"] = not ch.get("enabled", True)
                self.save_channels(channels)
                return ch["enabled"]
        return False

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def get_overrides(self, channel_id: Optional[str] = None) -> list[dict]:
        overrides = self._read("overrides", {"overrides": []})["overrides"]
        if channel_id:
            return [o for o in overrides if o["channel_id"] == channel_id]
        return overrides

    def add_override(self, override: dict) -> dict:
        override["id"] = override.get("id") or str(uuid.uuid4())[:8]
        data = self._read("overrides", {"overrides": []})
        data["overrides"].append(override)
        self._write("overrides", data)
        return override

    def update_override(self, override_id: str, updates: dict) -> Optional[dict]:
        data = self._read("overrides", {"overrides": []})
        for ov in data["overrides"]:
            if ov["id"] == override_id:
                ov.update(updates)
                self._write("overrides", data)
                return ov
        return None

    def delete_override(self, override_id: str) -> None:
        data = self._read("overrides", {"overrides": []})
        data["overrides"] = [o for o in data["overrides"] if o["id"] != override_id]
        self._write("overrides", data)

    # ------------------------------------------------------------------
    # Playlist sources
    # ------------------------------------------------------------------

    def get_sources(self) -> list[dict]:
        data = self._read("sources", None)
        if data is None:
            # First run: seed with defaults
            self._write("sources", {"sources": DEFAULT_SOURCES})
            return list(DEFAULT_SOURCES)
        sources = data.get("sources", [])
        # Backfill any default sources added since first run
        existing_ids = {s["id"] for s in sources}
        added = [s for s in DEFAULT_SOURCES if s["id"] not in existing_ids]
        if added:
            sources = sources + added
            self._write("sources", {"sources": sources})
        return sources

    def save_sources(self, sources: list[dict]) -> None:
        self._write("sources", {"sources": sources})

    def get_source(self, source_id: str) -> Optional[dict]:
        return next((s for s in self.get_sources() if s["id"] == source_id), None)

    def add_source(self, source: dict) -> dict:
        source["id"] = source.get("id") or str(uuid.uuid4())[:8]
        sources = self.get_sources()
        sources.append(source)
        self.save_sources(sources)
        return source

    def delete_source(self, source_id: str) -> None:
        sources = [s for s in self.get_sources() if s["id"] != source_id]
        self.save_sources(sources)
        # Also delete cached channels
        cache = self.data_dir / f"source_cache_{source_id}.json"
        if cache.exists():
            cache.unlink()

    def cache_source_channels(self, source_id: str, channels: list[dict]) -> None:
        self._write(f"source_cache_{source_id}", {"channels": channels})

    def get_cached_source_channels(self, source_id: str) -> Optional[list[dict]]:
        data = self._read(f"source_cache_{source_id}", None)
        if data is None:
            return None
        return data.get("channels", [])

    # ------------------------------------------------------------------
    # Images metadata
    # ------------------------------------------------------------------

    def get_images(self) -> list[dict]:
        return self._read("images", {"images": []})["images"]

    def add_image(self, image: dict) -> dict:
        image["id"] = image.get("id") or str(uuid.uuid4())[:8]
        data = self._read("images", {"images": []})
        data["images"].append(image)
        self._write("images", data)
        return image

    def delete_image(self, image_id: str) -> Optional[dict]:
        data = self._read("images", {"images": []})
        removed = next((i for i in data["images"] if i["id"] == image_id), None)
        data["images"] = [i for i in data["images"] if i["id"] != image_id]
        self._write("images", data)
        return removed
