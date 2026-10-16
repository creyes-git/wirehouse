"""wirehouse CLI.

  wirehouse scan   <path>   detect structure -> archmap.raw.json + enrich-brief.md
  wirehouse render <path>   merge enrichment.json -> archmap.json + wirehouse.html
  wirehouse build  <path>   scan + render in one go (uses any cached enrichment)
  wirehouse install         install the Claude Code skill (~/.claude/skills/wirehouse)
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from wirehouse import __version__

RAW_NAME = "archmap.raw.json"
MAP_NAME = "archmap.json"
HTML_NAME = "wirehouse.html"


def _out_dir(project: Path, out: str | None) -> Path:
    d = Path(out).resolve() if out else project / "wirehouse-out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(msg: str) -> None:
    print(msg, flush=True)


def cmd_scan(project: Path, out_dir: Path) -> dict:
    from wirehouse.build import build_archmap
    from wirehouse.enrich import load_enrichment, write_brief

    _log(f"wirehouse {__version__}: scanning {project}")
    data = build_archmap(project, log=_log)
    (out_dir / RAW_NAME).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    brief, n_nodes, n_links = write_brief(data, load_enrichment(out_dir), out_dir)
    _log(f"  wrote {out_dir / RAW_NAME}")
    if n_nodes or n_links:
        _log(f"  enrichment needed: {n_nodes} blocks/folders and {n_links} connections, see {brief}")
    else:
        _log("  enrichment is up to date")
    return data


def cmd_render(project: Path, out_dir: Path, open_it: bool) -> Path:
    from wirehouse.enrich import load_enrichment, merge
    from wirehouse.render.html import write_html

    raw = out_dir / RAW_NAME
    if not raw.is_file():
        raise SystemExit(f"error: {raw} not found. Run `wirehouse scan {project}` first.")
    data = json.loads(raw.read_text(encoding="utf-8"))
    enrichment = load_enrichment(out_dir)
    data = merge(data, enrichment)
    stale = sum(1 for n in data["nodes"] if n.get("stale"))
    (out_dir / MAP_NAME).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    html_path = write_html(data, out_dir / HTML_NAME)
    size = html_path.stat().st_size / 1024 / 1024
    st = data.get("enrichment_stats")
    if st:
        _log(f"  merged enrichment: {st['nodes']} block/folder descriptions, {st['links']} connection notes, "
             f"+{st['added_nodes']} nodes, +{st['added_edges']} edges, -{st['removed_nodes']} nodes, -{st['removed_edges']} connections"
             + (f", {stale} stale" if stale else ""))
    else:
        _log("  no enrichment.json yet: descriptions are rule-based")
    for w in data.get("warnings", []):
        _log(f"  warning: {w}")
    _log(f"  wrote {html_path} ({size:.1f} MB)")
    if open_it:
        webbrowser.open(html_path.as_uri())
    return html_path


def cmd_install() -> None:
    src = Path(__file__).parent / "skill" / "SKILL.md"
    home = Path(__file__).resolve().parent.parent
    dest_dir = Path.home() / ".claude" / "skills" / "wirehouse"
    dest_dir.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8").replace("{{WIREHOUSE_HOME}}", str(home))
    (dest_dir / "SKILL.md").write_text(text, encoding="utf-8")
    _log(f"installed skill to {dest_dir / 'SKILL.md'}. Use /wirehouse in Claude Code.")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="wirehouse", description="Walk through your project's architecture as a 3D warehouse.")
    p.add_argument("--version", action="version", version=f"wirehouse {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "render", "build"):
        sp = sub.add_parser(name)
        sp.add_argument("path", nargs="?", default=".", help="project root (default: current folder)")
        sp.add_argument("-o", "--out", help="output folder (default: <path>/wirehouse-out)")
        if name != "scan":
            sp.add_argument("--open", action="store_true", help="open the HTML in your browser")
    sub.add_parser("install", help="install the Claude Code skill")
    args = p.parse_args(argv)

    if args.cmd == "install":
        cmd_install()
        return 0
    project = Path(args.path).resolve()
    if not project.is_dir():
        raise SystemExit(f"error: {project} is not a folder")
    out_dir = _out_dir(project, args.out)
    if args.cmd in ("scan", "build"):
        cmd_scan(project, out_dir)
    if args.cmd in ("render", "build"):
        cmd_render(project, out_dir, args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
