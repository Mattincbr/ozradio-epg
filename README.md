# Radio EPG Generator

Generate [XMLTV](https://xmltv.org/)-format EPG files for radio stations in IPTV M3U8 playlists. Includes a full web GUI for managing channels, schedules, one-off overrides, images, and a playlist builder.

## Features

- **Web GUI** — browser-based interface for all management tasks
- **Playlist builder** — import channels from pre-configured sources (ABC Australia, Matt Huisman, BBC) or any M3U8 URL; assemble and download a bespoke M3U8
- **Visual schedule editor** — tab-based per-day-pattern editor (Weekdays / Saturday / Sunday / individual days)
- **Programme overrides** — one-off events, sports coverage, or cancellations applied at EPG generation time
- **Image management** — upload station logos and programme images; logos auto-assign to channels
- **XMLTV output** — valid `<tv>`, `<channel>`, and `<programme>` elements with titles, descriptions, presenters, and timezone-aware timestamps
- **ABC Australia scraper** — scrape `https://www.abc.net.au/{city}/station-epg` pages directly from the UI or CLI
- **CLI** — headless operation for scripting and CI

## Installation

```bash
pip install -e .
# or with dev tools (pytest, responses)
pip install -e ".[dev]"
```

Requires Python ≥ 3.11.

## Quick start — Web UI

```bash
radio-epg web
# Opens at http://127.0.0.1:5000/
```

### Typical workflow

1. **Playlist Builder** → click **Load** next to a source (ABC, Matt Huisman, BBC) to browse its stations
2. **Select** the channels you want → **Import to Channels**
3. **Channels** → for each channel, click **Create Schedule** or **Edit Schedule**
4. In the **Schedule Editor**, add time slots for Weekdays / Saturday / Sunday, or click **Scrape from website** for ABC stations
5. **Overrides** → add one-off events or sports blocks that replace the regular schedule on specific dates
6. **Images** → upload station logos and programme artwork
7. **Generate EPG** → choose date range, download `epg.xml`

```bash
# Custom port / host
radio-epg web --port 8080 --host 0.0.0.0

# Use a specific working directory for data storage
radio-epg web --base-dir /srv/radio-epg
```

## Pre-configured playlist sources

| Name | URL |
|---|---|
| ABC Australia (AAC) | `https://raw.githubusercontent.com/fhdm-dev/radio/master/pl/ABC-Radio-(Australia)-AAC.m3u` |
| Matt Huisman – AU Radio | `https://i.mjh.nz/au/all/kodi-radio.m3u8` |
| BBC (Non-UK) | `https://raw.githubusercontent.com/fhdm-dev/radio/master/pl/BBC%20(Non-UK).m3u` |

Additional sources can be added in the Playlist Builder.

## Programme overrides

Overrides let you replace regular programming with one-off content:

| Type | Effect |
|---|---|
| **Event** | Replaces overlapping regular slots with the override content |
| **Sports** | Same as Event — displayed with a Sports badge |
| **Cancellation** | Removes overlapping slots (programme gap in the EPG) |

Overrides are stored in `data/overrides.json` and applied when you generate the EPG (if "Apply overrides" is checked).

## CLI usage

The CLI still works independently of the web UI:

```bash
# List channels in an M3U8
radio-epg list-channels examples/sample.m3u8

# Scrape an ABC schedule and save YAML
radio-epg scrape https://www.abc.net.au/brisbane/station-epg \
    --output schedules/abc.brisbane.yaml

# Generate a skeleton YAML to fill in manually
radio-epg init-schedule "abc.brisbane" --name "ABC Radio Brisbane" \
    --timezone "Australia/Brisbane" --output schedules/abc.brisbane.yaml

# Generate EPG from an M3U8 + schedules directory
radio-epg generate examples/sample.m3u8 --schedules-dir schedules \
    --output epg.xml --days 14

# Launch the web interface
radio-epg web --port 5000
```

## Schedule YAML format

```yaml
channel:
  id: abc.brisbane
  name: ABC Radio Brisbane
  timezone: Australia/Brisbane
  website: https://www.abc.net.au/brisbane/station-epg

schedule:
  weekdays:
    - start: "05:30"
      title: ABC News Breakfast
      description: Start your day with the latest news.
      duration: 180          # minutes; omit to run until the next slot starts

    - start: "08:30"
      title: Brisbane Mornings
      presenter: Craig Zonca and Loretta Ryan

  saturday:
    - start: "06:00"
      title: Saturday Morning
      presenter: Rebecca Levingston
      duration: 240

  sunday:
    - start: "06:00"
      title: Sunday Morning
      duration: 240
```

**Day keys** (most-specific wins): `monday`–`sunday`, `weekdays`, `weekend`, `default`.

## Data storage

All web UI state lives under the working directory:

```
data/
  channels.json       — configured channel list
  overrides.json      — programme overrides
  sources.json        — playlist source URLs
  source_cache_*.json — cached M3U8 channel lists

schedules/
  abc.brisbane.yaml   — per-channel weekly schedules

uploads/
  logos/              — uploaded station logo images
  images/             — uploaded programme images
```

## Project layout

```
radio_epg/
├── cli.py              — Click CLI (radio-epg command)
├── m3u8_parser.py      — EXTINF attribute parser
├── models.py           — Channel, TimeSlot, WeeklySchedule, Programme, ProgramOverride
├── schedule.py         — YAML loader, schedule expansion, override application
├── xml_generator.py    — XMLTV XML output
├── scrapers/
│   ├── base.py         — Abstract BaseScraper
│   └── abc_au.py       — ABC Australia scraper
└── web/
    ├── app.py          — Flask application factory
    ├── store.py        — JSON file persistence layer
    ├── routes.py       — All Flask route handlers
    ├── templates/      — Jinja2 HTML templates
    └── static/         — CSS and JavaScript

schedules/              — Weekly schedule YAML files
examples/               — Sample M3U8 playlist
tests/                  — Pytest test suite
```

## Running tests

```bash
pytest
```

35 tests covering M3U8 parsing, schedule expansion, override application, XMLTV generation, and ABC scraper (HTTP mocked).
