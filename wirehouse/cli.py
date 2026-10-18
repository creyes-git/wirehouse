"""wirehouse CLI.

  wirehouse scan   <path>   detect structure -> archmap.raw.json + enrich-brief.md
  wirehouse render <path>   merge enrichment.json -> archmap.json + wirehouse.html
  wirehouse build  <path>   scan + render in one go (uses any cached enrichment)
  wirehouse install         add the /wirehouse skill to your coding agents (see AGENT_SKILL_DIRS)
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
    brief, n_nodes, n_links = write_brief(data, load_enrichment(out_dir)[0], out_dir)
    _log(f"  wrote {out_dir / RAW_NAME}")
    if n_nodes or n_links:
        _log(f"  enrichment needed: {n_nodes} blocks/folders and {n_links} connections, see {brief}")
    else:
        _log("  enrichment is up to date")
    return data


def cmd_render(project: Path, out_dir: Path, open_it: bool, share: bool = False) -> Path:
    from wirehouse import guide
    from wirehouse.enrich import load_enrichment, merge
    from wirehouse.redact import scrub
    from wirehouse.render.html import write_html

    raw = out_dir / RAW_NAME
    if not raw.is_file():
        raise SystemExit(f"error: {raw} not found. Run `wirehouse scan {project}` first.")
    try:
        data = json.loads(raw.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise SystemExit(f"error: {raw} is not valid JSON ({exc}). Run `wirehouse scan {project}` again.")
    if not data.get("project", {}).get("root"):
        data.setdefault("project", {})["root"] = str(project)   # citations are checked against this folder
    enrichment, shape_problems = load_enrichment(out_dir)
    data = merge(data, enrichment)
    data = guide.apply(data, enrichment)
    data["diagnostics"] = shape_problems + data["diagnostics"]
    root = data["project"].get("root") or str(project)
    if share:
        # For publishing: no absolute paths of this machine (they name the user) and no list of
        # uncommitted files. Code-host links keep working; VS Code links are left out.
        data["project"].pop("root", None)
        if data.get("repo"):
            data["repo"].pop("dirty", None)
            data["repo"].pop("dirty_complete", None)
    data, redacted = scrub(data, share=share, root=root)
    if redacted:
        _log(f"  warning: removed {redacted} credential-looking value(s) from the output")
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
    tours, quests = data.get("tours", []), data.get("quests", [])
    made = " (made by Wirehouse; add your own in enrichment.json)" if tours and all(t.get("auto") for t in tours) else ""
    _log(f"  {len(tours)} tours, {len(quests)} quests{made}")
    for d in data.get("diagnostics", []):
        _log(f"  {d['severity']} [{d['code']}] {d['subject']}: {d['message']} -> {d['fix']}")
    _log(f"  wrote {html_path} ({size:.1f} MB)")
    if open_it:
        webbrowser.open(html_path.as_uri())
    return html_path


# Where each agent looks for personal skills (the open SKILL.md format), relative to the home
# folder, and the folder whose presence means the agent is installed. `~/.agents/skills` is the
# shared location several agents read, so it is always written.
SHARED_SKILL_DIR = ".agents/skills"
AGENT_SKILL_DIRS = {
    "claude": (".claude", ".claude/skills"),
    "codex": (".codex", SHARED_SKILL_DIR),
    "cursor": (".cursor", ".cursor/skills"),
    "opencode": (".config/opencode", ".config/opencode/skills"),
    "gemini": (".gemini", ".gemini/skills"),
    "antigravity": (".gemini/antigravity", ".gemini/antigravity/skills"),
    "copilot": (".copilot", ".copilot/skills"),
}


def skill_text(home: Path | None = None) -> str:
    src = Path(__file__).parent / "skill" / "SKILL.md"
    text = src.read_text(encoding="utf-8")
    home = home or Path(__file__).resolve().parent.parent
    if not (home / "pyproject.toml").is_file():
        # a regular pip install: home is site-packages, so the source checkout line would mislead
        text = "\n".join(line for line in text.splitlines() if "{{WIREHOUSE_HOME}}" not in line) + "\n"
    return text.replace("{{WIREHOUSE_HOME}}", str(home))


def cmd_install(agents: list[str] | None = None, dirs: list[str] | None = None, home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    if agents or dirs:
        targets = [home / AGENT_SKILL_DIRS[a][1] for a in agents or []]
    else:
        targets = [home / SHARED_SKILL_DIR]
        targets += [home / skills for marker, skills in AGENT_SKILL_DIRS.values() if (home / marker).is_dir()]
    targets += [Path(d).expanduser().resolve() for d in dirs or []]
    written, text = [], skill_text()
    for skills in dict.fromkeys(targets):
        dest = skills / "wirehouse" / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written.append(dest)
        _log(f"installed skill to {dest}")
    _log("Ask your agent for /wirehouse (or \"map this project with wirehouse\"). Restart it if it was already open.")
    return written


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
            sp.add_argument("--share", action="store_true",
                            help="leave out local paths (this machine's folders, uncommitted files) before publishing the page")
    sp = sub.add_parser("install", help="add the /wirehouse skill to your coding agents",
                        description="Writes SKILL.md to ~/.agents/skills plus the skills folder of every agent found "
                                    "in your home folder, unless --agent or --dir is given.")
    sp.add_argument("--agent", action="append", choices=sorted(AGENT_SKILL_DIRS), help="only this agent (repeatable)")
    sp.add_argument("--dir", action="append", help="also write to this skills folder (any other agent)")
    sp.add_argument("--print", action="store_true", help="print the instructions instead, to paste into any agent")
    args = p.parse_args(argv)

    if args.cmd == "install":
        if args.print:
            print(skill_text())
        else:
            cmd_install(args.agent, args.dir)
        return 0
    project = Path(args.path).resolve()
    if not project.is_dir():
        raise SystemExit(f"error: {project} is not a folder")
    out_dir = _out_dir(project, args.out)
    if args.cmd in ("scan", "build"):
        cmd_scan(project, out_dir)
    if args.cmd in ("render", "build"):
        cmd_render(project, out_dir, args.open, args.share)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
