"""Pack the archmap, Three.js and the warehouse app into one offline HTML file."""

from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).parent


def _safe_json(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("<!--", "<\\!--")


def render_html(data: dict) -> str:
    template = (HERE / "template.html").read_text(encoding="utf-8")
    css = (HERE / "app.css").read_text(encoding="utf-8")
    app = (HERE / "app.js").read_text(encoding="utf-8")
    three = (HERE / "vendor" / "three.min.js").read_text(encoding="utf-8")
    title = f"{data['project']['name']} · Wirehouse"
    fonts_path = HERE / "vendor" / "fonts.embedded.css"
    fonts = fonts_path.read_text(encoding="utf-8") if fonts_path.is_file() else ""
    parts = {
        "__TITLE__": html.escape(title),
        "/*__FONTS__*/": fonts,
        "/*__CSS__*/": css,
        "/*__THREE__*/": three,
        "/*__DATA__*/": "window.WIREHOUSE = " + _safe_json(data) + ";",
        "/*__APP__*/": app,
    }
    out = template
    for key, value in parts.items():
        # str.replace treats the value literally (no regex escapes to worry about)
        out = out.replace(key, value, 1)
    return out


def write_html(data: dict, path: Path) -> Path:
    path.write_text(render_html(data), encoding="utf-8")
    return path
