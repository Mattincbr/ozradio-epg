"""Generate XMLTV-format EPG XML from channels and programmes."""

from __future__ import annotations

from datetime import datetime
from typing import IO
from xml.etree import ElementTree as ET
from xml.dom import minidom

from .models import Channel, Programme


_XMLTV_DATE_FMT = "%Y%m%d%H%M%S %z"


def generate_xmltv(
    channels: list[Channel],
    programmes: list[Programme],
    source_name: str = "radio-epg-generator",
) -> str:
    """Return a pretty-printed XMLTV XML string."""
    root = ET.Element("tv")
    root.set("source-info-name", source_name)
    root.set("generator-info-name", "radio-epg")

    # Deduplicate channels — only include ones that have programmes
    channel_ids_with_programmes = {p.channel_id for p in programmes}
    seen: set[str] = set()

    for ch in channels:
        if ch.tvg_id not in channel_ids_with_programmes:
            continue
        if ch.tvg_id in seen:
            continue
        seen.add(ch.tvg_id)
        _add_channel(root, ch)

    for prog in sorted(programmes, key=lambda p: p.start):
        _add_programme(root, prog)

    return _pretty(root)


def write_xmltv(
    channels: list[Channel],
    programmes: list[Programme],
    output: IO[str] | str,
    source_name: str = "radio-epg-generator",
) -> None:
    """Write XMLTV XML to a file path or file-like object."""
    xml = generate_xmltv(channels, programmes, source_name)
    if isinstance(output, str):
        with open(output, "w", encoding="utf-8") as f:
            f.write(xml)
    else:
        output.write(xml)


def _add_channel(root: ET.Element, ch: Channel) -> None:
    el = ET.SubElement(root, "channel")
    el.set("id", ch.tvg_id)
    name_el = ET.SubElement(el, "display-name")
    name_el.text = ch.name
    if ch.logo:
        icon = ET.SubElement(el, "icon")
        icon.set("src", ch.logo)


def _add_programme(root: ET.Element, prog: Programme) -> None:
    el = ET.SubElement(root, "programme")
    el.set("start", _fmt_dt(prog.start))
    el.set("stop", _fmt_dt(prog.stop))
    el.set("channel", prog.channel_id)

    title_el = ET.SubElement(el, "title")
    title_el.set("lang", "en")
    title_el.text = prog.title

    if prog.description or prog.presenter:
        desc_parts = []
        if prog.description:
            desc_parts.append(prog.description)
        if prog.presenter:
            desc_parts.append(f"Presenter: {prog.presenter}")
        desc_el = ET.SubElement(el, "desc")
        desc_el.set("lang", "en")
        desc_el.text = "  ".join(desc_parts)

    if prog.presenter:
        credits_el = ET.SubElement(el, "credits")
        presenter_el = ET.SubElement(credits_el, "presenter")
        presenter_el.text = prog.presenter


def _fmt_dt(dt: datetime) -> str:
    # XMLTV format: "20260601060000 +1000"
    s = dt.strftime("%Y%m%d%H%M%S ")
    offset = dt.strftime("%z")          # e.g. "+1000"
    return s + offset


def _pretty(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="unicode", xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')
    return dom.toprettyxml(indent="  ", encoding=None)
