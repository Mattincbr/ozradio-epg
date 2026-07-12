# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Radio EPG Web Manager standalone binary."""

import sys
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "radio_epg" / "web" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle templates and static files inside the binary
        (str(ROOT / "radio_epg" / "web" / "templates"), "radio_epg/web/templates"),
        (str(ROOT / "radio_epg" / "web" / "static"),    "radio_epg/web/static"),
        (str(ROOT / "radio_epg" / "data"),               "radio_epg/data"),
    ],
    hiddenimports=[
        "radio_epg",
        "radio_epg.web",
        "radio_epg.web.app",
        "radio_epg.web.routes",
        "radio_epg.web.store",
        "radio_epg.models",
        "radio_epg.schedule",
        "radio_epg.schedule_library",
        "radio_epg.xml_generator",
        "flask",
        "jinja2",
        "werkzeug",
        "click",
        "lxml",
        "lxml.etree",
        "lxml._elementpath",
        "bs4",
        "yaml",
        "pytz",
        "requests",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "cryptography", "OpenSSL"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="radio-epg-web",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
