"""Entry point: python -m radio_epg.web  or  radio-epg-web"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="radio-epg-web",
        description="Radio EPG Manager — web interface",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.cwd(),
        help="Working directory for data/schedules/uploads (default: cwd)",
    )
    args = parser.parse_args()

    from radio_epg.web.app import create_app

    app = create_app(base_dir=args.data_dir)

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}/"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
