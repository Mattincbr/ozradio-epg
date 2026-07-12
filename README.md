# Radio EPG Generator

**Radio EPG Generator** is a web-based tool that builds Electronic Programme Guide (EPG) files
for internet radio stations. If you use an IPTV player to listen to radio online, this tool lets
you see what's on — show names, presenters, and times — instead of just a stream URL.

You run it on your computer, manage everything through a browser, and point your IPTV player at
the resulting file.

---

## Table of Contents

- [What does it do?](#what-does-it-do)
- [Before you start](#before-you-start)
- [Installation — Mac](#installation--mac)
- [Installation — Windows](#installation--windows)
- [Starting the app](#starting-the-app)
- [First-time setup](#first-time-setup)
- [Playlist Builder](#playlist-builder)
- [Managing Channels](#managing-channels)
- [Schedule Editor](#schedule-editor)
- [Programme Overrides](#programme-overrides)
- [Image Library](#image-library)
- [Generating your EPG](#generating-your-epg)
- [Using the EPG in your IPTV player](#using-the-epg-in-your-iptv-player)
- [Keeping the app up to date](#keeping-the-app-up-to-date)
- [Troubleshooting](#troubleshooting)
- [Where your data is stored](#where-your-data-is-stored)
- [Advanced: CLI reference](#advanced-cli-reference)

---

## What does it do?

IPTV players (like Kodi, Jellyfin, TiviMate, or any app that reads M3U playlists) can show an
on-screen programme guide alongside your radio stations — but only if you give them an EPG file.
This tool creates that file.

Here is the basic idea:

1. You tell it which radio stations you want (by importing from a playlist or searching Radio Browser)
2. You set up a weekly schedule for each station (or scrape it from the station's website for ABC stations)
3. Add any one-off overrides — like a big sports event or a holiday special — for specific dates
4. Click **Generate EPG** and download `epg.xml`
5. Point your IPTV player at that file, and it will show programme information alongside your stations

Everything is managed through a web interface that runs locally in your browser.

---

## Before you start

You will need:

- A computer running **macOS** or **Windows 10 / 11**
- An internet connection
- About 10 minutes

You do **not** need any prior programming experience. The instructions below will walk you through
every step, including opening a terminal window for the first time.

---

## Installation — Mac

### Step 1 — Open Terminal

Terminal is the app you use to type commands on a Mac. You will only need it to install and
start the app — once it is running you use your normal web browser.

To open Terminal:
- Press **Command + Space** to open Spotlight
- Type `Terminal` and press **Enter**

A window with a command prompt will appear. Leave it open throughout the installation.

### Step 2 — Check your Python version

Type this and press **Enter**:

```
python3 --version
```

If you see `Python 3.11` or higher (e.g. `Python 3.12.3`), skip to **Step 4**.

If you see an older version, or `command not found`, continue with Step 3.

### Step 3 — Install Python (if needed)

The easiest way on Mac is through a tool called Homebrew. If you already have Homebrew installed,
you can skip the first command.

**Install Homebrew** (paste this whole line and press Enter):

```
/bin/bash -c "$(curl -fsSL https://brew.sh/install.sh)"
```

It will ask for your Mac password. Type it (nothing will appear on screen as you type — that is
normal) and press Enter. This takes a minute or two.

**Install Python**:

```
brew install python@3.11
```

### Step 4 — Install Git (if needed)

Git is the tool used to download the app. Check if you have it:

```
git --version
```

If you see a version number, you already have it. If not, run:

```
brew install git
```

Or simply try the next step — macOS will offer to install Git automatically the first time you use it.

### Step 5 — Download the app

Choose a folder where you want to keep the app. Your home folder is fine. Then run:

```
cd ~
git clone https://github.com/Mattincbr/reimagined-octo-disco.git
cd reimagined-octo-disco
git checkout claude/radio-epg-m3u8-generator-pjhtj0
```

This creates a folder called `reimagined-octo-disco` in your home directory and downloads all the app files into it.

### Step 6 — Set up a virtual environment

A virtual environment keeps this app's dependencies separate from anything else on your Mac.
Run these three commands one at a time:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

You should see `(.venv)` appear at the start of your command prompt. That means the virtual
environment is active.

The last command installs the app and all its dependencies. It may take a minute.

### Step 7 — Run the app

```
radio-epg web --base-dir ~/radio-epg-data
```

You should see:

```
Radio EPG web interface running at http://127.0.0.1:5000/
```

Open your browser (Safari, Chrome, or Firefox) and go to:
**http://127.0.0.1:5000**

That's it — the app is running. Jump to [First-time setup](#first-time-setup).

---

## Installation — Windows

### Step 1 — Install Python

1. Go to **https://www.python.org/downloads/windows/** in your browser
2. Click the yellow **Download Python 3.x.x** button (the latest 3.11 or newer version)
3. Run the downloaded installer
4. **Important:** On the first screen, tick the box that says **"Add Python to PATH"** before
   clicking Install
5. Click **Install Now** and wait for it to finish

To check it worked, continue to Step 2.

### Step 2 — Install Git

1. Go to **https://git-scm.com/download/win** in your browser
2. Download and run the installer
3. Accept all the default settings — just keep clicking **Next** and then **Finish**

### Step 3 — Open a terminal window

Press **Windows + X** and choose **Terminal** (or **Windows PowerShell**).
Alternatively, search for **Git Bash** in the Start menu — this was installed with Git and works
very well for these commands.

### Step 4 — Check Python installed correctly

Type this and press Enter:

```
python --version
```

You should see `Python 3.11` or higher. If you see an error, try:

```
py --version
```

If neither works, revisit Step 1 and make sure you ticked "Add Python to PATH".

### Step 5 — Download the app

```
cd %USERPROFILE%
git clone https://github.com/Mattincbr/reimagined-octo-disco.git
cd reimagined-octo-disco
git checkout claude/radio-epg-m3u8-generator-pjhtj0
```

If you are using Git Bash, use `cd ~` instead of `cd %USERPROFILE%`.

### Step 6 — Set up a virtual environment

Run these three commands one at a time:

**Command Prompt or PowerShell:**
```
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

**Git Bash:**
```
python -m venv .venv
source .venv/Scripts/activate
pip install -e .
```

You should see `(.venv)` appear at the start of your prompt.

### Step 7 — Run the app

```
radio-epg web --base-dir %USERPROFILE%\radio-epg-data
```

In Git Bash:
```
radio-epg web --base-dir ~/radio-epg-data
```

Open your browser and go to: **http://127.0.0.1:5000**

---

## Starting the app

Every time you want to use the app after the initial installation, open your terminal and run:

**Mac:**
```
cd ~/reimagined-octo-disco
source .venv/bin/activate
radio-epg web --base-dir ~/radio-epg-data
```

**Windows (Command Prompt / PowerShell):**
```
cd %USERPROFILE%\reimagined-octo-disco
.venv\Scripts\activate
radio-epg web --base-dir %USERPROFILE%\radio-epg-data
```

Then open **http://127.0.0.1:5000** in your browser.

To stop the app, go back to the terminal window and press **Control + C**.

### Making it accessible from other devices

If you want to access the app from another device on your home network (like a tablet, phone, or
a TV-connected computer), use this command instead:

**Mac:**
```
radio-epg web --host 0.0.0.0 --port 5000 --base-dir ~/radio-epg-data
```

Then find your Mac's IP address in **System Settings → Network** and go to
`http://<your-mac-ip>:5000` from any device on the same Wi-Fi.

---

## First-time setup

When you first open the app, the Dashboard will be empty. Here is the recommended order to get
everything set up:

1. Go to **Playlist Builder** to add channels to your list
2. Visit **Channels** to see all your channels and check settings
3. For each channel, open the **Schedule Editor** to set up its weekly programme guide
4. Add any **Overrides** for upcoming one-off events or sports
5. Upload logos and programme images in the **Images** section
6. Go to **Generate EPG** and download your `epg.xml`

---

## Playlist Builder

The Playlist Builder is where you find and add radio stations. There are two ways to do it:

### From an M3U8 playlist source

The app comes pre-loaded with four sources:

| Source | What it contains |
|---|---|
| ABC Australia (AAC) | All ABC radio stations — national and regional |
| Matt Huisman – Australian Radio | Large collection of Australian commercial and community stations |
| BBC (Non-UK) | BBC radio stations accessible outside the United Kingdom |
| IPRD Global Catalogue | Broad international catalogue |

To use a source:
1. Go to **Playlist Builder** in the left sidebar
2. Click the refresh icon next to the source you want — the app will download the station list
3. The centre panel fills with all available channels
4. Use the **search box** or **group filter** at the top of the centre panel to find stations
5. Tick the checkbox next to each station you want
6. Click **Import to Channels** (adds them to your channel list) or **Download M3U8** (saves a
   playlist file with just those stations)

You can also add your own M3U8 source by clicking the **+** button next to the Sources heading.

### Using Radio Browser

Radio Browser is a crowdsourced global directory of over 40,000 internet radio stations.

1. Click the **Radio Browser** tab in the left panel
2. The country and genre dropdowns load automatically (this takes a few seconds on first open)
3. Choose a **country**, a **genre**, and/or type a **station name**
4. Click **Search Radio Browser**
5. Results appear in the centre panel, showing codec and bitrate for each station
6. Select stations and use **Import to Channels** or **Download M3U8** as normal

---

## Managing Channels

The **Channels** page shows everything you have imported or added manually.

### What you can do here

- **Enable / Disable** — the toggle switch on each row turns a channel on or off. Disabled
  channels are excluded from EPG generation
- **Edit** — click the pencil icon to change the channel name, stream URL, logo URL, group, or
  timezone
- **Upload a logo** — on the edit page, use the upload section to replace a URL logo with your
  own image file
- **Delete** — the bin icon removes a channel from your list (it does not delete any schedule file)

### Adding a channel manually

If you know the stream URL of a station that is not in any of the sources, click **Add Channel**
at the top of the Channels page and fill in:
- **TVG ID** — a unique identifier, e.g. `triple.j` (used to match the schedule file)
- **Display Name** — what appears in your player
- **Stream URL** — the direct stream address

---

## Schedule Editor

A schedule tells the EPG what programme is on at what time. Schedules repeat weekly, so you set
them up once and the app fills in every day automatically.

### Opening the schedule editor

From the **Channels** page, click **Create Schedule** (if none exists yet) or **Edit Schedule**
next to any channel. You can also get there from the Dashboard by clicking the calendar icon on
a channel card.

### How schedules work

The editor has a tab for each day pattern you have set up. The most common setup is:

- **Weekdays** — one pattern that applies to Monday through Friday
- **Saturday** — a different pattern for Saturday
- **Sunday** — a different pattern for Sunday

You can also create patterns for individual days (e.g. just **Monday**) if a station has a
show that only runs on one specific day.

### Adding time slots

1. Click the tab for the day pattern you want to edit (or click **Add Day Pattern** to create one)
2. Click **Add Slot** at the bottom of the table
3. Fill in:
   - **Start** — the time the programme begins (24-hour format, e.g. `06:00`)
   - **Title** — the programme name
   - **Presenter** — optional, the host's name
   - **Description** — optional, a short summary
   - **Duration** — the length in minutes. Leave blank and it will automatically end when the
     next slot begins
4. Repeat for each programme in the day
5. Click **Save Schedule** when done

Slots are sorted by start time when you save, so you can add them in any order.

### Scraping an ABC schedule automatically

For any ABC Australia station, the app can fetch the schedule directly from the ABC website:

1. Open the schedule editor for an ABC channel
2. Click **Scrape from website**
3. Enter the ABC station page URL, for example:
   `https://www.abc.net.au/brisbane/station-epg`
4. Click **Scrape & Save**

The app will download the schedule and save it automatically.

---

## Programme Overrides

Overrides let you replace the regular schedule for a specific date and time — for example, a live
cricket broadcast that replaces afternoon programming, or a public holiday special.

### Adding an override

1. Go to **Overrides** in the sidebar
2. Click **Add Override**
3. Fill in the details:
   - **Channel** — which station is affected
   - **Date** — the date of the override
   - **Start and End time** — the window that is affected
   - **Title** — what to show in the EPG for that time slot
   - **Type** — choose from:
     - **Special Event** — replaces the normal schedule with your content
     - **Sports Coverage** — same as Event, but shows a Sports label in the UI
     - **Cancellation** — removes the normal programming and leaves a gap in the EPG
   - **Image** — optional artwork for the programme
4. Click **Add Override**

The preview at the bottom of the form shows what is normally scheduled at that time, so you can
see exactly what you are replacing.

Overrides are applied when you generate the EPG if the **Apply overrides** option is checked.

### Editing or removing overrides

Use the filter bar at the top of the Overrides page to narrow down by channel or date. Click the
pencil icon to edit, or the bin icon to delete.

---

## Image Library

The **Images** page lets you upload and manage logos and programme artwork.

### Uploading a logo

Station logos can be uploaded from two places:
- **Images → Upload Image**: set Type to **Station Logo**, choose the channel, and upload
- **Channels → Edit Channel → Upload**: dedicated logo upload on the channel edit page

Supported formats: PNG, JPG, SVG, WebP, GIF (max 16 MB).

Uploaded logos take priority over any logo URL from the original playlist.

### Uploading programme images

Programme images appear in EPG-compatible players alongside show descriptions.

1. Go to **Images**
2. Click **Upload Image**
3. Set Type to **Programme Image**
4. Optionally assign it to a channel and enter the programme title it belongs to
5. Upload the file

---

## Generating your EPG

1. Go to **Generate EPG** in the sidebar
2. Set the **Start Date** (defaults to today)
3. Choose how many **Days** to cover (7 days is a good default; some players want 14)
4. Check **Apply programme overrides** if you want your one-off events included
5. Tick the channels to include (all scheduled channels are ticked by default)
6. Click **Generate & Download epg.xml**

Your browser will download a file called `epg.xml`. Keep it somewhere you can find it easily —
you will need to tell your IPTV player where it is.

You will need to regenerate this file periodically (weekly is a good routine) to keep the guide
current, and whenever you add new overrides.

---

## Using the EPG in your IPTV player

The EPG file needs to be accessible to your player. The easiest approach is to serve it from the
app itself.

### If your player is on the same device as the app

Point the player directly at the generated file:

- **Mac:** `file:///Users/yourusername/radio-epg-data/epg.xml`
  (replace `yourusername` with your actual username)
- **Windows:** copy the file path from Windows Explorer

### If your player is on a different device (TV box, phone, tablet)

You need to make the file available over your network. The simplest option is to copy the file
to a location your player can reach, or run the app with `--host 0.0.0.0` and serve the file
from there.

Alternatively, many NAS devices, Plex, and similar home media servers can serve static files.

### Linking the EPG to your M3U8 playlist

Add `x-tvg-url` to the first line of your M3U8 file so your player knows where to look for
the guide:

```
#EXTM3U x-tvg-url="http://192.168.1.100:5000/epg.xml"
```

Replace `192.168.1.100` with your Mac or PC's local IP address.

Each station in your M3U8 also needs a `tvg-id` that matches the channel ID in the EPG. When
you use the **Download M3U8** button in the Playlist Builder, this is set correctly automatically.

---

## Keeping the app up to date

When new features or fixes are released, update your local copy by running:

**Mac:**
```
cd ~/reimagined-octo-disco
source .venv/bin/activate
git pull
pip install -e .
radio-epg web --base-dir ~/radio-epg-data
```

**Windows (Command Prompt):**
```
cd %USERPROFILE%\reimagined-octo-disco
.venv\Scripts\activate
git pull
pip install -e .
radio-epg web --base-dir %USERPROFILE%\radio-epg-data
```

Your data (channels, schedules, overrides, uploads) lives in `~/radio-epg-data` and is not
affected by updates.

---

## Troubleshooting

### "command not found: radio-epg"

The virtual environment is not active. Run:

**Mac:** `source .venv/bin/activate`
**Windows:** `.venv\Scripts\activate`

Make sure you are in the `reimagined-octo-disco` folder first.

### The browser says "This site can't be reached"

The app is not running. Go to your terminal window and check for error messages. Start it
again with `radio-epg web --base-dir ~/radio-epg-data`.

If the terminal says "Address already in use", another copy of the app is already running, or
something else is using port 5000. Try a different port:
```
radio-epg web --port 5001 --base-dir ~/radio-epg-data
```
Then open **http://127.0.0.1:5001** instead.

### The Playlist Builder shows an error when loading a source

The source URL may be temporarily unavailable. Wait a minute and try the refresh button again.
If it keeps failing, the playlist URL may have changed — you can remove that source and add the
updated URL manually.

### A Radio Browser search returns no results

Try broadening your search — remove the genre filter or use a shorter station name. Radio Browser's
results depend on what stations community members have submitted, so coverage varies by country.

### The EPG shows no programme information in my player

Check that:
1. The `tvg-id` in your M3U8 matches the channel ID in the EPG file (open `epg.xml` in a text
   editor and search for the channel name)
2. The EPG covers the current date — regenerate it if it has expired
3. Your player has loaded (or refreshed) the EPG file — most players have a "refresh EPG" option

### "Python was not found" on Windows

You need to add Python to your PATH. The easiest fix is to re-run the Python installer,
choose **Modify**, and tick **Add Python to environment variables**.

---

## Where your data is stored

Everything the app creates is in the data directory you specify with `--base-dir`:

```
~/radio-epg-data/
  data/
    channels.json         Your configured channel list
    overrides.json        Programme overrides
    sources.json          Playlist source URLs
    source_cache_*.json   Cached station lists from playlist sources

  schedules/
    abc.brisbane.yaml     Weekly schedule for ABC Brisbane
    triple.j.yaml         Weekly schedule for triple j
    ...                   One file per channel

  uploads/
    logos/                Station logo images you have uploaded
    images/               Programme images you have uploaded
```

To back up everything, just copy the entire `radio-epg-data` folder.

To start fresh, delete that folder (the app will recreate it on next run).

---

## Advanced: CLI reference

If you prefer to work from the command line, all features are available without the web interface:

```bash
# List all channels in an M3U8 file
radio-epg list-channels your-playlist.m3u8

# Scrape a schedule from an ABC station page and save it
radio-epg scrape https://www.abc.net.au/brisbane/station-epg \
    --output schedules/abc.brisbane.yaml

# Create a blank schedule template to fill in manually
radio-epg init-schedule "triple.j" \
    --name "triple j" \
    --timezone "Australia/Sydney" \
    --output schedules/triple.j.yaml

# Generate an EPG from an M3U8 file and a schedules folder
radio-epg generate your-playlist.m3u8 \
    --schedules-dir schedules \
    --output epg.xml \
    --days 14

# Launch the web interface
radio-epg web --host 0.0.0.0 --port 5000 --base-dir ~/radio-epg-data
```

---

*Built with Python, Flask, and Bootstrap. Data from [Radio Browser](https://www.radio-browser.info/).*
