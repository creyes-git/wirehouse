"""The map as text: a Mermaid diagram and a Markdown summary for READMEs, pull requests and docs.

Same rules as the page: only recorded connections, rolled up to top-level blocks, each with the
file and line it was found in. Text is easy to diff, so a pull request can show how the map moved.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from wirehouse.enrich import top_links
from wirehouse.model import LAYERS
from wirehouse.redact import scrub

EDGE_LABEL = {
    "imports": "imports code", "calls": "calls", "data": "reads and writes", "auth": "signs in with",
    "publishes": "sends messages", "depends_on": "starts after", "provisions": "provisions", "uses": "uses",
    "references": "references",
}
# Start-up order and provisioning are not traffic (the page's traces skip them too): drawn dotted.
NOT_TRAFFIC = {"depends_on", "provisions"}
KIND_ORDER = ["auth", "data", "publishes", "calls", "provisions", "uses", "imports", "references", "depends_on"]
STORE_KINDS = {"database", "cache", "storage", "search"}
MAX_EVIDENCE = 3


def _label(text: str) -> str:
    """Text inside a quoted Mermaid label: no quotes, brackets or line breaks can end it early."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text.replace("&", "#amp;").replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")


def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().replace("|", "\\|")


def web_link(repo: dict | None, file: str, line: int | None) -> str | None:
    """The code host's link to `file` at the scanned commit, as the page builds it."""
    if not repo or not repo.get("web") or not repo.get("revision"):
        return None
    path = "/".join(quote(p) for p in ((repo.get("prefix") + "/" if repo.get("prefix") else "") + file).split("/"))
    base, rev = repo["web"], repo["revision"]
    return {
        "github": f"{base}/blob/{rev}/{path}" + (f"#L{line}" if line else ""),
        "gitlab": f"{base}/-/blob/{rev}/{path}" + (f"#L{line}" if line else ""),
        "bitbucket": f"{base}/src/{rev}/{path}" + (f"#lines-{line}" if line else ""),
        "azure": f"{base}?path=/{path}&version=GC{rev}" + (f"&line={line}" if line else ""),
    }.get(repo.get("provider"))


def _main_kind(kinds: set[str]) -> str:
    return next((k for k in KIND_ORDER if k in kinds), next(iter(kinds), "uses"))


def mermaid(data: dict) -> str:
    tops = [n for n in data["nodes"] if n["parent"] is None]
    ids = {n["id"]: f"n{i}" for i, n in enumerate(tops)}
    lines = ["flowchart LR"]
    for layer in LAYERS:
        members = [n for n in tops if n.get("layer") == layer["id"]]
        if not members:
            continue
        lines.append(f'  subgraph {layer["id"]}["{_label(layer["name"])}"]')
        for n in members:
            name = _label(n["name"])
            shape = f'[("{name}")]' if n["kind"] in STORE_KINDS else f'(["{name}"])' if n["kind"] == "user" else f'["{name}"]'
            lines.append(f"    {ids[n['id']]}{shape}")
        lines.append("  end")
    for n in tops:   # blocks without a known layer still belong on the diagram
        if n.get("layer") not in {layer["id"] for layer in LAYERS}:
            lines.append(f'  {ids[n["id"]]}["{_label(n["name"])}"]')
    for link in sorted(top_links(data).values(), key=lambda L: (L["source"], L["target"])):
        if link["source"] not in ids or link["target"] not in ids:
            continue
        kind = _main_kind(link["kinds"])
        text = EDGE_LABEL.get(kind, kind) + ("" if link["confirmed"] else " (inferred)")
        arrow = "-.->" if kind in NOT_TRAFFIC or not link["confirmed"] else "-->"
        lines.append(f'  {ids[link["source"]]} {arrow}|"{_label(text)}"| {ids[link["target"]]}')
    return "\n".join(lines) + "\n"


def markdown(data: dict) -> str:
    data, _ = scrub(data)
    nodes = {n["id"]: n for n in data["nodes"]}
    repo = data.get("repo")
    order = {layer["id"]: i for i, layer in enumerate(LAYERS)}
    tops = sorted((n for n in data["nodes"] if n["parent"] is None), key=lambda n: (order.get(n.get("layer"), len(order)), n["name"].lower()))
    at = f" at commit `{repo['short']}`" if repo and repo.get("short") else ""
    out = [
        f"# {data['project']['name']} architecture",
        "",
        f"Mapped by Wirehouse{at}. Every connection was found in the code (file and line below) or added by an",
        "agent with checked evidence; dotted arrows are inferred or describe start-up order and provisioning,",
        "not traffic.",
        "",
        "```mermaid",
        mermaid(data).rstrip("\n"),
        "```",
        "",
        "## Blocks",
        "",
    ]
    for n in tops:
        text = n.get("purpose") or n.get("description") or ""
        tech = ", ".join(n.get("tech") or [])
        out.append(f"- **{_cell(n['name'])}** ({n['kind']}{', ' + _cell(tech) if tech else ''})" + (f": {_cell(text)}" if text else ""))
    links = sorted(top_links(data).values(), key=lambda L: (nodes[L["source"]]["name"].lower(), nodes[L["target"]]["name"].lower()))
    out += ["", "## Connections", ""]
    if not links:
        out.append("No connections between blocks were recorded.")
    else:
        out += ["| From | To | Kind | Evidence |", "|------|----|------|----------|"]
        notes = data.get("link_notes") or {}
        for L in links:
            kinds = ", ".join(EDGE_LABEL.get(k, k) for k in sorted(L["kinds"])) + ("" if L["confirmed"] else " (inferred)")
            cites = []
            for ev in L["evidence"][:MAX_EVIDENCE]:
                spot = ev["file"] + (f":{ev['line']}" if ev.get("line") else "")
                href = web_link(repo, ev["file"], ev.get("line"))
                cites.append(f"[`{_cell(spot)}`]({href})" if href else f"`{_cell(spot)}`")
            note = notes.get(f"{L['source']}->{L['target']}")
            out.append(f"| {_cell(nodes[L['source']]['name'])} | {_cell(nodes[L['target']]['name'])} | {kinds}"
                       + (f": {_cell(note)}" if note else "") + f" | {', '.join(cites) or 'none recorded'} |")
    return "\n".join(out) + "\n"
