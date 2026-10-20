"""Pack the archmap, Three.js and the warehouse app into one offline HTML file."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote

from wirehouse.redact import scrub
from wirehouse.scan import write_replacing

HERE = Path(__file__).parent


def _safe_json(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("<!--", "<\\!--")


def render_html(data: dict) -> str:
    data, _ = scrub(data)
    template = (HERE / "template.html").read_text(encoding="utf-8")
    css = (HERE / "app.css").read_text(encoding="utf-8")
    app = (HERE / "app.js").read_text(encoding="utf-8")
    three = (HERE / "vendor" / "three.min.js").read_text(encoding="utf-8")
    title = f"{data['project']['name']} · Wirehouse"
    fonts_path = HERE / "vendor" / "fonts.embedded.css"
    fonts = fonts_path.read_text(encoding="utf-8") if fonts_path.is_file() else ""
    parts = {
        "__TITLE__": html.escape(title),
        "__FAVICON__": "data:image/svg+xml," + quote((HERE / "vendor" / "favicon.svg").read_text(encoding="utf-8").strip(), safe=" =:/,'"),   # quotes stay encoded: this sits in href="..."
        "/*__FONTS__*/": fonts,
        "/*__CSS__*/": css,
        "/*__THREE__*/": three,
        "/*__DATA__*/": "window.WIREHOUSE = " + _safe_json(data) + ";",
        "/*__APP__*/": app,
    }
    # One pass over the template only: a value that happens to contain a placeholder (a description
    # quoting "/*__APP__*/") is inserted as it is, never filled in turn.
    pattern = re.compile("|".join(re.escape(k) for k in parts))
    missing = [k for k in parts if template.count(k) != 1]
    if missing:
        raise ValueError(f"template.html must hold each placeholder once: {missing}")
    return pattern.sub(lambda m: parts[m.group(0)], template)


def write_html(data: dict, path: Path) -> Path:
    return write_replacing(path, render_html(data))
