"""The archmap data model: node kinds, layers, edge kinds and small constructors.

archmap.json is the contract between the Python side (detection, enrichment)
and the renderer. Every node has a `parent` (None for top-level blocks in the
warehouse); walking into a block shows its children. Edges are stored at the
most specific level known (usually file -> file or file -> resource) and the
renderer rolls them up to whatever level is on screen.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

# Warehouse floor zones, front (entrance) to back (loading dock).
LAYERS = [
    {"id": "clients", "name": "Clients", "hint": "Who or what starts a request"},
    {"id": "edge", "name": "Gateway & Auth", "hint": "Entry points, proxies and identity"},
    {"id": "services", "name": "Services", "hint": "Your running code: APIs, apps, workers"},
    {"id": "data", "name": "Data", "hint": "Databases, caches, queues and storage"},
    {"id": "external", "name": "External", "hint": "Third-party APIs and providers"},
    {"id": "ops", "name": "Ops", "hint": "CI/CD, infrastructure and observability"},
]

# kind -> default layer
KINDS = {
    "user": "clients",
    "frontend": "clients",
    "mobile": "clients",
    "desktop": "clients",
    "gateway": "edge",
    "auth": "edge",
    "service": "services",
    "worker": "services",
    "function": "services",
    "library": "services",
    "database": "data",
    "cache": "data",
    "queue": "data",
    "storage": "data",
    "search": "data",
    "external": "external",
    "ai": "external",
    "infra": "ops",
    "ci": "ops",
    "observability": "ops",
    "tests": "ops",
    # Inner levels (only visible inside rooms)
    "module": None,
    "file": None,
    "table": None,
    "resource": None,
}

EDGE_KINDS = {
    "imports": "Imports code from",
    "calls": "Calls over the network",
    "data": "Reads / writes data",
    "auth": "Authenticates with",
    "publishes": "Sends messages to",
    "depends_on": "Starts after / depends on",
    "provisions": "Provisions",
    "uses": "Uses",
    "references": "References (foreign key)",
}


def node(id: str, name: str, kind: str, *, parent: str | None = None, layer: str | None = None, **extra) -> dict:
    n = {
        "id": id,
        "name": name,
        "kind": kind,
        "layer": layer or KINDS.get(kind),
        "parent": parent,
        "description": "",
        "purpose": "",
        "tech": [],
        "locations": [],
        "source": "rule",
    }
    n.update(extra)
    return n


def edge(source: str, target: str, kind: str, *, description: str = "", evidence=None, confidence: str = "EXTRACTED", **extra) -> dict:
    e = {
        "source": source,
        "target": target,
        "kind": kind,
        "description": description,
        "evidence": list(evidence or []),
        "confidence": confidence,
    }
    e.update(extra)
    return e


def loc(file: str, line: int | None = None, label: str | None = None) -> dict:
    d = {"file": file}
    if line:
        d["line"] = int(line)
    if label:
        d["label"] = label
    return d
