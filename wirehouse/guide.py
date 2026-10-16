"""Tours and quests: the guided, game-like layer on top of the map.

A *tour* walks the worker through a list of stops (each a node with a short text and
the file + line it is based on), or along a route between two nodes. A *quest* asks
the reader to find something ("Where are passwords checked?") and counts as found
when they inspect the answer.

The coding agent writes tours and quests into enrichment.json. They are checked here before
they reach the page: every node must exist and every citation must point at a real
file and line in the project. Problems come back as diagnostics with a stable code,
the exact subject and how to fix it, so they can be repaired one by one. When
enrichment has none, Wirehouse makes a few from what the scan found.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

MAX_STOPS = 12
MAX_TEXT = 600
MAX_TITLE = 60
ZONE_ORDER = ["clients", "edge", "services", "data", "external", "ops"]
KIND_ORDER = ["user", "frontend", "mobile", "desktop", "gateway", "auth", "service", "function", "worker", "library", "tests",
              "database", "search", "cache", "queue", "storage", "ai", "external", "infra", "ci", "observability"]
DATA_KINDS = ["database", "cache", "storage", "queue", "search"]
# Values that look like credentials. Authored text should never carry them; if it does, they are cut out.
SECRET_LIKE = re.compile(
    r"\b(?:sk|pk|rk|whsec)_(?:live|test)?_?[A-Za-z0-9_]{8,}|\bghp_[A-Za-z0-9]{10,}|\bgithub_pat_[A-Za-z0-9_]{10,}|\bAKIA[0-9A-Z]{16}\b"
    r"|\bxox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b[a-z]+://[^\s:/@]+:[^\s@]+@"
    r"|(?i:\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|token)\s*[:=]\s*['\"]?[^\s'\",;]{4,})")


def diag(code: str, subject: str, message: str, fix: str, severity: str = "warning") -> dict:
    return {"code": code, "severity": severity, "subject": subject, "message": message, "fix": fix}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "tour"


def _clean(text, limit: int, subject: str, diags: list) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if SECRET_LIKE.search(text):
        diags.append(diag("guide/secret-like-text", subject, "text contained something that looks like a credential; it was removed",
                          "describe what the value is for, never the value itself", "error"))
        text = SECRET_LIKE.sub("[redacted]", text)
    return text[:limit]


class Evidence:
    """Checks `{"file": ..., "line": ...}` citations against the scanned project."""

    def __init__(self, data: dict):
        self.root = Path(data.get("project", {}).get("root") or ".")
        self.lines: dict[str, int] = {n["path"]: n.get("lines", 0) for n in data["nodes"] if n.get("kind") == "file" and n.get("path")}

    def _line_count(self, rel: str) -> int | None:
        if rel in self.lines:
            return self.lines[rel]
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts or re.match(r"^[A-Za-z]:", rel):
            return None
        path = self.root / rel
        try:
            if not path.resolve().is_relative_to(self.root.resolve()) or not path.is_file():
                return None
            if p.name.startswith(".env") and not re.search(r"example|sample|template|dist", p.name, re.I):
                return 10 ** 9   # real env files are never opened: existence is enough
            if path.stat().st_size > 5_000_000:
                return 10 ** 9
            with path.open("rb") as fh:
                data = fh.read()
            count = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
        except OSError:
            return None
        self.lines[rel] = count
        return count

    def check(self, items, subject: str, diags: list) -> list[dict]:
        out = []
        for ev in items or []:
            if not isinstance(ev, dict) or not ev.get("file"):
                diags.append(diag("evidence/missing-file", subject, f"citation {ev!r} has no file",
                                  'give each citation as {"file": "path/from/project/root", "line": N}'))
                continue
            rel = str(ev["file"]).replace("\\", "/")
            while rel.startswith("./"):
                rel = rel[2:]
            count = self._line_count(rel)
            if count is None:
                diags.append(diag("evidence/file-not-found", subject, f"`{rel}` is not a file in the project",
                                  "cite a path relative to the project root, as listed in archmap.json", "error"))
                continue
            line = ev.get("line")
            try:
                line = int(line) if line is not None else None
            except (TypeError, ValueError):
                line = None
            if line is not None and (line < 1 or line > count):
                diags.append(diag("evidence/line-out-of-range", subject, f"`{rel}` has {count} lines, cited line {line}",
                                  "open the file and cite the line the claim is based on", "error"))
                continue
            c = {"file": rel}
            if line:
                c["line"] = line
            out.append(c)
        return out[:3]


def validate(data: dict, enrichment: dict) -> tuple[list, list, list]:
    """The agent's tours and quests -> (tours, quests, diagnostics). Invalid parts are dropped, not guessed."""
    nodes = {n["id"] for n in data["nodes"]}
    ev = Evidence(data)
    diags: list[dict] = []
    tours, seen = [], set()
    for k, t in enumerate(enrichment.get("tours") or []):
        if not isinstance(t, dict):
            continue
        title = _clean(t.get("title"), MAX_TITLE, f"tours[{k}]", diags) or f"Tour {k + 1}"
        tid = _slug(str(t.get("id") or title))
        while tid in seen:
            tid += "-2"
        seen.add(tid)
        subject = f"tours[{tid}]"
        tour = {"id": tid, "title": title, "intro": _clean(t.get("intro"), MAX_TEXT, subject, diags)}
        if t.get("route"):
            r = t["route"]
            if isinstance(r, list) and len(r) == 2 and all(x in nodes for x in r) and r[0] != r[1]:
                tour["route"] = list(r)
                tours.append(tour)
            else:
                diags.append(diag("tour/unknown-node", subject, f"route {r!r} needs two different known node ids",
                                  "use [from_id, to_id] with ids from archmap.json", "error"))
            continue
        stops = []
        for j, s in enumerate(t.get("stops") or []):
            ss = f"{subject}.stops[{j}]"
            nid = s.get("node") if isinstance(s, dict) else None
            if nid not in nodes:
                diags.append(diag("tour/unknown-node", ss, f"node {nid!r} is not in the map", "use an id from archmap.json", "error"))
                continue
            stop = {"node": nid, "title": _clean(s.get("title"), MAX_TITLE, ss, diags), "text": _clean(s.get("text"), MAX_TEXT, ss, diags),
                    "evidence": ev.check(s.get("evidence"), ss, diags)}
            if not stop["text"]:
                diags.append(diag("tour/stop-without-text", ss, "stop has no text", "say in 1-3 sentences what the reader sees here and why it matters"))
            if not stop["evidence"]:
                diags.append(diag("tour/stop-without-evidence", ss, "stop cites no file and line",
                                  'add "evidence": [{"file": ..., "line": ...}] pointing at the code the text is based on'))
            stops.append(stop)
        if len(stops) > MAX_STOPS:
            diags.append(diag("tour/too-long", subject, f"{len(stops)} stops; only the first {MAX_STOPS} are kept", "split it into two tours"))
            stops = stops[:MAX_STOPS]
        if not stops:
            diags.append(diag("tour/empty", subject, "no valid stops", "give the tour stops or a route", "error"))
            continue
        tour["stops"] = stops
        tours.append(tour)

    quests, qseen = [], set()
    for k, q in enumerate(enrichment.get("quests") or []):
        if not isinstance(q, dict):
            continue
        question = _clean(q.get("question"), 160, f"quests[{k}]", diags)
        qid = _slug(str(q.get("id") or question))
        while qid in qseen:
            qid += "-2"
        qseen.add(qid)
        subject = f"quests[{qid}]"
        answers = q.get("answer")
        answers = [answers] if isinstance(answers, str) else list(answers or [])
        known = [a for a in answers if a in nodes]
        if len(known) < len(answers):
            diags.append(diag("quest/unknown-answer", subject, f"unknown answer ids {sorted(set(answers) - set(known))}",
                              "answers must be node ids from archmap.json", "error"))
        if not question or not known:
            diags.append(diag("quest/invalid", subject, "a quest needs a question and at least one known answer id", "fix or remove it", "error"))
            continue
        quests.append({"id": qid, "question": question, "answer": known, "hint": _clean(q.get("hint"), 240, subject, diags),
                       "explain": _clean(q.get("explain"), MAX_TEXT, subject, diags), "evidence": ev.check(q.get("evidence"), subject, diags)})
    return tours, quests, diags


