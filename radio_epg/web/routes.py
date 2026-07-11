"""All Flask route handlers for the Radio EPG web interface."""

from __future__ import annotations

import io
import os
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from ..m3u8_parser import parse_m3u8_text
from ..models import ProgramOverride
from ..schedule import apply_overrides, expand_schedule, load_schedule_dict, load_schedule_yaml
from ..scrapers.abc_au import ABCScraper
from ..scrapers.base import ScraperError
from ..xml_generator import generate_xmltv

_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def register_routes(app: Flask) -> None:

    # ------------------------------------------------------------------ helpers

    def store():
        return current_app.config["STORE"]

    def schedules_dir() -> Path:
        return current_app.config["SCHEDULES_DIR"]

    def uploads_dir() -> Path:
        return current_app.config["UPLOADS_DIR"]

    def schedule_path(tvg_id: str) -> Path:
        return schedules_dir() / f"{tvg_id}.yaml"

    def has_schedule(tvg_id: str) -> bool:
        return schedule_path(tvg_id).exists()

    def channel_logo_url(ch: dict) -> str:
        """Return the best available logo URL for a channel dict."""
        local = ch.get("local_logo")
        if local:
            return url_for("uploaded_file", path=f"logos/{local}")
        return ch.get("logo") or ch.get("tvg_logo") or ""

    app.jinja_env.globals["channel_logo_url"] = channel_logo_url
    app.jinja_env.globals["has_schedule"] = has_schedule

    # ------------------------------------------------------------------ static

    @app.route("/uploads/<path:path>")
    def uploaded_file(path: str):
        return send_from_directory(current_app.config["UPLOADS_DIR"], path)

    # ------------------------------------------------------------------ dashboard

    @app.route("/")
    def dashboard():
        channels = store().get_channels()
        enabled = [c for c in channels if c.get("enabled", True)]
        with_sched = [c for c in enabled if has_schedule(c["tvg_id"])]
        overrides = store().get_overrides()
        upcoming = sorted(
            [o for o in overrides if o.get("date", "") >= date.today().isoformat()],
            key=lambda o: (o["date"], o["start"]),
        )[:10]
        return render_template(
            "dashboard.html",
            channels=channels,
            enabled_count=len(enabled),
            scheduled_count=len(with_sched),
            override_count=len(overrides),
            upcoming_overrides=upcoming,
        )

    # ------------------------------------------------------------------ channels

    @app.route("/channels")
    def channels():
        all_channels = store().get_channels()
        return render_template("channels.html", channels=all_channels)

    @app.route("/channels/add", methods=["POST"])
    def channel_add():
        tvg_id = request.form.get("tvg_id", "").strip()
        name = request.form.get("name", "").strip()
        url = request.form.get("url", "").strip()
        if not (tvg_id and name and url):
            flash("tvg-id, name, and URL are required.", "danger")
            return redirect(url_for("channels"))
        store().upsert_channel({
            "tvg_id": tvg_id,
            "name": name,
            "url": url,
            "logo": request.form.get("logo", "").strip() or None,
            "group": request.form.get("group", "").strip() or None,
            "timezone": request.form.get("timezone", "UTC"),
            "enabled": True,
            "source": "manual",
        })
        flash(f"Channel '{name}' added.", "success")
        return redirect(url_for("channels"))

    @app.route("/channels/<tvg_id>/edit", methods=["GET", "POST"])
    def channel_edit(tvg_id: str):
        ch = store().get_channel(tvg_id)
        if not ch:
            abort(404)
        if request.method == "POST":
            ch["name"] = request.form.get("name", ch["name"]).strip()
            ch["url"] = request.form.get("url", ch["url"]).strip()
            ch["logo"] = request.form.get("logo", "").strip() or ch.get("logo")
            ch["group"] = request.form.get("group", "").strip() or None
            ch["timezone"] = request.form.get("timezone", "UTC")
            store().upsert_channel(ch)
            flash("Channel updated.", "success")
            return redirect(url_for("channel_edit", tvg_id=tvg_id))
        return render_template("channel_edit.html", channel=ch, timezones=_common_timezones())

    @app.route("/channels/<tvg_id>/delete", methods=["POST"])
    def channel_delete(tvg_id: str):
        ch = store().get_channel(tvg_id)
        name = ch["name"] if ch else tvg_id
        store().delete_channel(tvg_id)
        flash(f"Channel '{name}' removed.", "success")
        return redirect(url_for("channels"))

    @app.route("/channels/<tvg_id>/toggle", methods=["POST"])
    def channel_toggle(tvg_id: str):
        enabled = store().toggle_channel(tvg_id)
        return jsonify({"enabled": enabled})

    @app.route("/channels/<tvg_id>/upload-logo", methods=["POST"])
    def channel_upload_logo(tvg_id: str):
        ch = store().get_channel(tvg_id)
        if not ch:
            abort(404)
        f = request.files.get("logo")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return redirect(url_for("channel_edit", tvg_id=tvg_id))
        ext = Path(f.filename).suffix.lower()
        if ext not in _ALLOWED_IMAGE_EXTS:
            flash("File type not allowed.", "danger")
            return redirect(url_for("channel_edit", tvg_id=tvg_id))
        filename = secure_filename(f"{tvg_id}{ext}")
        f.save(uploads_dir() / "logos" / filename)
        ch["local_logo"] = filename
        store().upsert_channel(ch)
        flash("Logo uploaded.", "success")
        return redirect(url_for("channel_edit", tvg_id=tvg_id))

    # ------------------------------------------------------------------ schedule

    @app.route("/schedule/<tvg_id>", methods=["GET", "POST"])
    def schedule_edit(tvg_id: str):
        ch = store().get_channel(tvg_id)
        if not ch:
            abort(404)

        if request.method == "POST":
            # Expect JSON body: { "weekdays": [...], "saturday": [...], ... }
            payload = request.get_json(force=True, silent=True) or {}
            _save_schedule(tvg_id, ch, payload)
            return jsonify({"success": True})

        # GET: load existing schedule or return empty
        existing: dict = {}
        if has_schedule(tvg_id):
            try:
                raw = yaml.safe_load(schedule_path(tvg_id).read_text(encoding="utf-8"))
                existing = raw.get("schedule", {})
            except Exception:
                existing = {}

        return render_template(
            "schedule_edit.html",
            channel=ch,
            schedule=existing,
            timezones=_common_timezones(),
        )

    @app.route("/schedule/<tvg_id>/scrape", methods=["POST"])
    def schedule_scrape(tvg_id: str):
        ch = store().get_channel(tvg_id)
        if not ch:
            abort(404)
        scrape_url = request.form.get("url", "").strip()
        if not scrape_url:
            flash("No URL provided.", "danger")
            return redirect(url_for("schedule_edit", tvg_id=tvg_id))

        scraper = _pick_scraper(scrape_url)
        try:
            weekly = scraper.scrape(scrape_url)
            schedule_dict: dict = _weekly_to_dict(weekly)
            _save_schedule(tvg_id, ch, schedule_dict,
                           timezone=weekly.timezone)
            flash("Schedule scraped and saved.", "success")
        except ScraperError as exc:
            flash(f"Scrape failed: {exc}", "danger")
        return redirect(url_for("schedule_edit", tvg_id=tvg_id))

    @app.route("/api/schedule/<tvg_id>/import", methods=["POST"])
    def schedule_import_api(tvg_id: str):
        """AJAX import endpoint: URL / text / image → {ok, days}."""
        ch = store().get_channel(tvg_id)
        if not ch:
            return jsonify({"ok": False, "error": "Channel not found"}), 404

        ct = request.content_type or ""
        if "multipart" in ct:
            import_type = request.form.get("type", "image")
        else:
            body = request.get_json(silent=True) or {}
            import_type = body.get("type", "url")

        try:
            if import_type == "url":
                url = body.get("url", "").strip()
                if not url:
                    return jsonify({"ok": False, "error": "No URL provided"})
                scraper = _pick_scraper(url)
                weekly = scraper.scrape(url)
                days = _weekly_to_dict(weekly)
                return jsonify({"ok": True, "days": days})

            elif import_type == "text":
                text = body.get("text", "").strip()
                default_day = body.get("day", "weekdays")
                if not text:
                    return jsonify({"ok": False, "error": "No text provided"})
                from ..scrapers.text_parser import parse_schedule_text
                days = parse_schedule_text(text, default_day=default_day)
                if not days:
                    return jsonify({"ok": False, "error": "No schedule slots found in the pasted text."})
                return jsonify({"ok": True, "days": days})

            elif import_type == "image":
                api_key = (
                    store().get_setting("anthropic_api_key", "") or
                    os.environ.get("ANTHROPIC_API_KEY", "")
                )
                if not api_key:
                    return jsonify({
                        "ok": False,
                        "error": "No Anthropic API key configured. Add one in Settings.",
                    })
                file = request.files.get("file")
                if not file:
                    return jsonify({"ok": False, "error": "No image file uploaded"})
                image_bytes = file.read()
                ext = Path(secure_filename(file.filename or "img.jpg")).suffix.lower()
                media_type = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
                }.get(ext, "image/jpeg")
                from ..scrapers.image_parser import parse_image_with_claude
                days = parse_image_with_claude(image_bytes, media_type, api_key)
                if not days:
                    return jsonify({"ok": False, "error": "No schedule data found in the image."})
                return jsonify({"ok": True, "days": days})

            else:
                return jsonify({"ok": False, "error": f"Unknown import type: {import_type}"})

        except ScraperError as exc:
            return jsonify({"ok": False, "error": str(exc)})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Import failed: {exc}"})

    @app.route("/api/schedule-library")
    def schedule_library_list():
        from ..schedule_library import list_templates, match_templates
        name = request.args.get("match", "")
        templates = match_templates(name) if name else list_templates()
        return jsonify({"templates": templates})

    @app.route("/api/schedule-library/<template_id>")
    def schedule_library_get(template_id: str):
        from ..schedule_library import load_template_days
        days = load_template_days(template_id)
        if days is None:
            return jsonify({"ok": False, "error": "Template not found"}), 404
        return jsonify({"ok": True, "days": days})

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            api_key = request.form.get("anthropic_api_key", "").strip()
            store().set_setting("anthropic_api_key", api_key)
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        current = store().get_settings()
        return render_template("settings.html", settings=current)

    def _weekly_to_dict(weekly) -> dict:
        days = {}
        for day_key, day_sched in weekly.days.items():
            days[day_key] = [
                {k: v for k, v in {
                    "start": s.start,
                    "title": s.title,
                    "presenter": s.presenter,
                    "description": s.description,
                    "duration": s.duration,
                    "image": s.image,
                    "url": s.url,
                }.items() if v}
                for s in day_sched.slots
            ]
        return days

    def _save_schedule(tvg_id: str, ch: dict, schedule_dict: dict,
                       timezone: str | None = None) -> None:
        tz = timezone or ch.get("timezone", "UTC")
        data = {
            "channel": {
                "id": tvg_id,
                "name": ch.get("name", tvg_id),
                "timezone": tz,
                "website": ch.get("website"),
            },
            "schedule": schedule_dict,
        }
        schedule_path(tvg_id).write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ overrides

    @app.route("/overrides")
    def overrides():
        channel_filter = request.args.get("channel", "")
        date_filter = request.args.get("date", "")
        all_overrides = store().get_overrides(channel_filter or None)
        if date_filter:
            all_overrides = [o for o in all_overrides if o.get("date", "") == date_filter]
        all_overrides.sort(key=lambda o: (o.get("date", ""), o.get("start", "")))
        channels = store().get_channels()
        return render_template(
            "overrides.html",
            overrides=all_overrides,
            channels=channels,
            channel_filter=channel_filter,
            date_filter=date_filter,
        )

    @app.route("/overrides/add", methods=["POST"])
    def override_add():
        ov = {
            "channel_id": request.form.get("channel_id", ""),
            "date": request.form.get("date", ""),
            "start": request.form.get("start", ""),
            "end": request.form.get("end", ""),
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "override_type": request.form.get("override_type", "event"),
        }
        if not all([ov["channel_id"], ov["date"], ov["start"], ov["end"], ov["title"]]):
            flash("All fields except description are required.", "danger")
            return redirect(url_for("overrides"))

        # Optional image upload
        img = request.files.get("image")
        if img and img.filename:
            ext = Path(img.filename).suffix.lower()
            if ext in _ALLOWED_IMAGE_EXTS:
                fname = secure_filename(f"override_{ov['date']}_{ov['start'].replace(':','')}_{ov['channel_id']}{ext}")
                img.save(uploads_dir() / "images" / fname)
                ov["image"] = fname

        store().add_override(ov)
        flash("Override added.", "success")
        return redirect(url_for("overrides"))

    @app.route("/overrides/<override_id>/delete", methods=["POST"])
    def override_delete(override_id: str):
        store().delete_override(override_id)
        flash("Override removed.", "success")
        return redirect(url_for("overrides"))

    @app.route("/overrides/<override_id>/edit", methods=["GET", "POST"])
    def override_edit(override_id: str):
        all_ov = store().get_overrides()
        ov = next((o for o in all_ov if o["id"] == override_id), None)
        if not ov:
            abort(404)
        if request.method == "POST":
            ov.update({
                "channel_id": request.form.get("channel_id", ov["channel_id"]),
                "date": request.form.get("date", ov["date"]),
                "start": request.form.get("start", ov["start"]),
                "end": request.form.get("end", ov["end"]),
                "title": request.form.get("title", ov["title"]).strip(),
                "description": request.form.get("description", "").strip(),
                "override_type": request.form.get("override_type", ov.get("override_type", "event")),
            })
            img = request.files.get("image")
            if img and img.filename:
                ext = Path(img.filename).suffix.lower()
                if ext in _ALLOWED_IMAGE_EXTS:
                    fname = secure_filename(f"override_{ov['id']}{ext}")
                    img.save(uploads_dir() / "images" / fname)
                    ov["image"] = fname
            store().update_override(override_id, ov)
            flash("Override updated.", "success")
            return redirect(url_for("overrides"))
        channels = store().get_channels()
        return render_template("override_edit.html", override=ov, channels=channels)

    # ------------------------------------------------------------------ images

    @app.route("/images")
    def images():
        imgs = store().get_images()
        channels = store().get_channels()
        ch_map = {c["tvg_id"]: c["name"] for c in channels}
        return render_template("images.html", images=imgs, ch_map=ch_map)

    @app.route("/images/upload", methods=["POST"])
    def image_upload():
        f = request.files.get("file")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return redirect(url_for("images"))
        ext = Path(f.filename).suffix.lower()
        if ext not in _ALLOWED_IMAGE_EXTS:
            flash("Unsupported file type.", "danger")
            return redirect(url_for("images"))

        img_type = request.form.get("img_type", "programme")  # "logo" or "programme"
        channel_id = request.form.get("channel_id", "").strip()
        programme_title = request.form.get("programme_title", "").strip()
        original_name = Path(secure_filename(f.filename)).stem
        subdir = "logos" if img_type == "logo" else "images"
        prefix = f"{channel_id}_" if channel_id else ""
        filename = secure_filename(f"{prefix}{original_name}{ext}")
        save_path = uploads_dir() / subdir / filename
        f.save(save_path)

        store().add_image({
            "filename": filename,
            "path": f"{subdir}/{filename}",
            "type": img_type,
            "channel_id": channel_id or None,
            "programme_title": programme_title or None,
        })

        if img_type == "logo" and channel_id:
            ch = store().get_channel(channel_id)
            if ch:
                ch["local_logo"] = filename
                store().upsert_channel(ch)

        flash(f"Image '{filename}' uploaded.", "success")
        return redirect(url_for("images"))

    @app.route("/images/<image_id>/delete", methods=["POST"])
    def image_delete(image_id: str):
        removed = store().delete_image(image_id)
        if removed:
            fpath = uploads_dir() / removed["path"]
            if fpath.exists():
                fpath.unlink()
        flash("Image deleted.", "success")
        return redirect(url_for("images"))

    # ------------------------------------------------------------------ playlist builder

    @app.route("/playlist")
    def playlist():
        sources = store().get_sources()
        # Annotate with cached channel counts
        for src in sources:
            cached = store().get_cached_source_channels(src["id"])
            src["cached_count"] = len(cached) if cached is not None else None
        configured_ids = {c["tvg_id"] for c in store().get_channels()}
        return render_template(
            "playlist.html",
            sources=sources,
            configured_ids=list(configured_ids),
        )

    @app.route("/playlist/sources/add", methods=["POST"])
    def source_add():
        src = {
            "name": request.form.get("name", "").strip(),
            "url": request.form.get("url", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        if not src["name"] or not src["url"]:
            flash("Name and URL are required.", "danger")
            return redirect(url_for("playlist"))
        store().add_source(src)
        flash(f"Source '{src['name']}' added.", "success")
        return redirect(url_for("playlist"))

    @app.route("/playlist/sources/<source_id>/delete", methods=["POST"])
    def source_delete(source_id: str):
        store().delete_source(source_id)
        flash("Source removed.", "success")
        return redirect(url_for("playlist"))

    @app.route("/api/sources/<source_id>/channels")
    def api_source_channels(source_id: str):
        src = store().get_source(source_id)
        if not src:
            return jsonify({"error": "Source not found"}), 404

        # Return cached version if available and not force-refresh
        if not request.args.get("refresh"):
            cached = store().get_cached_source_channels(source_id)
            if cached is not None:
                return jsonify({"channels": cached, "cached": True})

        try:
            resp = requests.get(src["url"], timeout=30, headers={
                "User-Agent": "radio-epg/0.1 (playlist-fetcher)"
            })
            resp.raise_for_status()
            raw_channels = parse_m3u8_text(resp.text)
            ch_list = [
                {
                    "tvg_id": c.tvg_id,
                    "name": c.name,
                    "url": c.url,
                    "logo": c.logo or "",
                    "group": c.group or "",
                }
                for c in raw_channels
            ]
            store().cache_source_channels(source_id, ch_list)
            return jsonify({"channels": ch_list, "cached": False})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/playlist/import", methods=["POST"])
    def playlist_import():
        """Import selected channels into the configured channel list."""
        payload = request.get_json(force=True, silent=True) or {}
        channels_to_import = payload.get("channels", [])
        source_id = payload.get("source_id", "manual")
        imported = 0
        for ch in channels_to_import:
            tvg_id = ch.get("tvg_id", "")
            if not tvg_id:
                continue
            store().upsert_channel({
                "tvg_id": tvg_id,
                "name": ch.get("name", tvg_id),
                "url": ch.get("url", ""),
                "logo": ch.get("logo") or None,
                "group": ch.get("group") or None,
                "timezone": "UTC",
                "enabled": True,
                "source": source_id,
            })
            imported += 1
        return jsonify({"imported": imported})

    @app.route("/playlist/generate", methods=["POST"])
    def playlist_generate():
        """Generate and return a custom M3U8 file."""
        payload = request.get_json(force=True, silent=True) or {}
        tvg_ids = payload.get("tvg_ids", [])
        channels = store().get_channels()
        selected = [c for c in channels if c["tvg_id"] in tvg_ids]
        if not selected:
            return jsonify({"error": "No channels selected"}), 400

        lines = ["#EXTM3U x-tvg-url=\"epg.xml\"", ""]
        for ch in selected:
            logo = ch.get("logo") or ""
            group = ch.get("group") or ""
            name = ch.get("name", ch["tvg_id"])
            lines.append(
                f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" tvg-name="{name}" '
                f'tvg-logo="{logo}" group-title="{group}",{name}'
            )
            lines.append(ch.get("url", ""))
            lines.append("")

        content = "\n".join(lines)
        buf = io.BytesIO(content.encode("utf-8"))
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="radio.m3u8",
                         mimetype="audio/x-mpegurl")

    # ------------------------------------------------------------------ EPG generation

    @app.route("/epg")
    def epg():
        channels = [c for c in store().get_channels() if c.get("enabled", True)]
        with_sched = [c for c in channels if has_schedule(c["tvg_id"])]
        return render_template(
            "epg.html",
            channels=channels,
            scheduled_channels=with_sched,
            today=date.today().isoformat(),
        )

    @app.route("/epg/generate", methods=["POST"])
    def epg_generate():
        start_str = request.form.get("start_date") or date.today().isoformat()
        days = int(request.form.get("days", 7))
        selected_ids = request.form.getlist("channel_ids") or None
        apply_ov = request.form.get("apply_overrides") == "1"

        start_date = date.fromisoformat(start_str)
        all_channels = store().get_channels()

        if selected_ids:
            channels = [c for c in all_channels if c["tvg_id"] in selected_ids]
        else:
            channels = [c for c in all_channels if c.get("enabled", True)]

        from ..models import Channel as ChannelModel
        channel_models = [
            ChannelModel(
                tvg_id=c["tvg_id"],
                name=c["name"],
                url=c.get("url", ""),
                logo=channel_logo_url(c) or c.get("logo"),
                group=c.get("group"),
            )
            for c in channels
        ]

        all_programmes = []
        channel_timezones = {}

        for ch in channels:
            p = schedule_path(ch["tvg_id"])
            if not p.exists():
                continue
            try:
                weekly = load_schedule_yaml(p)
            except Exception:
                continue
            channel_timezones[ch["tvg_id"]] = weekly.timezone
            progs = expand_schedule(weekly, start_date, days)
            all_programmes.extend(progs)

        if apply_ov:
            raw_overrides = store().get_overrides()
            override_objs = [
                ProgramOverride(
                    id=o["id"],
                    channel_id=o["channel_id"],
                    date=o["date"],
                    start=o["start"],
                    end=o["end"],
                    title=o["title"],
                    description=o.get("description", ""),
                    override_type=o.get("override_type", "event"),
                    image=o.get("image"),
                )
                for o in raw_overrides
            ]
            all_programmes = apply_overrides(all_programmes, override_objs, channel_timezones)

        xml_str = generate_xmltv(channel_models, all_programmes)
        buf = io.BytesIO(xml_str.encode("utf-8"))
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="epg.xml",
                         mimetype="application/xml")

    # ------------------------------------------------------------------ Radio Browser

    _RB_BASE = "https://de1.api.radio-browser.info/json"
    _RB_HEADERS = {
        "User-Agent": "radio-epg/0.1 (https://github.com/Mattincbr/reimagined-octo-disco)"
    }

    @app.route("/api/radiobrowser/countries")
    def rb_countries():
        try:
            r = requests.get(f"{_RB_BASE}/countries",
                             headers=_RB_HEADERS, timeout=15,
                             params={"order": "name", "hidebroken": "true"})
            r.raise_for_status()
            return jsonify(r.json())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/radiobrowser/tags")
    def rb_tags():
        try:
            r = requests.get(f"{_RB_BASE}/tags",
                             headers=_RB_HEADERS, timeout=15,
                             params={"order": "stationcount", "reverse": "true",
                                     "limit": 300, "hidebroken": "true"})
            r.raise_for_status()
            return jsonify(r.json())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/radiobrowser/search")
    def rb_search():
        params: dict = {
            "order":       request.args.get("order", "votes"),
            "reverse":     "true",
            "hidebroken":  "true",
            "limit":       request.args.get("limit", "100"),
        }
        if request.args.get("countrycode"):
            params["countrycode"] = request.args["countrycode"].upper()
        if request.args.get("tag"):
            params["tag"] = request.args["tag"]
        if request.args.get("name"):
            params["name"] = request.args["name"]

        try:
            r = requests.get(f"{_RB_BASE}/stations/search",
                             headers=_RB_HEADERS, timeout=20, params=params)
            r.raise_for_status()
            stations = r.json()

            channels = []
            for s in stations:
                name = (s.get("name") or "").strip()
                url  = s.get("url_resolved") or s.get("url", "")
                if not name or not url:
                    continue
                tags_str  = (s.get("tags") or "").strip(", ")
                codec     = s.get("codec", "")
                bitrate   = s.get("bitrate", 0)
                country   = s.get("country", "")
                cc        = s.get("countrycode", "")
                channels.append({
                    "tvg_id": f"rb-{s['stationuuid']}",
                    "name":   name,
                    "url":    url,
                    "logo":   s.get("favicon") or "",
                    "group":  f"{cc} — {tags_str[:40]}" if tags_str else cc,
                    "_rb": {
                        "country": country,
                        "codec":   codec,
                        "bitrate": bitrate,
                        "tags":    tags_str,
                        "votes":   s.get("votes", 0),
                    },
                })
            return jsonify({"channels": channels, "total": len(channels)})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------ EPG Preview

    @app.route("/epg-preview")
    def epg_preview():
        channels = [c for c in store().get_channels() if c.get("enabled", True)]
        today = date.today()
        return render_template("epg_preview.html", channels=channels, today=today.isoformat())

    @app.route("/api/epg-preview")
    def api_epg_preview():
        """Return timeline blocks for the EPG preview page."""
        day_str = request.args.get("date", date.today().isoformat())
        try:
            day = date.fromisoformat(day_str)
        except ValueError:
            day = date.today()

        channels = [c for c in store().get_channels() if c.get("enabled", True)]
        rows = []
        import datetime as dt

        for ch in channels:
            p = schedule_path(ch["tvg_id"])
            if not p.exists():
                rows.append({"id": ch["tvg_id"], "name": ch["name"], "blocks": []})
                continue
            try:
                weekly = load_schedule_yaml(p)
                progs = expand_schedule(weekly, day, 1)
            except Exception:
                rows.append({"id": ch["tvg_id"], "name": ch["name"], "blocks": []})
                continue

            blocks = []
            now_utc = dt.datetime.now(dt.timezone.utc)
            for prog in progs:
                start_local = prog.start
                stop_local  = prog.stop
                start_min = start_local.hour * 60 + start_local.minute
                stop_min  = stop_local.hour * 60  + stop_local.minute
                if stop_min <= start_min:
                    stop_min = start_min + 30
                duration = stop_min - start_min
                left_pct = start_min / 1440 * 100
                width_pct = duration / 1440 * 100

                hour = start_local.hour
                if hour < 6:
                    color = "var(--color-slate-blue)"
                    fg = "#fff"
                elif hour < 18:
                    color = "var(--color-navy)"
                    fg = "#fff"
                else:
                    color = "var(--color-coral)"
                    fg = "#fff"

                try:
                    on_air = start_local <= now_utc.astimezone(start_local.tzinfo) < stop_local
                except Exception:
                    on_air = False

                blocks.append({
                    "title": prog.title,
                    "start": start_local.strftime("%H:%M"),
                    "stop": stop_local.strftime("%H:%M"),
                    "left_pct": round(left_pct, 3),
                    "width_pct": round(width_pct, 3),
                    "color": color,
                    "fg": fg,
                    "on_air": on_air,
                })
            rows.append({"id": ch["tvg_id"], "name": ch["name"], "blocks": blocks})

        return jsonify({"rows": rows, "date": day_str})

    # ------------------------------------------------------------------ Poster Studio

    @app.route("/poster-studio")
    def poster_studio():
        channels = [c for c in store().get_channels() if c.get("enabled", True)]
        return render_template("poster_studio.html", channels=channels)

    # ------------------------------------------------------------------ API helpers

    @app.route("/api/schedule/<tvg_id>")
    def api_schedule(tvg_id: str):
        if not has_schedule(tvg_id):
            return jsonify({})
        try:
            raw = yaml.safe_load(schedule_path(tvg_id).read_text(encoding="utf-8"))
            return jsonify(raw.get("schedule", {}))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/programmes/<tvg_id>/<date_str>")
    def api_programmes(tvg_id: str, date_str: str):
        """Return expanded programmes for a single day (for override preview)."""
        ch = store().get_channel(tvg_id)
        if not ch or not has_schedule(tvg_id):
            return jsonify([])
        try:
            weekly = load_schedule_yaml(schedule_path(tvg_id))
            progs = expand_schedule(weekly, date.fromisoformat(date_str), 1)
            return jsonify([
                {
                    "start": p.start.strftime("%H:%M"),
                    "stop": p.stop.strftime("%H:%M"),
                    "title": p.title,
                }
                for p in progs
            ])
        except Exception:
            return jsonify([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_scraper(url: str):
    if "abc.net.au" in url:
        return ABCScraper()
    _nine_radio_domains = (
        "4bc.com.au", "2gb.com.au", "3aw.com.au",
        "5aa.com.au", "6pr.com.au", "9radio.com.au",
        "2ue.com.au", "4bh.com.au", "6pb.com.au",
    )
    if any(d in url for d in _nine_radio_domains):
        from ..scrapers.nine_radio import NineRadioScraper
        return NineRadioScraper()
    if "novafm.com.au" in url or "smoothfm.com.au" in url:
        from ..scrapers.nova_entertainment import NovaEntertainmentScraper
        return NovaEntertainmentScraper()
    from ..scrapers.generic import GenericScraper
    return GenericScraper()


def _common_timezones() -> list[str]:
    return [
        "UTC",
        "Australia/Sydney",
        "Australia/Melbourne",
        "Australia/Brisbane",
        "Australia/Adelaide",
        "Australia/Perth",
        "Australia/Darwin",
        "Australia/Hobart",
        "Pacific/Auckland",
        "Europe/London",
        "Europe/Paris",
        "America/New_York",
        "America/Chicago",
        "America/Los_Angeles",
        "Asia/Tokyo",
        "Asia/Singapore",
    ]
