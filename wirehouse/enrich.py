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

from wirehouse.guide import Evidence, _clean, diag
from wirehouse.model import EDGE_KINDS, KINDS, LAYERS

LAYER_IDS = {layer["id"] for layer in LAYERS}

BRIEF_NAME = "enrich-brief.md"
ENRICH_NAME = "enrichment.json"


def load_enrichment(out_dir: Path) -> tuple[dict, list[dict]]:
    """enrichment.json -> (entries with the expected shape, diagnostics for the ones left out)."""
    p = out_dir / ENRICH_NAME
    if not p.is_file():
        return {}, []
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))   # PowerShell writes UTF-8 with a BOM
    except ValueError as exc:
        raise SystemExit(f"error: {p} is not valid JSON ({exc}). Fix it or delete it and re-run.")
    if not isinstance(raw, dict):
        raise SystemExit(f'error: {p} must hold one JSON object ({{"nodes": ..., "tours": ...}}), not a {type(raw).__name__}.')
    return normalize(raw)


# The shape agents are asked to write (see the brief). Anything else is reported and left out, so one
# wrong entry costs that entry, not the render.
SECTIONS = {"nodes": dict, "links": dict, "add_nodes": list, "add_edges": list, "remove_nodes": list,
            "remove_edges": list, "tours": list, "quests": list}
TEXT_FIELDS = {"id", "name", "kind", "layer", "parent", "description", "purpose", "hash", "reason", "source", "target",
               "node", "title", "intro", "text", "question", "hint", "explain"}
CITATION_FIELDS = {"evidence", "locations"}


def _shape(entry, subject: str, diags: list) -> dict | None:
    if not isinstance(entry, dict):
        diags.append(diag("enrichment/wrong-shape", subject, f"expected an object, found {type(entry).__name__}",
                          "write this entry as {...} like the example in the brief", "error"))
        return None
    out = {}
    for key, value in entry.items():
        bad = None
        if key in TEXT_FIELDS and value is not None and not isinstance(value, str):
            bad = "text"
        elif key in CITATION_FIELDS:
            value = [value] if isinstance(value, dict) else value
            bad = None if isinstance(value, list) else "a list of citations"
        elif key in ("tech", "route") and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            bad = "a list of strings"
        elif key == "answer" and not (isinstance(value, str) or isinstance(value, list) and all(isinstance(v, str) for v in value)):
            bad = "a node id or a list of node ids"
        elif key == "stops":
            if isinstance(value, list):
                value = [st for j, s in enumerate(value) if (st := _shape(s, f"{subject}.stops[{j}]", diags)) is not None]
            else:
                bad = "a list of stops"
        if bad:
            diags.append(diag("enrichment/wrong-shape", f"{subject}.{key}", f"`{key}` should be {bad}; it was left out",
                              "fix the value's type, see the example in the brief", "error"))
            continue
        out[key] = value
    return out


def normalize(raw: dict) -> tuple[dict, list[dict]]:
    diags: list[dict] = []
    out: dict = {}
    for key, value in raw.items():
        want = SECTIONS.get(key)
        if want is None:
            out[key] = value   # version and unknown keys are ignored downstream
            continue
        if not isinstance(value, want):
            diags.append(diag("enrichment/wrong-shape", key, f"`{key}` should be {'an object' if want is dict else 'a list'}; it was left out",
                              "see the example in the brief", "error"))
            continue
        if key == "links":
            # a bare string is a likely shorthand for {"description": ...}
            value = {k: {"description": v} if isinstance(v, str) else v for k, v in value.items()}
        if key == "remove_nodes":
            out[key] = [v for v in value if isinstance(v, str)]
            if len(out[key]) < len(value):
                diags.append(diag("enrichment/wrong-shape", key, "only node ids (strings) can be removed; other entries were left out",
                                  'write ["<node id>", ...]', "error"))
            continue
        if want is dict:
            out[key] = {k: e for k, v in value.items() if (e := _shape(v, f"{key}[{k}]", diags)) is not None}
        else:
            out[key] = [e for i, v in enumerate(value) if (e := _shape(v, f"{key}[{i}]", diags)) is not None]
    return out, diags


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
    diags: list[dict] = []
    removed_nodes = 0

    for nid in enrichment.get("remove_nodes", []):
        if nid not in nodes:
            continue
        removed_nodes += 1
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

    # What the agent adds goes through the same checks as tours: cited files must exist, text is
    # scanned for credentials, and a connection without valid evidence is left out.
    ev = Evidence(data)
    added_nodes = added_edges = 0
    for k, an in enumerate(enrichment.get("add_nodes", [])):
        if not an.get("id") or an["id"] in nodes:
            continue
        subject = f"add_nodes[{k}] {an['id']}"
        kind = an.get("kind") if an.get("kind") in KINDS else "external"
        parent = an.get("parent") if an.get("parent") in nodes else None
        n = {"id": an["id"], "name": _clean(an.get("name") or an["id"], 120, subject, diags), "kind": kind,
             "layer": an.get("layer") if an.get("layer") in LAYER_IDS else KINDS.get(kind), "parent": parent,
             "description": _clean(an.get("description"), 2000, subject, diags), "purpose": _clean(an.get("purpose"), 2000, subject, diags),
             "tech": [_clean(t, 60, subject, diags) for t in an.get("tech") or [] if isinstance(t, str)],
             "locations": ev.check(an.get("locations"), subject, diags), "source": "agent"}
        data["nodes"].append(n)
        nodes[n["id"]] = n
        added_nodes += 1

    for k, ae in enumerate(enrichment.get("add_edges", [])):
        src, dst = ae.get("source"), ae.get("target")
        subject = f"add_edges[{k}] {src}->{dst}"
        if src not in nodes or dst not in nodes:
            diags.append(diag("edge/unknown-endpoint", subject, "the source or the target is not in the map; the connection was left out",
                              "use node ids from archmap.json", "error"))
            continue
        evidence = ev.check(ae.get("evidence"), subject, diags)
        if not evidence:
            diags.append(diag("edge/without-evidence", subject, "added connection cites no real file and line; it was left out",
                              'add "evidence": [{"file": ..., "line": ...}] pointing at the code that makes the connection', "error"))
            continue
        data["edges"].append({"source": src, "target": dst, "kind": ae.get("kind") if ae.get("kind") in EDGE_KINDS else "uses",
                              "description": _clean(ae.get("description"), 2000, subject, diags), "evidence": evidence,
                              "confidence": "INFERRED", "count": 1, "source_tag": "agent"})
        added_edges += 1

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
            n["layer"] = (patch.get("layer") if patch.get("layer") in LAYER_IDS else None) or KINDS[patch["kind"]] or n["layer"]
        n["source"] = "agent"
        if patch.get("hash") and patch["hash"] != n.get("hash"):
            n["stale"] = True

    data["link_notes"] = {k: v.get("description", "") for k, v in (enrichment.get("links") or {}).items()
                          if v.get("description") and k not in removed_pairs}
    data["enrichment_stats"] = {
        "nodes": sum(1 for nid in (enrichment.get("nodes") or {}) if nid in nodes),
        "links": len(data["link_notes"]),
        "added_nodes": added_nodes, "added_edges": added_edges,
        "removed_nodes": removed_nodes, "removed_edges": len(removed_pairs),
    }
    data["diagnostics"] = diags
    return data