def check_added_edges(data: dict, enrichment: dict) -> list[dict]:
    """Every add_edges entry must cite real code."""
    ev, diags = Evidence(data), []
    for k, ae in enumerate(enrichment.get("add_edges") or []):
        subject = f"add_edges[{k}] {ae.get('source')}->{ae.get('target')}"
        if not ae.get("evidence"):
            diags.append(diag("edge/without-evidence", subject, "added connection cites no file and line",
                              'add "evidence": [{"file": ..., "line": ...}]', "error"))
        else:
            ev.check(ae.get("evidence"), subject, diags)
    return diags


# ── made by Wirehouse when enrichment has none ─────────────────────────────────
def _tops(data):
    return [n for n in data["nodes"] if n["parent"] is None]


def _first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(parts[:n])[:MAX_TEXT]


def _block_graph(data):
    nodes = {n["id"]: n for n in data["nodes"]}

    def top(i):
        while nodes[i]["parent"]:
            i = nodes[i]["parent"]
        return i

    out, degree = defaultdict(set), defaultdict(int)
    for e in data["edges"]:
        a, b = top(e["source"]), top(e["target"])
        if a == b:
            continue
        degree[a] += 1
        degree[b] += 1
        if e["kind"] not in ("depends_on", "provisions"):
            out[a].add(b)
    return nodes, out, degree


