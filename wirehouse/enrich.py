"""Agent enrichment: write a brief, merge the coding agent's answers back in.

The rule-based scan knows *what* is connected; the agent adds *why*. The skill
asks the agent to read `enrich-brief.md`, open the relevant files and write
`enrichment.json`. Entries carry the node's content hash, so on the next run
only nodes whose code changed are asked about again.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from wirehouse.model import EDGE_KINDS, KINDS

BRIEF_NAME = "enrich-brief.md"
ENRICH_NAME = "enrichment.json"


def load_enrichment(out_dir: Path) -> dict:
    p = out_dir / ENRICH_NAME
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"error: {p} is not valid JSON ({exc}). Fix it or delete it and re-run.")


def _index(data: dict):
    nodes = {n["id"]: n for n in data["nodes"]}
    children = defaultdict(list)
    for n in data["nodes"]:
        if n["parent"]:
            children[n["parent"]].append(n["id"])
    return nodes, children


def _top(nodes, nid):
    while nodes[nid]["parent"]:
        nid = nodes[nid]["parent"]
    return nid


def top_links(data: dict) -> dict[str, dict]:
    """Roll edges up to top-level blocks: 'a->b' -> {kinds, count, evidence}."""
    nodes, _ = _index(data)
    out: dict[str, dict] = {}
    for e in data["edges"]:
        a, b = _top(nodes, e["source"]), _top(nodes, e["target"])
        if a == b:
            continue
        key = f"{a}->{b}"
        L = out.setdefault(key, {"source": a, "target": b, "kinds": set(), "count": 0, "evidence": [], "notes": [], "confirmed": False})
        L["kinds"].add(e["kind"])
        L["confirmed"] = L["confirmed"] or e.get("confidence") == "EXTRACTED"
        L["count"] += e.get("count", 1)
        for ev in e.get("evidence", [])[:2]:
            if len(L["evidence"]) < 4:
                L["evidence"].append(ev)
        if e.get("description") and len(L["notes"]) < 3 and e["description"] not in L["notes"]:
            L["notes"].append(e["description"])
    return out


def nodes_needing_text(data: dict, enrichment: dict) -> list[dict]:
    done = enrichment.get("nodes", {})
    out = []
    for n in data["nodes"]:
        wanted = n["parent"] is None or (n["kind"] == "module" and n.get("stats", {}).get("files", 0) >= 2)
        if not wanted:
            continue
        prev = done.get(n["id"])
        if prev and prev.get("hash") == n.get("hash") and prev.get("description"):
            continue
        out.append(dict(n, _status="changed" if prev else "new"))
    return out


def write_brief(data: dict, enrichment: dict, out_dir: Path) -> tuple[Path, int, int]:
    nodes, children = _index(data)
    todo = nodes_needing_text(data, enrichment)
    links = top_links(data)
    done_links = enrichment.get("links", {})
    link_todo = {k: v for k, v in links.items() if k not in done_links}
    lines = [
        f"# Wirehouse enrichment brief: {data['project']['name']}",
        "",
        "Wirehouse already mapped the structure with static rules. Your job is to add the human layer:",
        "what each block is and why it exists, and what each top-level connection carries.",
        "",
        f"Write (or update) `{ENRICH_NAME}` next to this file, then run `wirehouse render`.",
        "",
        "```json",
        "{",
        '  "version": 1,',
        '  "nodes": {',
        '    "<node id>": {"description": "1-2 sentences: what it is", "purpose": "1 sentence: its role in the system", "hash": "<hash from this brief>"},',
        '    "<node id>": {"name": "optional better display name", "kind": "optional, top-level only", "description": "...", "purpose": "...", "hash": "..."}',
        "  },",
        '  "links": {"<source id>-><target id>": {"description": "what flows over this connection, and when"}},',
        '  "add_nodes": [{"id": "res:custom-x", "name": "...", "kind": "external", "description": "...", "purpose": "...", "locations": [{"file": "path", "line": 1}]}],',
        '  "add_edges": [{"source": "<id>", "target": "<id>", "kind": "calls", "description": "...", "evidence": [{"file": "path", "line": 1}]}],',
        '  "remove_nodes": [], "remove_edges": [{"source": "<id>", "target": "<id>"}],',
        '  "tours": [',
        '    {"id": "checkout", "title": "How an order gets paid", "intro": "1 sentence", "stops": [',
        '      {"node": "<node id>", "text": "1-3 sentences: what the reader sees here", "evidence": [{"file": "path", "line": 12}]}]},',
        '    {"id": "login", "title": "Follow a sign-in", "route": ["<from node id>", "<to node id>"]}',
        "  ],",
        '  "quests": [{"id": "pw", "question": "Where are passwords checked?", "answer": ["<node id>"], "hint": "...", "explain": "...", "evidence": [{"file": "path", "line": 3}]}]',
        "}",
        "```",
        "",
        "Rules:",
        "- Ground every sentence in the code. Open the listed files when the name alone is not enough. Do not guess.",
        "- Plain language a new teammate understands. No marketing words. Mention concrete things (tables, endpoints, providers).",
        "- Copy each node's `hash` exactly. It is how Wirehouse knows which descriptions are still fresh.",
        "- Keep existing entries in the file. Only add or update the ones listed below.",
        "- Only add nodes/edges the rules missed, and only with evidence (file + line). Remove false positives with `remove_*`.",
        f"- Allowed kinds: {', '.join(k for k, v in KINDS.items() if v)}. Edge kinds: {', '.join(EDGE_KINDS)}.",
        "- Never write secret values (keys, passwords, tokens) into the JSON.",
        "- Node ids: top-level blocks and folders are listed below. Files are `file:<path from project root>` and",
        "  tables are `table:<database>:<lowercase name>` (listed under each database). Any id in `archmap.raw.json` works.",
        "- `kind` (top-level blocks only) fixes a block the rules put in the wrong zone, e.g. release scripts detected",
        "  as a `worker` that are really `ci`. Evidence may point at any file in the project, scanned or not.",
        "",
        "- `name`: only set it when the folder or package name hides what the block is (for example `superdb` ->",
        "  \"Market data warehouse\"). Never just repeat the path.",
        "- `remove_edges` on two top-level ids drops every connection between those blocks, at all levels. Add a",
        "  `reason` with file:line evidence; it is kept for reviewers. The matching `links` entry is dropped too.",
        "- Unknown keys are ignored. `wirehouse render` reports how many nodes, links and removals were applied.",
        "- `tours` (2-4, each 3-8 stops) walk a new teammate through the system in the order a request or job really",
        "  moves. A `route` tour gives two node ids and Wirehouse walks the recorded path between them. `quests` (3-6)",
        "  ask the reader to find something worth knowing; `answer` lists the node ids that count. Every stop and quest",
        "  cites the file and line it is based on. `wirehouse render` checks each node id, file and line and prints",
        "  `error [code] subject: message -> fix` for anything wrong: fix exactly that entry and render again.",
        "- Folders that contain a single subfolder are merged into one entry (`db/queries`), and folders with fewer",
        "  than 2 files are not listed (they keep their rule text).",
        "",
        "Connection evidence types: `import` (code imports the library), `env` (reads an env var that points at it),",
        "`URL ... in request code` (a URL next to fetch/request code), `declares dependency (no import found)` (only in",
        "a manifest: check whether it is really used). Connections marked *inferred* have no direct evidence.",
        "",
        f"## Blocks and folders to describe ({len(todo)})",
        "",
    ]
    groups: dict[str, int] = {}
    for n in todo:
        t = _top(nodes, n["id"])
        label = nodes[t]["name"] if n["parent"] else "top-level blocks"
        if n["parent"] and nodes[n["parent"]]["parent"]:
            label += " / " + n.get("path", "").split("/")[len(nodes[t].get("path", ".").split("/")) if nodes[t].get("path", ".") != "." else 0]
        groups[label] = groups.get(label, 0) + 1
    if len(todo) > 60:
        lines += ["Suggested split for subagents: " + ", ".join(f"{k} ({v})" for k, v in groups.items()), ""]
    for n in sorted(todo, key=lambda x: (x["parent"] is not None, x["id"])):
        st = n.get("stats", {})
        kids = [nodes[c] for c in children.get(n["id"], [])]
        kid_names = ", ".join(sorted(k["name"] for k in kids)[:24]) + (" …" if len(kids) > 24 else "")
        lines.append(f"### `{n['id']}` | {n['name']} ({n['kind']}) | hash `{n.get('hash')}` | {n['_status']}")
        meta = []
        if n.get("path"):
            meta.append(f"path `{n['path']}`")
        if st.get("files"):
            meta.append(f"{st['files']} files, {st.get('lines', 0):,} lines")
        if st.get("endpoints"):
            meta.append(f"{st['endpoints']} endpoints/pages")
        if n.get("tech"):
            meta.append("tech: " + ", ".join(n["tech"]))
        if meta:
            lines.append("- " + " · ".join(meta))
        if kid_names:
            lines.append(f"- contains: {kid_names}")
        tables = sorted(k["id"] for k in kids if k["kind"] == "table")
        if tables:
            lines.append("- table ids: " + ", ".join(f"`{t}`" for t in tables[:40]) + (" …" if len(tables) > 40 else ""))
        if n.get("detected_via"):
            lines.append("- detected via: " + "; ".join(n["detected_via"][:5]))
        locs = [f"{l['file']}" + (f":{l['line']}" if l.get("line") else "") for l in n.get("locations", [])[:4]]
        if locs:
            lines.append("- see: " + ", ".join(locs))
        lines.append(f"- rule text: {n.get('description', '')}")
        lines.append("")
    lines += [f"## Top-level connections to describe ({len(link_todo)})", ""]
    for key, L in sorted(link_todo.items()):
        a, b = nodes[L["source"]], nodes[L["target"]]
        ev = ", ".join(f"{e['file']}:{e.get('line', '')}" for e in L["evidence"])
        inferred = "" if L["confirmed"] else " | *inferred*"
        lines.append(f"- `{key}` | {a['name']} → {b['name']} | {', '.join(sorted(L['kinds']))} ×{L['count']}{inferred} | {'; '.join(L['notes'])} | evidence: {ev}")
    lines.append("")
    p = out_dir / BRIEF_NAME
    p.write_text("\n".join(lines), encoding="utf-8")
    return p, len(todo), len(link_todo)


def merge(data: dict, enrichment: dict) -> dict:
    if not enrichment:
        return data
    nodes, children = _index(data)
    warnings = []

    for nid in enrichment.get("remove_nodes", []):
        if nid not in nodes:
            continue
        stack, gone = [nid], set()
        while stack:
            cur = stack.pop()
            gone.add(cur)
            stack += children.get(cur, [])
        data["nodes"] = [n for n in data["nodes"] if n["id"] not in gone]
        data["edges"] = [e for e in data["edges"] if e["source"] not in gone and e["target"] not in gone]
        nodes, children = _index(data)

    removed_pairs = set()
    for rm in enrichment.get("remove_edges", []):
        removed_pairs.add(f"{rm.get('source')}->{rm.get('target')}")
        data["edges"] = [e for e in data["edges"]
                         if not (_top(nodes, e["source"]) == rm.get("source") and _top(nodes, e["target"]) == rm.get("target"))
                         and not (e["source"] == rm.get("source") and e["target"] == rm.get("target"))]

    for an in enrichment.get("add_nodes", []):
        if not an.get("id") or an["id"] in nodes:
            continue
        kind = an.get("kind") if an.get("kind") in KINDS else "external"
        parent = an.get("parent") if an.get("parent") in nodes else None
        n = {"id": an["id"], "name": an.get("name", an["id"]), "kind": kind, "layer": an.get("layer") or KINDS.get(kind),
             "parent": parent, "description": an.get("description", ""), "purpose": an.get("purpose", ""),
             "tech": an.get("tech", []), "locations": an.get("locations", []), "source": "agent"}
        data["nodes"].append(n)
        nodes[n["id"]] = n

    for ae in enrichment.get("add_edges", []):
        if ae.get("source") in nodes and ae.get("target") in nodes:
            data["edges"].append({"source": ae["source"], "target": ae["target"],
                                  "kind": ae.get("kind") if ae.get("kind") in EDGE_KINDS else "uses",
                                  "description": ae.get("description", ""), "evidence": ae.get("evidence", []),
                                  "confidence": "INFERRED", "count": 1, "source_tag": "agent"})
        else:
            warnings.append(f"add_edges: unknown endpoint in {ae}")

    for nid, patch in (enrichment.get("nodes") or {}).items():
        n = nodes.get(nid)
        if not n:
            continue
        for field in ("name", "description", "purpose"):
            if patch.get(field):
                n[field] = patch[field]
        if patch.get("tech"):
            n["tech"] = list(dict.fromkeys(list(n.get("tech", [])) + list(patch["tech"])))
        if patch.get("kind") in KINDS and n["parent"] is None:
            n["kind"] = patch["kind"]
            n["layer"] = patch.get("layer") or KINDS[patch["kind"]] or n["layer"]
        n["source"] = "agent"
        if patch.get("hash") and patch["hash"] != n.get("hash"):
            n["stale"] = True

    data["link_notes"] = {k: v.get("description", "") for k, v in (enrichment.get("links") or {}).items()
                          if v.get("description") and k not in removed_pairs}
    data["enrichment_stats"] = {
        "nodes": sum(1 for nid in (enrichment.get("nodes") or {}) if nid in nodes),
        "links": len(data["link_notes"]),
        "added_nodes": len(enrichment.get("add_nodes", [])), "added_edges": len(enrichment.get("add_edges", [])),
        "removed_nodes": len(enrichment.get("remove_nodes", [])), "removed_edges": len(removed_pairs),
    }
    if warnings:
        data.setdefault("warnings", []).extend(warnings)
    return data
