"""Change review: what moved between an earlier map and this one.

Blocks and folders are compared by their content hash and files by their sha, so a block counts as
changed only when the code under it did. Connections are compared rolled up to top-level blocks,
the same pairs the page and `wirehouse export` show. Anything removed is listed by name: it is no
longer in the code, so it cannot be drawn.
"""

from __future__ import annotations

from wirehouse.enrich import top_links

MAX_LISTED = 300   # per list; counts stay exact


def _fingerprints(data: dict) -> dict[str, tuple[str, str | None]]:
    """id -> (level, content fingerprint) for top-level blocks and files."""
    out = {}
    for n in data["nodes"]:
        if n.get("parent") is None:
            out[n["id"]] = ("block", n.get("hash"))
        elif n.get("kind") == "file":
            out[n["id"]] = ("file", n.get("sha"))
    return out


def _brief(n: dict) -> dict:
    return {"id": n["id"], "name": n.get("name", n["id"]), "kind": n.get("kind", ""), "path": n.get("path", "")}


def compute(old: dict, new: dict) -> dict:
    before, after = _fingerprints(old), _fingerprints(new)
    old_nodes = {n["id"]: n for n in old["nodes"]}
    out: dict = {"against": {"commit": (old.get("repo") or {}).get("short"), "name": old.get("project", {}).get("name")}}
    for level in ("block", "file"):
        was = {i for i, (lv, _) in before.items() if lv == level}
        now = {i for i, (lv, _) in after.items() if lv == level}
        changed = sorted(i for i in was & now if before[i][1] and after[i][1] and before[i][1] != after[i][1])
        out[f"{level}s"] = {
            "added": sorted(now - was)[:MAX_LISTED],
            "removed": [_brief(old_nodes[i]) for i in sorted(was - now)][:MAX_LISTED],
            "changed": changed[:MAX_LISTED],
            "counts": {"added": len(now - was), "removed": len(was - now), "changed": len(changed)},
        }
    old_links, new_links = top_links(old), top_links(new)
    removed = []
    for key in sorted(set(old_links) - set(new_links)):
        L = old_links[key]
        removed.append({"key": key, "source": L["source"], "target": L["target"],
                        "source_name": old_nodes[L["source"]].get("name", L["source"]),
                        "target_name": old_nodes[L["target"]].get("name", L["target"]), "kinds": sorted(L["kinds"])})
    out["links"] = {
        "added": sorted(set(new_links) - set(old_links)),
        "removed": removed,
        "changed": sorted(k for k in set(old_links) & set(new_links) if old_links[k]["kinds"] != new_links[k]["kinds"]),
    }
    return out


def total(delta: dict) -> int:
    return sum(delta[level]["counts"][k] for level in ("blocks", "files") for k in ("added", "removed", "changed")) + \
        sum(len(delta["links"][k]) for k in ("added", "removed", "changed"))