def auto_tours(data: dict) -> list[dict]:
    nodes, out, degree = _block_graph(data)
    tops = _tops(data)
    if not tops:
        return []
    zone = lambda n: ZONE_ORDER.index(n["layer"]) if n.get("layer") in ZONE_ORDER else 2  # noqa: E731
    kind = lambda n: KIND_ORDER.index(n["kind"]) if n["kind"] in KIND_ORDER else 99  # noqa: E731
    keep = tops
    if len(tops) > 10:
        keep = sorted(tops, key=lambda n: -degree[n["id"]])[:10]
    keep = sorted(keep, key=lambda n: (zone(n), kind(n), n["name"].lower()))
    tours = [{
        "id": "main-floor", "title": "Walk the main floor", "auto": True,
        "intro": "One stop per block, from the entrance to the loading dock.",
        "stops": [{"node": n["id"], "title": n["name"], "text": _first_sentences(n.get("purpose") or "") + (" " if n.get("purpose") else "") + _first_sentences(n.get("description") or ""),
                   "evidence": [{"file": l["file"], **({"line": l["line"]} if l.get("line") else {})} for l in (n.get("locations") or [])[:1]]}
                  for n in keep],
    }]
    starts = [n["id"] for n in tops if n["kind"] == "user"] or [n["id"] for n in tops if n["layer"] == "clients"]
    stores = sorted([n for n in tops if n["kind"] in DATA_KINDS], key=lambda n: (DATA_KINDS.index(n["kind"]), -degree[n["id"]]))
    for s in starts[:1]:
        seen, frontier = {s}, [s]
        while frontier:   # block-level reachability, so the route tour is only offered when it exists
            frontier = [b for a in frontier for b in out[a] if b not in seen and not seen.add(b)]
        target = next((n for n in stores if n["id"] in seen), None)
        if target:
            tours.append({"id": "request", "title": f"Follow a request to {target['name']}", "auto": True,
                          "intro": f"The shortest recorded path from {nodes[s]['name']} to {target['name']}.", "route": [s, target["id"]]})
    return tours


