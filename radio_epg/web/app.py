"""Flask application factory for the Radio EPG web interface."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .store import Store


def create_app(base_dir: str | Path = ".") -> Flask:
    base_dir = Path(base_dir).resolve()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "radio-epg-dev-key-change-me")
    app.config["BASE_DIR"] = base_dir
    app.config["DATA_DIR"] = base_dir / "data"
    app.config["SCHEDULES_DIR"] = base_dir / "schedules"
    app.config["UPLOADS_DIR"] = base_dir / "uploads"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

    # Ensure required directories exist
    for subdir in ["", "logos", "images"]:
        (app.config["UPLOADS_DIR"] / subdir).mkdir(parents=True, exist_ok=True)
    app.config["SCHEDULES_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)

    app.config["STORE"] = Store(app.config["DATA_DIR"])

    from .routes import register_routes
    register_routes(app)

    return app
