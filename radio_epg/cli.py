"""Command-line interface for the Radio EPG generator."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import click
import yaml

from .m3u8_parser import parse_m3u8_file, parse_m3u8_text
from .models import Channel
from .schedule import expand_schedule, load_schedule_dict, load_schedule_yaml
from .scrapers.abc_au import ABCScraper
from .scrapers.base import ScraperError
from .xml_generator import write_xmltv


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option()
def cli():
    """Generate XMLTV EPG files for radio stations in IPTV M3U8 playlists."""


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@cli.command("list-channels")
@click.argument("m3u8_file", type=click.Path(exists=True))
def list_channels(m3u8_file: str):
    """List all channels found in an M3U8 file."""
    channels = parse_m3u8_file(m3u8_file)
    if not channels:
        click.echo("No channels found.")
        return
    click.echo(f"Found {len(channels)} channel(s):\n")
    for ch in channels:
        group = f"  [{ch.group}]" if ch.group else ""
        logo = f"  logo={ch.logo}" if ch.logo else ""
        click.echo(f"  {ch.tvg_id:<30} {ch.name}{group}{logo}")


@cli.command("scrape")
@click.argument("url")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write schedule YAML to this file (default: stdout)")
@click.option("--timezone", "-t", default=None,
              help="Override timezone (e.g. Australia/Brisbane)")
def scrape(url: str, output: str | None, timezone: str | None):
    """Scrape a station schedule page and output a YAML schedule file.

    Currently supports ABC Australia station pages:
      https://www.abc.net.au/brisbane/station-epg
    """
    scraper = _pick_scraper(url)
    if scraper is None:
        raise click.ClickException(f"No scraper available for URL: {url}")

    click.echo(f"Scraping {url} ...", err=True)
    try:
        schedule = scraper.scrape(url)
    except ScraperError as exc:
        raise click.ClickException(str(exc))

    if timezone:
        schedule.timezone = timezone

    data = _schedule_to_dict(schedule)
    text = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(text)


@cli.command("generate")
@click.argument("m3u8_file", type=click.Path(exists=True))
@click.option("--schedules-dir", "-s", type=click.Path(exists=True), default="schedules",
              show_default=True,
              help="Directory containing YAML schedule files named <tvg-id>.yaml")
@click.option("--output", "-o", type=click.Path(), default="epg.xml",
              show_default=True, help="Output XMLTV file path")
@click.option("--days", "-d", default=7, show_default=True,
              help="Number of days of EPG to generate")
@click.option("--start-date", default=None,
              help="Start date (YYYY-MM-DD, default: today)")
@click.option("--scrape-missing/--no-scrape-missing", default=False,
              help="Auto-scrape schedule for stations that have a website in their YAML")
def generate(
    m3u8_file: str,
    schedules_dir: str,
    output: str,
    days: int,
    start_date: str | None,
    scrape_missing: bool,
):
    """Generate an XMLTV EPG file from an M3U8 playlist.

    \b
    For each channel in the M3U8 file the tool looks for a corresponding
    YAML schedule in SCHEDULES_DIR/<tvg-id>.yaml.  Run the 'scrape' command
    first to create those files, or write them by hand.
    """
    start = date.fromisoformat(start_date) if start_date else date.today()
    channels = parse_m3u8_file(m3u8_file)
    click.echo(f"Loaded {len(channels)} channel(s) from {m3u8_file}", err=True)

    all_programmes = []
    sched_dir = Path(schedules_dir)

    for ch in channels:
        yaml_path = sched_dir / f"{ch.tvg_id}.yaml"
        if not yaml_path.exists():
            # Try with dots replaced by hyphens / underscores
            alt = sched_dir / f"{ch.tvg_id.replace('.', '-')}.yaml"
            if alt.exists():
                yaml_path = alt
            else:
                click.echo(f"  [skip] No schedule for {ch.tvg_id}", err=True)
                continue

        try:
            schedule = load_schedule_yaml(yaml_path)
        except Exception as exc:
            click.echo(f"  [warn] Could not load {yaml_path}: {exc}", err=True)
            continue

        progs = expand_schedule(schedule, start, days)
        click.echo(f"  {ch.tvg_id}: {len(progs)} programme slots", err=True)
        all_programmes.extend(progs)

    if not all_programmes:
        click.echo("No programmes generated — check your schedule files.", err=True)
        sys.exit(1)

    write_xmltv(channels, all_programmes, output)
    click.echo(f"\nWrote {len(all_programmes)} programme(s) to {output}", err=True)


@cli.command("init-schedule")
@click.argument("channel_id")
@click.option("--name", default=None, help="Display name of the channel")
@click.option("--timezone", default="UTC", show_default=True)
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write to file (default: stdout)")
def init_schedule(channel_id: str, name: str | None, timezone: str, output: str | None):
    """Generate a skeleton YAML schedule file for a channel."""
    template = {
        "channel": {
            "id": channel_id,
            "name": name or channel_id,
            "timezone": timezone,
            "website": None,
        },
        "schedule": {
            "weekdays": [
                {"start": "06:00", "title": "Morning Show", "presenter": "Host Name",
                 "description": "Your weekday morning show.", "duration": 180},
                {"start": "09:00", "title": "Mid Morning", "presenter": "",
                 "description": "", "duration": 180},
                {"start": "12:00", "title": "Midday Show", "presenter": "",
                 "description": "", "duration": 120},
                {"start": "14:00", "title": "Afternoon Drive", "presenter": "",
                 "description": "", "duration": 180},
                {"start": "17:00", "title": "Drive", "presenter": "",
                 "description": "", "duration": 120},
                {"start": "19:00", "title": "Evening", "presenter": "",
                 "description": "", "duration": 180},
                {"start": "22:00", "title": "Overnight", "presenter": "",
                 "description": "", "duration": None},
            ],
            "saturday": [
                {"start": "06:00", "title": "Saturday Morning", "presenter": "",
                 "description": "", "duration": 240},
                {"start": "10:00", "title": "Weekend Music", "presenter": "",
                 "description": "", "duration": None},
            ],
            "sunday": [
                {"start": "06:00", "title": "Sunday Morning", "presenter": "",
                 "description": "", "duration": 240},
                {"start": "10:00", "title": "Weekend Music", "presenter": "",
                 "description": "", "duration": None},
            ],
        },
    }

    text = yaml.dump(template, allow_unicode=True, default_flow_style=False, sort_keys=False)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(text)


@cli.command("web")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address")
@click.option("--port", default=5000, show_default=True, help="Port number")
@click.option("--debug/--no-debug", default=False, help="Enable Flask debug mode")
@click.option("--base-dir", default=".", show_default=True,
              help="Base directory for data/, schedules/ and uploads/")
def web(host: str, port: int, debug: bool, base_dir: str):
    """Launch the Radio EPG web interface.

    \b
    Serves a browser-based GUI for:
      - Importing channels from M3U8 playlist sources
      - Editing weekly schedules visually
      - Managing one-off overrides (events, sports, cancellations)
      - Uploading station logos and programme images
      - Generating and downloading XMLTV EPG files
    """
    from .web.app import create_app
    app = create_app(base_dir)
    click.echo(f"Radio EPG web interface running at http://{host}:{port}/", err=True)
    app.run(host=host, port=port, debug=debug)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_scraper(url: str):
    if "abc.net.au" in url:
        return ABCScraper()
    return None


def _schedule_to_dict(schedule) -> dict:
    days_data = {}
    for day_key, day_sched in schedule.days.items():
        slots = []
        for slot in day_sched.slots:
            s: dict = {"start": slot.start, "title": slot.title}
            if slot.presenter:
                s["presenter"] = slot.presenter
            if slot.description:
                s["description"] = slot.description
            if slot.duration is not None:
                s["duration"] = slot.duration
            slots.append(s)
        days_data[day_key] = slots

    return {
        "channel": {
            "id": schedule.channel_id,
            "name": schedule.channel_name,
            "timezone": schedule.timezone,
            "website": schedule.source_url,
        },
        "schedule": days_data,
    }
