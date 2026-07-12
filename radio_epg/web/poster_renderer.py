"""Server-side poster PNG renderer using Playwright + Chromium."""

from __future__ import annotations

import os

# Inline CSS tokens so the headless browser doesn't need CDN access
_TOKEN_CSS = """
:root {
  --color-navy:      #1B2E4F;
  --color-salmon:    #E8FF3D;
  --color-ivory:     #F8F3EE;
  --color-coral:     #9C5A28;
  --color-slate-blue:#7B9BC4;
  --color-gold:      #C9A96E;
  --font-display:    'Playfair Display', Georgia, 'Times New Roman', serif;
  --font-body:       'Lato', 'Helvetica Neue', Arial, sans-serif;
  --font-descriptor: 'Raleway', 'Helvetica Neue', Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1280px; height: 720px; overflow: hidden; }
#poster {
  position: absolute;
  inset: 0;
  width: 1280px;
  height: 720px;
  font-family: var(--font-body);
}
"""

_LIGHT = dict(
    bg="#F8F3EE", fg="#1B2E4F", accent="#9C5A28",
    sub="rgba(27,46,79,.55)", border="rgba(27,46,79,.18)",
)
_DARK = dict(
    bg="#1B2E4F", fg="#ffffff", accent="#E8FF3D",
    sub="rgba(255,255,255,.55)", border="rgba(255,255,255,.15)",
)

_GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Playfair+Display:wght@700;800&"
    "family=Raleway:wght@300;400;600&"
    "family=Lato:wght@400;700&"
    "display=swap"
)


def _esc(s: str) -> str:
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _colors(daypart: str) -> dict:
    if daypart == "light":
        return _LIGHT
    if daypart == "dark":
        return _DARK
    from datetime import datetime
    h = datetime.now().hour
    return _DARK if (h >= 18 or h < 6) else _LIGHT


def _dp_label(daypart: str) -> str:
    if daypart == "light":
        return "Daytime"
    if daypart == "dark":
        return "Evening"
    from datetime import datetime
    h = datetime.now().hour
    return "Evening" if (h >= 18 or h < 6) else "Daytime"


