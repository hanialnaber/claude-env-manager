"""Builds demo/demo.html: the real UI with an in-memory example backend,
in one self-contained file you can open in any browser. No server needed.

    python3 demo/build_demo.py
"""

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "claude_env_manager" / "ui"
html = (UI / "index.html").read_text()
css = (UI / "style.css").read_text()
# Inline the bundled fonts so the demo is one file.
css = re.sub(
    r'url\("fonts/([a-z-]+\.woff2)"\)',
    lambda m: 'url("data:font/woff2;base64,' + base64.b64encode((UI / "fonts" / m.group(1)).read_bytes()).decode() + '")',
    css,
)
js = (UI / "app.js").read_text()
mock = (Path(__file__).parent / "mock.js").read_text()

html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
html = html.replace(
    '<script src="app.js"></script>',
    f"<script>\n{mock}\n</script>\n<script>\n{js}\n</script>",
)
html = html.replace(
    '<div id="banner" class="banner hidden" role="status"></div>',
    '<p class="demo-note">Demo with made-up example data. Nothing here touches a real computer. '
    "Install the app to manage your own variables.</p>\n"
    '    <div id="banner" class="banner hidden" role="status"></div>',
)
html = html.replace(
    "</style>",
    ".demo-note{font-size:13px;color:var(--muted);border:1px dashed rgba(233,185,73,.45);"
    "border-radius:14px;padding:10px 14px;margin:18px 0 0;background:rgba(3,6,16,.45)}\n</style>",
    1,
)
out = Path(__file__).parent / "demo.html"
out.write_text(html)
print(f"Wrote {out}")
