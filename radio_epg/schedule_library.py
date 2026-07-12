"""Built-in schedule template library.

Templates are YAML files in radio_epg/data/schedules/.  Each file must have a
``_meta`` section with at least ``id``, ``display_name`` and ``match`` keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

_LIBRARY_DIR = Path(__file__).parent / "data" / "schedules"


def list_templates() -> list[dict]:
    """Return metadata dicts for all bundled templates, sorted by display name."""
    templates = []
    for path in sorted(_LIBRARY_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            if not meta.get("id"):
                continue
            templates.append({
                "id":          meta["id"],
                "name":        meta.get("display_name", meta["id"]),
                "description": meta.get("description", ""),
                "country":     meta.get("country", ""),
                "notes":       meta.get("notes", ""),
                "match":       meta.get("match", []),
            })
        except Exception:
            continue
    return sorted(templates, key=lambda t: t["name"].lower())


def match_templates(channel_name: str) -> list[dict]:
    """Return templates whose match keywords appear in *channel_name*."""
    name_lower = channel_name.lower()
    return [
        t for t in list_templates()
        if any(kw.lower() in name_lower for kw in t["match"])
    ]


def load_template_days(template_id: str) -> Optional[dict[str, list[dict]]]:
    """Load a template by ID and return its schedule as {day: [slot, ...]} dict.

    Each slot is ``{"start": "HH:MM", "title": "…", "description"?: "…"}``.
    Returns None if the template is not found.
    """
    for path in _LIBRARY_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if data.get("_meta", {}).get("id") != template_id:
                continue
            days: dict[str, list[dict]] = {}
            for day_key, slots_raw in (data.get("schedule") or {}).items():
                days[day_key] = [
                    {k: v for k, v in {
                        "start":       str(s.get("start", "")),
                        "title":       s.get("title", ""),
                        "description": s.get("description", ""),
                        "presenter":   s.get("presenter", ""),
                        "duration":    s.get("duration"),
                    }.items() if v}
                    for s in (slots_raw or [])
                    if s.get("start") and s.get("title")
                ]
            return days
        except Exception:
            continue
    return None