def _poster_body(template: str, c: dict, channel: str, title: str,
                 presenter: str, time_range: str, dp_label: str) -> str:
    sub = c["sub"]
    ch = _esc(channel)
    t = _esc(title)
    pr = _esc(presenter)
    tr = _esc(time_range)
    dp = _esc(dp_label)

    match template:
        case "plate":
            return f"""
              <div style="position:absolute;inset:24px;border:2px solid {c['border']}"></div>
              <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
                          justify-content:center;text-align:center;padding:0 12%">
                <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.22em;
                            text-transform:uppercase;font-size:1rem;color:{c['accent']}">Now Playing</div>
                <div style="font-family:var(--font-descriptor);font-weight:300;letter-spacing:.14em;
                            text-transform:uppercase;font-size:1.1rem;color:{sub};margin-top:.5rem">{ch}</div>
                <div style="font-family:var(--font-display);font-weight:800;font-size:4.5rem;
                            line-height:1.04;margin:.75rem 0">{t}</div>
                <div style="width:64px;height:4px;background:{c['accent']};margin:.2rem 0 1rem"></div>
                <div style="font-family:var(--font-body);font-size:1.5rem;font-weight:700">{tr}</div>
                <div style="font-family:var(--font-body);font-size:1.3rem;color:{sub};margin-top:.2rem">{pr}</div>
              </div>"""

        case "band":
            return f"""
              <div style="position:absolute;inset:0;background:linear-gradient(180deg,
                rgba(16,29,52,.55) 0%,rgba(16,29,52,.12) 34%,rgba(16,29,52,.55) 100%)"></div>
              <div style="position:absolute;top:28px;left:36px;font-family:var(--font-descriptor);
                          font-weight:600;letter-spacing:.2em;text-transform:uppercase;
                          font-size:1rem;color:#fff;text-shadow:0 2px 6px rgba(16,29,52,.6)">{dp} &middot; {ch}</div>
              <div style="position:absolute;left:0;right:0;bottom:0;background:{c['bg']};color:{c['fg']};
                          padding:24px 36px;display:flex;align-items:center;gap:28px">
                <div style="flex:1;min-width:0">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.18em;
                              text-transform:uppercase;font-size:.9rem;color:{sub}">Now Playing</div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:2.8rem;
                              line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{t}</div>
                </div>
                <div style="text-align:right;flex:0 0 auto">
                  <div style="font-family:var(--font-body);font-weight:700;font-size:1.5rem">{tr}</div>
                  <div style="font-family:var(--font-body);font-size:1.15rem;color:{sub}">{pr}</div>
                </div>
              </div>"""

        case "split":
            return f"""
              <div style="position:absolute;inset:0;display:flex">
                <div style="flex:0 0 38%;background:{c['accent']};color:var(--color-navy);
                            display:flex;flex-direction:column;justify-content:flex-end;padding:36px">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.14em;
                              text-transform:uppercase;font-size:1rem">{ch}</div>
                </div>
                <div style="flex:1;display:flex;flex-direction:column;justify-content:center;
                            padding:40px 48px;background:{c['bg']};color:{c['fg']}">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.2em;
                              text-transform:uppercase;font-size:.9rem;color:{c['accent']}">Now Playing &middot; {dp}</div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:3.5rem;
                              line-height:1.05;margin:.5rem 0 .75rem">{t}</div>
                  <div style="font-family:var(--font-body);font-weight:700;font-size:1.5rem">{tr}</div>
                  <div style="font-family:var(--font-body);font-size:1.2rem;color:{sub}">{pr}</div>
                </div>
              </div>"""

        case "minimal":
            return f"""
              <div style="position:absolute;inset:0;background:{c['bg']};color:{c['fg']}">
                <div style="position:absolute;top:36px;left:48px;font-family:var(--font-descriptor);
                            font-weight:300;letter-spacing:.14em;text-transform:uppercase;
                            font-size:1rem;color:{sub}">{ch}</div>
                <div style="position:absolute;left:48px;right:48px;bottom:48px">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.2em;
                              text-transform:uppercase;font-size:.9rem;color:{c['accent']};margin-bottom:.5rem">Now Playing &middot; {dp}</div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:4.2rem;line-height:1.02">{t}</div>
                  <div style="font-family:var(--font-body);font-weight:700;font-size:1.4rem;margin-top:.5rem">
                    {tr} <span style="color:{sub};font-weight:400">&middot; {pr}</span></div>
                </div>
              </div>"""

        case "masthead":
            return f"""
              <div style="position:absolute;inset:0;background:{c['bg']};color:{c['fg']};
                          padding:48px 64px;display:flex;flex-direction:column">
                <div style="display:flex;align-items:center;justify-content:space-between;
                            border-bottom:1.5px solid {c['border']};padding-bottom:18px">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.24em;
                              text-transform:uppercase;font-size:.85rem;color:{sub}">Radio EPG &middot; {ch}</div>
                </div>
                <div style="flex:1;display:flex;flex-direction:column;justify-content:center">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.22em;
                              text-transform:uppercase;font-size:.9rem;color:{c['accent']};margin-bottom:.75rem">Now Playing</div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:5.5rem;
                              line-height:.96;letter-spacing:-.015em">{t}</div>
                </div>
                <div style="display:flex;align-items:flex-end;justify-content:space-between;
                            border-top:1.5px solid {c['border']};padding-top:18px">
                  <div style="font-family:var(--font-body);font-size:1.2rem;color:{sub}">With {pr}</div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:2.4rem">{tr}</div>
                </div>
              </div>"""

        case "broadsheet":
            return f"""
              <div style="position:absolute;inset:0;background:{c['bg']};color:{c['fg']};
                          padding:36px 56px;display:flex;flex-direction:column;text-align:center">
                <div style="border-top:2px solid {c['fg']};border-bottom:1px solid {c['border']};
                            padding:12px 0;display:flex;align-items:center;justify-content:center">
                  <div style="font-family:var(--font-display);font-weight:800;font-size:1.8rem;letter-spacing:.02em">{ch}</div>
                </div>
                <div style="flex:1;display:flex;flex-direction:column;align-items:center;
                            justify-content:center;padding:0 10%">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.3em;
                              text-transform:uppercase;font-size:.85rem;color:{c['accent']};margin-bottom:.75rem">Now Playing</div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:4.5rem;line-height:1.02">{t}</div>
                  <div style="font-family:var(--font-body);font-style:italic;font-size:1.4rem;
                              color:{sub};margin-top:.75rem">with {pr}</div>
                </div>
                <div style="border-top:1px solid {c['border']};padding-top:14px;
                            font-family:var(--font-descriptor);font-weight:600;
                            letter-spacing:.18em;text-transform:uppercase;font-size:1.05rem">{tr} &middot; {dp}</div>
              </div>"""

        case "feature":
            start_t = tr.split("–")[0] if "–" in tr else tr
            end_t = tr.split("–")[1] if "–" in tr else ""
            return f"""
              <div style="position:absolute;inset:0;background:{c['bg']};color:{c['fg']};
                          display:flex;align-items:stretch;padding:56px 60px;gap:52px">
                <div style="flex:0 0 38%;display:flex;flex-direction:column;justify-content:space-between;
                            border-right:1.5px solid {c['border']};padding-right:48px">
                  <div style="font-family:var(--font-descriptor);font-weight:300;letter-spacing:.14em;
                              text-transform:uppercase;font-size:.9rem;color:{sub}">{ch}</div>
                  <div>
                    <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.22em;
                                text-transform:uppercase;font-size:.8rem;color:{c['accent']};margin-bottom:.3rem">On Air</div>
                    <div style="font-family:var(--font-display);font-weight:800;font-size:5rem;line-height:.92">{_esc(start_t)}</div>
                    <div style="font-family:var(--font-body);font-size:1.1rem;color:{sub};margin-top:.2rem">until {_esc(end_t)}</div>
                  </div>
                </div>
                <div style="flex:1;display:flex;flex-direction:column;justify-content:center;min-width:0">
                  <div style="font-family:var(--font-display);font-weight:800;font-size:3.8rem;line-height:1.02">{t}</div>
                  <div style="width:56px;height:4px;background:{c['accent']};margin:1rem 0"></div>
                  <div style="font-family:var(--font-body);font-size:1.3rem;color:{sub}">{pr}</div>
                </div>
              </div>"""

        case "marquee":
            return f"""
              <div style="position:absolute;inset:0;background:{c['bg']};color:{c['fg']};padding:40px">
                <div style="position:absolute;inset:22px;border:2px solid {c['fg']}"></div>
                <div style="position:absolute;inset:32px;border:1px solid {c['border']}"></div>
                <div style="position:relative;height:100%;display:flex;flex-direction:column;
                            align-items:center;justify-content:space-between;text-align:center;padding:28px 12%">
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.34em;
                              text-transform:uppercase;font-size:.9rem;color:{c['accent']}">On Air &middot; {ch}</div>
                  <div>
                    <div style="font-family:var(--font-display);font-weight:800;font-size:4.8rem;
                                line-height:1;letter-spacing:-.01em">{t}</div>
                    <div style="font-family:var(--font-body);font-size:1.3rem;color:{sub};margin-top:.6rem">{pr}</div>
                  </div>
                  <div style="font-family:var(--font-display);font-weight:800;font-size:2rem">{tr}</div>
                </div>
              </div>"""

        case "ledger":
            return f"""
              <div style="position:absolute;inset:0;background:{c['bg']};color:{c['fg']};
                          display:flex;flex-direction:column;justify-content:center;padding:56px 72px;gap:18px">
                <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.28em;
                            text-transform:uppercase;font-size:.9rem;color:{c['accent']}">{ch}</div>
                <div style="width:72px;height:4px;background:{c['accent']}"></div>
                <div style="font-family:var(--font-display);font-weight:800;font-size:4.8rem;
                            line-height:1;letter-spacing:-.01em">{t}</div>
                <div style="border-top:1px solid {c['border']};margin-top:8px;padding-top:16px;
                            display:flex;justify-content:space-between;align-items:flex-end">
                  <div style="font-family:var(--font-body);font-size:1.3rem;color:{sub}">{pr}</div>
                  <div style="font-family:var(--font-descriptor);font-weight:600;letter-spacing:.12em;
                              font-size:1.1rem">{tr}</div>
                </div>
                <div style="border-top:1px solid {c['border']};height:1px"></div>
                <div style="border-top:1px solid {c['border']};height:1px;opacity:.5"></div>
              </div>"""

        case _:
            return f'<div style="display:flex;align-items:center;justify-content:center;height:100%">Unknown template</div>'


def render_poster_png(
    template: str,
    channel: str,
    daypart: str,
    title: str,
    presenter: str,
    time_start: str,
    time_end: str,
) -> bytes:
    """Render a 1280×720 poster to PNG bytes using headless Chromium."""
    c = _colors(daypart)
    dp_label = _dp_label(daypart)
    time_range = f"{time_start}–{time_end}" if time_start and time_end else time_start or ""

    body_html = _poster_body(template, c, channel, title, presenter, time_range, dp_label)

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="{_GOOGLE_FONTS_URL}">
<style>{_TOKEN_CSS}</style>
</head>
<body>
<div id="poster" style="background:{c['bg']};color:{c['fg']}">
  {body_html}
</div>
</body>
</html>"""

    from playwright.sync_api import sync_playwright

    chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH", "/opt/pw-browsers/chromium")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=chromium_path,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.set_content(html, wait_until="domcontentloaded")
        page.wait_for_timeout(800)  # let fonts load
        png_bytes = page.screenshot(clip={"x": 0, "y": 0, "width": 1280, "height": 720})
        browser.close()

    return png_bytes