def auto_quests(data: dict) -> list[dict]:
    nodes, out, degree = _block_graph(data)
    tops = _tops(data)
    names = lambda ns: ", ".join(n["name"] for n in ns[:4])  # noqa: E731
    quests = []
    stores = [n for n in tops if n["kind"] in ("database", "cache", "storage")]
    if stores:
        quests.append({"id": "find-data", "question": "Find where the data is kept", "answer": [n["id"] for n in stores],
                       "hint": "Head for the Data zone: silos, stacks of pucks and pallets.",
                       "explain": f"{names(stores)} hold the data. Amber pipes show who reads and writes it."})
    files = [n for n in data["nodes"] if n.get("kind") == "file" and not n.get("test")]
    eps = [(f, ep) for f in files for ep in f.get("endpoints", []) if ep.get("method") not in ("PAGE", None)]
    if eps:
        rank = {"POST": 0, "PUT": 1, "PATCH": 1, "DELETE": 2}
        f, ep = sorted(eps, key=lambda x: (rank.get(x[1]["method"], 3), -x[1]["path"].count("/"), x[1]["path"]))[0]
        top = f
        while top["parent"]:
            top = nodes[top["parent"]]
        quests.append({"id": "find-endpoint", "question": f"Which file handles {ep['method']} {ep['path']}?", "answer": [f["id"]],
                       "hint": f"It is inside {top['name']}. Walk in, or search with /.",
                       "explain": f"`{f['path']}` defines {ep['method']} {ep['path']} at line {ep.get('line', '?')}.",
                       "evidence": [{"file": f["path"], **({"line": ep["line"]} if ep.get("line") else {})}]})
    guards = [n for n in tops if n["kind"] in ("auth", "gateway")]
    if guards:
        quests.append({"id": "find-auth", "question": "Find what checks who is allowed in", "answer": [n["id"] for n in guards],
                       "hint": "The Gateway and auth zone sits between the clients and the services.",
                       "explain": f"{names(guards)} stand between users and the services. Pink pipes are sign-in traffic."})
    ext = [n for n in tops if n["kind"] in ("external", "ai") and any(n["id"] in out[a] for a in out)]
    if ext:
        quests.append({"id": "find-provider", "question": "Find a third-party service this system calls", "answer": [n["id"] for n in ext],
                       "hint": "Outside providers wait at the loading dock, at the back of the floor.",
                       "explain": f"Third parties called from the code: {names(ext)}."})
    tables = [n for n in data["nodes"] if n.get("kind") == "table"]
    if tables:
        t = sorted(tables, key=lambda n: n["name"])[0]
        quests.append({"id": "find-table", "question": f"Find the {t['name']} table", "answer": [t["id"]],
                       "hint": f"Tables sit on the racks inside {nodes[t['parent']]['name']}.",
                       "explain": t.get("description", ""),
                       "evidence": [{"file": l["file"], **({"line": l["line"]} if l.get("line") else {})} for l in (t.get("locations") or [])[:1]]})
    for q in quests:
        q["auto"] = True
    return quests[:5]


def apply(data: dict, enrichment: dict) -> dict:
    """Attach tours, quests and diagnostics to a merged archmap."""
    enrichment = enrichment or {}
    tours, quests, diags = validate(data, enrichment)
    diags += check_added_edges(data, enrichment)
    nodes, out, _ = _block_graph(data)

    def top(i):
        while nodes[i]["parent"]:
            i = nodes[i]["parent"]
        return i

    for t in tours:
        if t.get("route"):
            a, b = top(t["route"][0]), top(t["route"][1])
            seen, frontier = {a}, [a]
            while frontier:
                frontier = [y for x in frontier for y in out[x] if y not in seen and not seen.add(y)]
            if b not in seen and a != b:
                diags.append(diag("tour/no-recorded-path", f"tours[{t['id']}]", "no recorded connections lead from the first node to the second",
                                  "pick two nodes the map connects (trace downstream from the first in the page to check)"))
    # Descriptions and connection notes the agent wrote get the same credential check as tours.
    for n in data["nodes"]:
        if n.get("source") == "agent":
            for field in ("name", "description", "purpose"):
                if n.get(field) and SECRET_LIKE.search(str(n[field])):
                    n[field] = _clean(n[field], 2000, f"nodes[{n['id']}].{field}", diags)
    for key, note in list((data.get("link_notes") or {}).items()):
        if note and SECRET_LIKE.search(note):
            data["link_notes"][key] = _clean(note, 2000, f"links[{key}]", diags)
    data["tours"] = tours or auto_tours(data)
    data["quests"] = quests or auto_quests(data)
    data["diagnostics"] = diags
    return data
