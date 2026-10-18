"""Turn scan results into an archmap: nodes (with parents) and edges.

Pipeline:  scan -> per-file facts -> units -> infra -> Builder.run() -> archmap dict
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from wirehouse import __version__
from wirehouse.detectors.code import NOISE_HOSTS, FileFacts, analyze
from wirehouse.detectors.infra import Infra, detect_infra
from wirehouse.detectors.units import Unit, detect_units
from wirehouse.model import EDGE_KINDS, LAYERS, SCHEMA_VERSION, edge, loc, node
from wirehouse.redact import scrub
from wirehouse.repo import repo_info
from wirehouse.scan import MAX_FILE_BYTES, ScanResult, SourceFile, as_dict, scan
from wirehouse.signatures import (
    BY_ID, Signature, match_cs_namespace, match_go, match_host, match_image, match_npm, match_nuget, match_py_import,
    match_pypi, match_value,
)

KIND_LABEL = {
    "user": "people using the system", "frontend": "web frontend", "mobile": "mobile app", "desktop": "desktop app",
    "gateway": "gateway / reverse proxy", "auth": "authentication provider", "service": "backend service",
    "worker": "background worker / job", "function": "serverless function", "library": "shared library",
    "database": "database", "cache": "cache", "queue": "queue / messaging", "storage": "file / object storage",
    "search": "search / vector index", "external": "third-party API", "ai": "AI model provider", "infra": "infrastructure",
    "ci": "CI/CD pipeline", "observability": "observability tool", "tests": "test project",
}
RES_EDGE_KIND = {"database": "data", "cache": "data", "storage": "data", "search": "data", "queue": "publishes",
                 "auth": "auth", "external": "calls", "ai": "calls", "observability": "uses", "gateway": "calls"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "[::1]"}
CALLISH = re.compile(r"fetch|axios|request|httpx|requests\.|urlopen|HttpClient|ENDPOINT|BASE_URL|_URL|baseURL|baseUrl|api|ky\.|got\(|\.post\(|\.get\(", re.I)
# Env vars that describe *this* app's own address or allowed callers, not outgoing calls.
# (NEXT_PUBLIC_API_URL and friends are how a frontend finds its API, so PUBLIC_ alone says nothing.)
SELF_URL_VARS = re.compile(r"CORS|ORIGIN|ALLOWED|REDIRECT|CALLBACK|APP_URL|SITE_URL|BASE_PATH|NEXTAUTH_URL|AUTH_URL|TRUSTED"
                           r"|FRONTEND_(?:HOST|URL|ORIGIN|BASE)|CLIENT_URL|UI_URL|WEB_URL|DASHBOARD_URL", re.I)
STRING_LITERAL = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`")
URL_ANY = re.compile(r"\b[a-z][\w+.-]{0,30}://\S+", re.I)   # bounded scheme: long dotted words were quadratic
COMMENT_START = re.compile(r"(?:^|\s)(?:#|//|/\*|\*|--)")
JS_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"]


def _strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas from JSONC (tsconfig) without touching strings like "**/*.ts"."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _basename(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def _file_instance(value: str) -> str | None:
    r"""The file a file-based database string names (`app.db`), never the rest of it.

    `Data Source=app.sqlite;Password=...` keeps only `app.sqlite`, and `sqlite:///C:\Users\me\app.db`
    only `app.db`: the instance ends up in node ids and names, so credentials and local folders must not.
    """
    m = re.search(r"\b(?:data\s*source|datasource|filename)\s*=\s*([^;]+)", value, re.I)
    v = m.group(1) if m else value
    v = v.split("?")[0].split(";")[0].strip().strip("'\"")
    name = re.split(r"[\\/]", v.rstrip("\\/"))[-1]
    return name or None


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


class Builder:
    def __init__(self, scan_res: ScanResult, facts: dict[str, FileFacts], units: list[Unit], infra: Infra):
        self.scan = scan_res
        self.facts = facts
        self.units = units
        self.infra = infra
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}
        self.files: dict[str, SourceFile] = {sf.rel: sf for sf in scan_res.sources}
        self.file_unit: dict[str, Unit] = {}
        self.service_target: dict[str, str] = {}   # compose service name -> node id
        self.port_target: dict[int, str] = {}       # port -> unit node id
        self.res_via: dict[str, list[str]] = defaultdict(list)
        self.orm_files: dict[str, Signature] = {}
        for u in units:
            for f in u.files:
                self.file_unit[f.rel] = u

    # ── node / edge helpers ───────────────────────────────────────────────
    def add_node(self, n: dict) -> dict:
        if n["id"] in self.nodes:
            return self.nodes[n["id"]]
        self.nodes[n["id"]] = n
        return n

    def add_edge(self, source: str, target: str, kind: str, *, evidence=None, description: str = "", confidence="EXTRACTED", **extra):
        if not source or not target or source == target or source not in self.nodes or target not in self.nodes:
            return
        key = (source, target, kind)
        e = self.edges.get(key)
        if e is None:
            e = edge(source, target, kind, description=description, confidence=confidence, **extra)
            e["count"] = 0
            self.edges[key] = e
        e["count"] += 1
        for ev in evidence or []:
            if len(e["evidence"]) < 12 and ev not in e["evidence"]:
                e["evidence"].append(ev)
        if confidence == "EXTRACTED":
            e["confidence"] = "EXTRACTED"
        for k, v in extra.items():
            if k == "via" and v:
                e.setdefault("via", [])
                for item in (v if isinstance(v, list) else [v]):
                    if item not in e["via"]:
                        e["via"].append(item)

    def note_via(self, node_id: str, text: str):
        if text not in self.res_via[node_id] and len(self.res_via[node_id]) < 8:
            self.res_via[node_id].append(text)

    def res_node(self, sig: Signature, instance: str | None = None, *, compose_service: str | None = None) -> str:
        nid = f"res:{sig.id}" + (f":{instance}" if instance else "")
        if nid not in self.nodes:
            name = sig.name + (f" · {instance}" if instance else "")
            n = node(nid, name, sig.kind, tech=[sig.tech], signature=sig.id)
            if compose_service:
                n["compose"] = [compose_service]
            self.add_node(n)
        return nid

    def _has_res(self, sig: Signature) -> bool:
        return any(nid == f"res:{sig.id}" or nid.startswith(f"res:{sig.id}:") for nid in self.nodes)

    def res_for(self, sig: Signature) -> str:
        """The node an import/dependency of `sig` should point at (a single instance if there is exactly one)."""
        insts = [nid for nid in self.nodes if nid == f"res:{sig.id}" or nid.startswith(f"res:{sig.id}:")]
        if len(insts) == 1:
            return insts[0]
        if f"res:{sig.id}" in insts:
            return f"res:{sig.id}"
        if insts:
            return sorted(insts)[0]
        return self.res_node(sig)

    # ── pipeline ──────────────────────────────────────────────────────────
    def run(self) -> dict:
        self._map_compose()
        self._unit_nodes()
        self._tree()
        self._internal_imports()
        self._env_and_urls()     # creates instance-specific resources first
        self._file_resources()
        self._manifest_resources()
        self._orm_edges()
        self._tables()
        self._compose_edges()
        self._infra_items()
        self._users()
        self._postprocess()
        return self._output()

    # compose services -> units / resources
    def _map_compose(self):
        units_by_dir = defaultdict(list)
        for u in self.units:
            units_by_dir[u.dir].append(u)
        for cs in self.infra.compose:
            if cs.build_context is None:
                sigs = [s for s in match_image(cs.image) if s.role == "block"]
                if sigs:
                    self.service_target[cs.name] = self.res_node(sigs[0], None if not self._has_other_instance(sigs[0]) else cs.name,
                                                                 compose_service=cs.name)
                    self.note_via(self.service_target[cs.name], f"docker-compose service `{cs.name}` (image `{cs.image}`)")
                    self.nodes[self.service_target[cs.name]].setdefault("locations", []).append(loc(cs.file, cs.line))
                else:
                    nid = f"svc:{cs.name}"
                    self.add_node(node(nid, cs.name, "service", tech=[cs.image or "container"], compose=[cs.name],
                                       locations=[loc(cs.file, cs.line)]))
                    self.note_via(nid, f"docker-compose service `{cs.name}` (image `{cs.image}`)")
                    self.service_target[cs.name] = nid
                continue
            df = self.infra.dockerfiles.get(cs.dockerfile or "")
            cmd = cs.command or (df.cmd if df else "")
            unit = self._unit_from_command(cmd, cs.build_context, df, cs.dockerfile)
            if unit is None:
                nid = f"svc:{cs.name}"
                self.add_node(node(nid, cs.name, "service", tech=["container"], compose=[cs.name], locations=[loc(cs.file, cs.line)]))
                self.service_target[cs.name] = nid
                continue
            if re.search(r"(?:^|[-_])(?:tests?|e2e|playwright|cypress|selenium)(?:$|[-_])", cs.name) or \
                    re.search(r"playwright|cypress", cs.dockerfile or "", re.I):
                self.service_target[cs.name] = unit.id   # still reachable by name, but not "how it runs"
                continue
            unit.compose_services.append(cs.name)
            # A command override that is not a server (e.g. `python -m pkg.ingest run`) is a one-shot job:
            # it does not listen on the port the shared image EXPOSEs.
            serves = not cs.command or re.search(r"uvicorn|gunicorn|hypercorn|daphne|runserver|flask run|node|next|npm|pnpm|yarn|serve|dotnet|--port", cs.command)
            unit.ports += cs.ports + (df.expose if df and serves else [])
            m = re.search(r"--port[ =](\d{2,5})|-p[ =](\d{2,5})", cmd) if serves else None
            if m:
                unit.ports.append(int(m.group(1) or m.group(2)))
            self.service_target[cs.name] = unit.id
        for u in self.units:
            ports = set(u.ports) or ({int(u.props["default_port"])} if u.props.get("default_port") else set())
            for p in ports:
                self.port_target.setdefault(p, u.id)

    def _has_other_instance(self, sig: Signature) -> bool:
        return sum(1 for cs in self.infra.compose if cs.build_context is None and sig in match_image(cs.image)) > 1

    def _unit_from_command(self, cmd: str, context: str, df, dockerfile: str | None = None) -> Unit | None:
        paths = []
        for m in re.finditer(r"-m\s+([\w.]+)", cmd):
            paths.append(m.group(1).replace(".", "/"))
        for m in re.finditer(r"\b([A-Za-z_][\w.]*):[A-Za-z_]\w*\b", cmd):
            if "." in m.group(1):
                paths.append(m.group(1).replace(".", "/"))
        for m in re.finditer(r"([\w./-]+\.(?:py|js|mjs|cjs|ts|dll))\b", cmd):
            paths.append(m.group(1).lstrip("./"))
        base = context or ""
        for p in paths:
            full = f"{base}/{p}" if base else p
            best = None
            for u in self.units:
                if (u.dir and (full == u.dir or full.startswith(u.dir + "/"))) and (best is None or len(u.dir) > len(best.dir)):
                    best = u
            if best:
                return best
        low = (cmd + " " + (df.base if df else "")).lower()
        fam = "js" if re.search(r"\b(node|npm|pnpm|yarn|bun|next|nuxt)\b", low) else \
              "python" if re.search(r"python|uvicorn|gunicorn|celery|hypercorn|daphne", low) else \
              "dotnet" if "dotnet" in low else \
              "go" if re.search(r"\bgo (?:run|build)\b|golang", low) else None
        cands = [u for u in self.units if fam is None or u.family == fam]
        df_dir = _dirname(dockerfile) if dockerfile else None
        if df_dir and df_dir != base:
            by_df = [u for u in cands if u.dir == df_dir]
            if len(by_df) == 1:
                return by_df[0]
        exact = [u for u in cands if u.dir == base]
        if exact:
            return exact[0]
        inside = [u for u in cands if base == "" or u.dir.startswith(base + "/")]
        if len(inside) == 1:
            return inside[0]
        containing = sorted([u for u in cands if u.dir == "" or base.startswith(u.dir + "/")], key=lambda x: -len(x.dir))
        return containing[0] if containing else None

    def _unit_nodes(self):
        project = self.scan.root.name
        taken = Counter()
        for u in self.units:
            if u.dir == "":
                primary = [s for s in u.compose_services if s]
                u.name = primary[0] if primary else (u.pkg_name or project)
            else:
                u.name = _basename(u.dir)
            taken[u.name] += 1
        for u in self.units:
            if taken[u.name] > 1:
                u.name = f"{u.name} ({ {'js': 'JS', 'python': 'Python', 'dotnet': '.NET', 'go': 'Go'}[u.family] })"
        for u in self.units:
            n = node(u.id, u.name, u.kind, tech=list(dict.fromkeys(u.tech)), path=u.dir or ".", family=u.family,
                     framework=u.framework, compose=u.compose_services, ports=sorted(set(u.ports)),
                     locations=[loc(m) for m in u.manifests])
            self.add_node(n)

    # directories and files inside each unit
    def _tree(self):
        for u in self.units:
            dir_ids: dict[str, str] = {u.dir: u.id}

            def ensure_dir(path: str) -> str:
                if path in dir_ids:
                    return dir_ids[path]
                parent = ensure_dir(_dirname(path) if _dirname(path) != path else u.dir)
                if not path.startswith(u.dir) and u.dir:
                    return u.id
                nid = f"dir:{path}"
                if nid in self.nodes:
                    nid = f"dir:{path}#{u.family}"
                self.add_node(node(nid, _basename(path), "module", parent=parent, path=path))
                dir_ids[path] = nid
                return nid

            for sf in sorted(u.files, key=lambda s: s.rel):
                d = _dirname(sf.rel)
                if u.dir and not (d == u.dir or d.startswith(u.dir + "/")):
                    d = u.dir
                parent = ensure_dir(d) if d != u.dir else u.id
                ff = self.facts[sf.rel]
                n = node(f"file:{sf.rel}", _basename(sf.rel), "file", parent=parent, path=sf.rel, lang=sf.lang,
                         lines=sf.lines, sha=sf.sha, locations=[loc(sf.rel, 1)])
                if sf.is_test:
                    n["test"] = True
                if ff.doc:
                    n["doc"] = ff.doc
                if ff.symbols:
                    n["symbols"] = ff.symbols
                if ff.endpoints:
                    n["endpoints"] = [dict(e, file=sf.rel) for e in ff.endpoints]
                self.add_node(n)
        self._collapse_chains()

    def _collapse_chains(self):
        children = defaultdict(list)
        for n in self.nodes.values():
            if n["parent"]:
                children[n["parent"]].append(n["id"])
        changed = True
        while changed:
            changed = False
            for nid in list(self.nodes):
                n = self.nodes.get(nid)
                if not n or n["kind"] != "module":
                    continue
                kids = children.get(nid, [])
                if len(kids) == 1 and self.nodes[kids[0]]["kind"] == "module":
                    child = self.nodes[kids[0]]
                    child["name"] = f"{n['name']}/{child['name']}"
                    child["parent"] = n["parent"]
                    children[n["parent"]] = [c for c in children[n["parent"]] if c != nid] + [child["id"]]
                    del self.nodes[nid]
                    changed = True

    # file -> file import edges
    def _internal_imports(self):
        py_index = self._python_module_index()
        alias_maps = self._ts_aliases()
        go_index = self._go_package_index()
        for rel, ff in self.facts.items():
            sf = self.files[rel]
            src = f"file:{rel}"
            if src not in self.nodes or sf.is_test:
                continue
            for spec, line in ff.imports:
                targets: list[str] = []
                if sf.lang == "python":
                    targets = self._resolve_py(rel, spec, ff.py_from_names.get(spec, []), py_index)
                elif sf.lang in ("typescript", "javascript"):
                    t = self._resolve_js(rel, spec, alias_maps)
                    targets = [t] if t else []
                elif sf.lang == "go":
                    targets = go_index.get(spec, [])[:8]   # a Go import names a package: every file in its folder
                for t in targets:
                    if t != rel and f"file:{t}" in self.nodes:
                        self.add_edge(src, f"file:{t}", "imports", evidence=[loc(rel, line)])

    def _go_package_index(self) -> dict[str, list[str]]:
        """Import path -> the non-test files of that package, for packages inside this repo's Go modules."""
        out: dict[str, list[str]] = defaultdict(list)
        for u in self.units:
            if u.family != "go" or not u.pkg_name:
                continue
            for sf in u.files:
                if sf.lang != "go" or sf.is_test:
                    continue
                d = _dirname(sf.rel)
                sub = d[len(u.dir):].strip("/") if u.dir else d
                out[u.pkg_name + ("/" + sub if sub else "")].append(sf.rel)
        return out

    def _python_module_index(self) -> dict[str, str]:
        roots = {""} | {u.dir for u in self.units if u.family == "python"}
        roots |= {u.dir + "/src" if u.dir else "src" for u in self.units if u.family == "python"}
        index: dict[str, str] = {}
        for rel, sf in self.files.items():
            if sf.lang != "python":
                continue
            for r in roots:
                if r and not rel.startswith(r + "/"):
                    continue
                sub = rel[len(r) + 1:] if r else rel
                mod = sub[:-3].replace("/", ".")
                if mod.endswith(".__init__"):
                    mod = mod[: -len(".__init__")]
                index.setdefault(mod, rel)
        return index

    def _resolve_py(self, rel: str, mod: str, names: list[str], index: dict[str, str]) -> list[str]:
        if mod.startswith("."):
            dots = len(mod) - len(mod.lstrip("."))
            pkg_parts = _dirname(rel).split("/") if _dirname(rel) else []
            pkg_parts = pkg_parts[: len(pkg_parts) - (dots - 1)] if dots > 1 else pkg_parts
            rest = mod.lstrip(".")
            base_path = "/".join(pkg_parts + (rest.split(".") if rest else []))
            cands = [base_path + "/" + n for n in names] + [base_path]
            out = []
            for c in cands:
                for p in (c + ".py", c + "/__init__.py"):
                    if p in self.files:
                        out.append(p)
                        break
            return out[:8]
        out = []
        for n in names:
            if f"{mod}.{n}" in index:
                out.append(index[f"{mod}.{n}"])
        if mod in index:
            out.append(index[mod])
        return out[:8]

    def _ts_aliases(self) -> list[tuple[str, list[tuple[str, list[str]]], str]]:
        out = []
        for rel in self.scan.configs.get("tsconfig", []):
            try:
                data = as_dict(json.loads(_strip_jsonc(self.scan.read(rel))))
            except ValueError:
                continue
            co = as_dict(data.get("compilerOptions"))
            base = _dirname(rel)
            base_url = co.get("baseUrl") if isinstance(co.get("baseUrl"), str) else None
            root = os.path.normpath(os.path.join(base, base_url)).replace("\\", "/") if base_url else base
            root = "" if root == "." else root
            paths = [(k, [t for t in v if isinstance(t, str)]) for k, v in as_dict(co.get("paths")).items() if isinstance(v, list)]
            out.append((base, paths, root))
        out.sort(key=lambda x: -len(x[0]))
        return out

    def _try_js(self, candidate: str) -> str | None:
        candidate = os.path.normpath(candidate).replace("\\", "/")
        if candidate.startswith("../"):
            return None
        candidate = "" if candidate == "." else candidate
        if candidate in self.files:
            return candidate
        stem = re.sub(r"\.(m|c)?js$", "", candidate)
        for ext in JS_EXTS:
            if stem + ext in self.files:
                return stem + ext
        for ext in JS_EXTS:
            p = f"{candidate}/index{ext}" if candidate else f"index{ext}"
            if p in self.files:
                return p
        return None

    def _resolve_js(self, rel: str, spec: str, alias_maps) -> str | None:
        if spec.startswith("."):
            return self._try_js(os.path.join(_dirname(rel), spec))
        for base, paths, root in alias_maps:
            if base and not rel.startswith(base + "/"):
                continue
            for pattern, targets in paths:
                pre = pattern.rstrip("*")
                if (pattern.endswith("*") and spec.startswith(pre)) or spec == pattern:
                    rest = spec[len(pre):] if pattern.endswith("*") else ""
                    for t in targets:
                        cand = os.path.join(root, t.replace("*", rest))
                        hit = self._try_js(cand)
                        if hit:
                            return hit
            break
        return None

    # env vars + URLs -> services / resources
    def _env_target(self, value: str, var: str) -> tuple[str | None, str]:
        v = value.strip()
        if not v or v.startswith("${") and v.endswith("}") and ":-" not in v:
            return None, ""
        m = re.match(r"\$\{\w+:-([^}]*)\}", v)
        if m:
            v = m.group(1)
        sigs = match_value(v)
        if sigs:
            sig = sigs[0]
            host = None
            um = re.match(r"\w[\w+.-]*://(?:[^@/]*@)?([A-Za-z0-9_.-]+)", v)
            if um:
                host = um.group(1).lower()
                if host in self.service_target and self.service_target[host].startswith(f"res:{sig.id}"):
                    return self.service_target[host], f"{var} → {sig.name} (compose service `{host}`)"
            inst = None
            if any(s.startswith(".") for s in sig.schemes) and "://" not in v.replace(":///", "://x") or "sqlite" in v.lower():
                inst = _file_instance(v)
            nid = self.res_node(sig, inst)
            return nid, f"{var} → {sig.name}" + (f" `{inst}`" if inst else "")
        um = re.match(r"(?:https?|wss?|grpc)://([A-Za-z0-9_.-]+)(?::(\d+))?", v)
        if um:
            host, port = um.group(1).lower(), um.group(2)
            if host in self.service_target:
                return self.service_target[host], f"{var} → compose service `{host}`"
            if host in LOCAL_HOSTS and port and int(port) in self.port_target:
                return self.port_target[int(port)], f"{var} → localhost:{port}"
            sigs = match_host(host)
            if sigs:
                return self.res_node(sigs[0]), f"{var} → {host}"
        return None, ""

    def _env_and_urls(self):
        by_name: dict[str, list] = defaultdict(list)
        for ev in self.infra.env:
            by_name[ev.name].append(ev)
        known = set(by_name)
        # sig hints from env var *names* (e.g. OPENROUTER_API_KEY) when no value is given
        name_hints = {}
        for name in known:
            low = name.lower()
            for sig in (BY_ID.get(i) for i in ("openrouter", "openai", "anthropic", "stripe", "sendgrid", "resend", "logodev",
                                               "sentry", "clerk", "supabase", "twilio", "posthog", "gemini", "mistral", "groq")):
                key = sig.id.replace("_", "")
                if low.startswith(key) or f"_{key}_" in f"_{low}_" or (sig.id == "logodev" and "logo_dev" in low):
                    name_hints[name] = sig
        for rel, ff in self.facts.items():
            sf = self.files[rel]
            src = f"file:{rel}"
            if src not in self.nodes or sf.is_test:
                continue
            unit = self.file_unit.get(rel)
            refs = list(ff.env) + [(n, l) for n, l in ff.upper_literals if n in known]
            seen = set()
            for var, line in refs:
                if var in seen or SELF_URL_VARS.search(var):
                    continue
                seen.add(var)
                defs = by_name.get(var, [])
                # Prefer the value compose sets for this unit's own service
                defs = sorted(defs, key=lambda d: (0 if unit and d.service in unit.compose_services else 1 if d.service is None else 2, d.commented))
                target, why = None, ""
                for d in defs:
                    target, why = self._env_target(d.value, var)
                    if target:
                        break
                if not target and var in name_hints:
                    target = self.res_for(name_hints[var])
                    why = f"{var} configures {name_hints[var].name}"
                if target and target != (unit.id if unit else None):
                    kind = self._edge_kind_for(target)
                    self.add_edge(src, target, kind, evidence=[loc(rel, line, var)], description=why, env=var)
                    if target.startswith("res:"):
                        self.note_via(target, f"env var `{var}`")
            src_lines = sf.text.splitlines()
            for host, port, line in ff.service_urls:
                # judge the code on the line, not its strings: `{mode: 'cors'}` is not a CORS setting
                if SELF_URL_VARS.search(STRING_LITERAL.sub("", src_lines[line - 1] if line <= len(src_lines) else "")):
                    continue
                target = None
                if host in self.service_target:
                    target = self.service_target[host]
                elif host in LOCAL_HOSTS and port in self.port_target:
                    target = self.port_target[port]
                if target and target != (unit.id if unit else None):
                    self.add_edge(src, target, self._edge_kind_for(target), evidence=[loc(rel, line)],
                                  description=f"HTTP to {host}:{port}")
            lines = sf.text.splitlines()
            for host, line in ff.urls:
                sigs = [s for s in match_host(host) if s.role == "block"]
                own = lines[line - 1] if line <= len(lines) else ""
                at = own.find("://")
                if at >= 0 and COMMENT_START.search(own[:at]):
                    continue   # a URL in a comment documents, it does not call
                # "api" inside the URL itself (api.openai.com) must not make the line look like a request
                ctx = URL_ANY.sub(" ", " ".join(lines[max(0, line - 2): line]))
                if sigs:
                    # Only count it as a call when the code around it looks like a request,
                    # not when it is an href, a link in a comment or a URL in a data file.
                    # A bare mention never puts a block on the floor by itself.
                    if CALLISH.search(ctx) and not re.search(r"href|<a |@see|//\s*https?:", ctx):
                        t = self.res_for(sigs[0])
                        self.note_via(t, f"URL host `{host}`")
                        self.add_edge(src, t, self._edge_kind_for(t), evidence=[loc(rel, line, host)], description=f"URL {host} in request code")
                    elif self._has_res(sigs[0]):
                        self.note_via(self.res_for(sigs[0]), f"URL host `{host}`")
                    continue
                if host in LOCAL_HOSTS or any(host == h or host.endswith("." + h) for h in NOISE_HOSTS) or re.match(r"^\d+\.\d+", host):
                    continue
                if not CALLISH.search(ctx):
                    continue
                nid = f"ext:{host}"
                if nid not in self.nodes:
                    self.add_node(node(nid, host, "external", tech=["HTTP API"], confidence="INFERRED"))
                self.add_edge(src, nid, "calls", evidence=[loc(rel, line, host)], description=f"HTTP call to {host}", confidence="INFERRED")
                self.note_via(nid, f"URL in `{rel}`")

    def _edge_kind_for(self, target: str) -> str:
        n = self.nodes.get(target)
        if not n:
            return "calls"
        return RES_EDGE_KIND.get(n["kind"], "calls")

    # imports / code patterns -> resources
    def _file_resources(self):
        for rel, ff in self.facts.items():
            sf = self.files[rel]
            src = f"file:{rel}"
            if src not in self.nodes or sf.is_test:
                continue
            hits: list[tuple[Signature, int, str]] = []
            for spec, line in ff.imports:
                if sf.lang in ("typescript", "javascript"):
                    if spec.startswith((".", "/", "@/", "~/", "#")):
                        continue
                    parts = spec.split("/")
                    pkg = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
                    for s in match_npm(pkg):
                        hits.append((s, line, f"import `{spec}`"))
                    if spec.startswith("firebase/auth"):
                        hits.append((BY_ID["firebase_auth"], line, "import `firebase/auth`"))
                elif sf.lang == "python" and not spec.startswith("."):
                    for s in match_py_import(spec):
                        hits.append((s, line, f"import `{spec}`"))
                elif sf.lang == "csharp":
                    for s in match_cs_namespace(spec):
                        hits.append((s, line, f"using `{spec}`"))
                elif sf.lang == "go":
                    for s in match_go(spec):
                        hits.append((s, line, f"import `{spec}`"))
            for sid, line in ff.code_hits:
                hits.append((BY_ID[sid], line, "code pattern"))
            for sig, line, why in hits:
                if sig.role == "orm":
                    self.orm_files[rel] = sig
                    continue
                t = self.res_for(sig)
                self.add_edge(src, t, RES_EDGE_KIND.get(sig.kind, "uses"), evidence=[loc(rel, line)], description=why)
                self.note_via(t, why if "import" in why or "using" in why else f"{why} in `{rel}`")

    def _manifest_resources(self):
        for u in self.units:
            used = {e["target"] for e in self.edges.values() if self.file_unit.get(e["source"][5:]) is u}
            for dep in u.deps.values():
                if dep.dev:
                    continue
                matcher = {"js": match_npm, "python": match_pypi, "dotnet": match_nuget, "go": match_go}[u.family]
                for sig in matcher(dep.name):
                    if sig.role != "block":
                        if sig.role == "orm" and sig.name not in self.nodes[u.id]["tech"]:
                            self.nodes[u.id]["tech"].append(sig.name)
                        continue
                    t = self.res_for(sig)
                    self.note_via(t, f"dependency `{dep.name}` in {dep.manifest}")
                    if any(x == t for x in used):
                        continue
                    self.add_edge(u.id, t, RES_EDGE_KIND.get(sig.kind, "uses"), evidence=[loc(dep.manifest, dep.line)],
                                  description=f"declares dependency `{dep.name}` (no import found)", confidence="INFERRED")
            if u.family == "dotnet":
                for ref in u.project_refs:
                    for other in self.units:
                        if other.family == "dotnet" and other.dir == ref and other is not u:
                            self.add_edge(u.id, other.id, "imports", evidence=[loc(u.manifests[0])], description="ProjectReference")

    def _db_targets_near(self, rel: str) -> list[str]:
        def dbs_from(sources):
            c = Counter()
            for e in self.edges.values():
                if e["source"] in sources and self.nodes[e["target"]]["kind"] in ("database",):
                    c[e["target"]] += 1
            return [t for t, _ in c.most_common()]

        src = f"file:{rel}"
        r = dbs_from({src})
        if r:
            return r
        d = _dirname(rel)
        r = dbs_from({f"file:{x}" for x in self.files if _dirname(x) == d})
        if r:
            return r
        u = self.file_unit.get(rel)
        if u:
            r = dbs_from({u.id} | {f"file:{f.rel}" for f in u.files})
            if r:
                return r
        all_db = [n["id"] for n in self.nodes.values() if n["kind"] == "database"]
        return all_db if len(all_db) == 1 else []

    def _orm_edges(self):
        for rel, sig in self.orm_files.items():
            dbs = self._db_targets_near(rel)
            if dbs:
                self.add_edge(f"file:{rel}", dbs[0], "data", description=f"via {sig.name}", via=sig.name, confidence="INFERRED")
                if sig.name not in self.nodes[dbs[0]]["tech"]:
                    self.nodes[dbs[0]]["tech"].append(sig.name)

    def _tables(self):
        prisma_provider = {}
        for rel, sf in self.files.items():
            if sf.lang == "prisma":
                m = re.search(r'datasource\s+\w+\s*\{[^}]*provider\s*=\s*"(\w+)"', sf.text)
                if m:
                    prov = {"postgresql": "postgres", "mysql": "mysql", "sqlite": "sqlite", "sqlserver": "sqlserver",
                            "mongodb": "mongodb", "cockroachdb": "postgres"}.get(m.group(1))
                    if prov:
                        prisma_provider[rel] = self.res_for(BY_ID[prov])
                        self.add_edge(f"file:{rel}", prisma_provider[rel], "data", description="Prisma datasource", via="Prisma")
        fks = []
        for rel, ff in self.facts.items():
            if not ff.tables or f"file:{rel}" not in self.nodes:
                continue
            db = prisma_provider.get(rel) or (self._db_targets_near(rel) or [None])[0]
            if not db:
                continue
            for t in ff.tables:
                tid = f"table:{db[4:]}:{t['name'].lower()}"
                if tid not in self.nodes:
                    self.add_node(node(tid, t["name"], "table", parent=db, subkind=t["kind"],
                                       locations=[loc(rel, t["line"])], via=t["via"],
                                       description=f"{'View' if t['kind'] == 'view' else 'Table'} defined by {t['via']} in `{rel}` (line {t['line']})."))
                else:
                    self.nodes[tid]["locations"].append(loc(rel, t["line"]))
                if t.get("columns") and not self.nodes[tid].get("columns"):
                    self.nodes[tid]["columns"] = t["columns"]
                    fks.append((tid, db, rel, t))
                self.add_edge(f"file:{rel}", tid, "data", evidence=[loc(rel, t["line"])], description=f"defines {t['name']} ({t['via']})")
        # foreign keys become table -> table edges, once every table of the database is known
        for tid, db, rel, t in fks:
            for c in t["columns"]:
                fk = c.get("fk")
                target = f"table:{db[4:]}:{fk['table'].lower()}" if fk else None
                if target in self.nodes and target != tid:
                    self.add_edge(tid, target, "references", evidence=[loc(rel, t["line"])],
                                  description=f"{t['name']}.{c['name']} -> {self.nodes[target]['name']}.{fk['column']}")

    def _compose_edges(self):
        traefik = [n for n in self.nodes if n == "res:traefik" or n.startswith("res:traefik:")]
        for cs in self.infra.compose:
            tgt = self.service_target.get(cs.name)
            if "traefik" in cs.routed_by and traefik and tgt and tgt not in traefik:
                self.add_edge(traefik[0], tgt, "calls", evidence=[loc(cs.file, cs.line)],
                              description=f"routes requests to `{cs.name}` (Traefik labels)")
        for cs in self.infra.compose:
            src = self.service_target.get(cs.name)
            for dep in cs.depends_on:
                tgt = self.service_target.get(dep)
                if src and tgt:
                    self.add_edge(src, tgt, "depends_on", evidence=[loc(cs.file, cs.line)], description=f"compose `{cs.name}` depends_on `{dep}`")

    def _infra_items(self):
        groups = {"terraform": ("infra:terraform", "Terraform", "infra"), "kubernetes": ("infra:k8s", "Kubernetes", "infra"),
                  "ci": ("infra:ci", "CI/CD", "ci")}
        for it in self.infra.items:
            if it.group in groups:
                gid, gname, gkind = groups[it.group]
                if gid not in self.nodes:
                    self.add_node(node(gid, gname, gkind, tech=[gname]))
                leaf = f"{gid}:{it.file}:{it.name}"
                self.add_node(node(leaf, it.name, "resource", parent=gid, subkind=it.kind, description=it.detail,
                                   locations=[loc(it.file, it.line)]))
                self.nodes[gid]["locations"].append(loc(it.file, it.line))
                if it.image:
                    for sig in match_image(it.image):
                        if sig.role == "block":
                            self.add_edge(leaf, self.res_for(sig), "provisions", description=f"runs image `{it.image}`")
                if it.kind in ("database", "cache", "queue", "storage"):
                    same = [n["id"] for n in self.nodes.values() if n["kind"] == it.kind and n["parent"] is None and n["id"].startswith("res:")]
                    if len(same) == 1:
                        self.add_edge(leaf, same[0], "provisions", description=f"{it.detail} provisions this", confidence="INFERRED")
            elif it.group == "platform":
                nid = f"infra:platform:{it.name}"
                self.add_node(node(nid, it.name, "infra", tech=[it.name], description=it.detail, locations=[loc(it.file, it.line)]))
                d = _dirname(it.file)
                owner = sorted([u for u in self.units if u.dir == "" or d == u.dir or d.startswith(u.dir + "/")], key=lambda u: -len(u.dir))
                if owner:
                    self.add_edge(nid, owner[0].id, "provisions", evidence=[loc(it.file)], description=f"hosts {owner[0].name}")
            elif it.group == "gateway":
                nid = f"gw:{it.name}:{it.file}"
                self.add_node(node(nid, it.name, "gateway", tech=[it.name], description=it.detail, locations=[loc(it.file, it.line)]))
                for host in it.targets:
                    t = self.service_target.get(host.lower())
                    if t:
                        self.add_edge(nid, t, "calls", evidence=[loc(it.file)], description=f"proxies to `{host}`")

    def _users(self):
        clients = [n for n in self.nodes.values() if n["parent"] is None and n["kind"] in ("frontend", "mobile", "desktop")]
        gateways = [n for n in self.nodes.values() if n["parent"] is None and n["kind"] == "gateway"]
        # People reach the gateways, plus any client app no gateway routes to (an SPA served elsewhere).
        behind = {e["target"] for e in self.edges.values() if self.nodes[e["source"]]["kind"] == "gateway"}
        entry = gateways + [c for c in clients if c["id"] not in behind] if gateways else clients
        if not entry:
            entry = [n for n in self.nodes.values() if n["parent"] is None and n["kind"] == "service"
                     and any(c.get("endpoints") for c in self._descendant_files(n["id"]))]
        if not entry:
            return
        self.add_node(node("actor:users", "Users", "user", tech=["Browser / client"], confidence="INFERRED",
                           description="People (or client programs) using the system. Added by Wirehouse as the starting point of every request."))
        for n in entry:
            self.add_edge("actor:users", n["id"], "calls", description=f"use {n['name']}", confidence="INFERRED")

    def _descendant_files(self, nid: str):
        prefix_children = defaultdict(list)
        for n in self.nodes.values():
            if n["parent"]:
                prefix_children[n["parent"]].append(n)
        out, stack = [], [nid]
        while stack:
            cur = stack.pop()
            for c in prefix_children.get(cur, []):
                if c["kind"] == "file":
                    out.append(c)
                stack.append(c["id"])
        return out

    # descriptions, stats, hashes
    def _postprocess(self):
        nodes = self.nodes
        children = defaultdict(list)
        for n in nodes.values():
            if n["parent"]:
                children[n["parent"]].append(n["id"])

        def top(nid):
            while nodes[nid]["parent"]:
                nid = nodes[nid]["parent"]
            return nid

        tops = {nid: top(nid) for nid in nodes}
        # drop depends_on when the pair already has a real connection
        real_pairs = {(tops[e["source"]], tops[e["target"]]) for e in self.edges.values() if e["kind"] != "depends_on"}
        for key in [k for k, e in self.edges.items() if e["kind"] == "depends_on" and (tops[e["source"]], tops[e["target"]]) in real_pairs]:
            del self.edges[key]

        # aggregate stats bottom-up
        def agg(nid):
            n = nodes[nid]
            files = lines = eps = 0
            shas = []
            langs = Counter()
            if n["kind"] == "file":
                files, lines, eps = 1, n.get("lines", 0), len(n.get("endpoints", []))
                shas.append(n.get("sha", ""))
                langs[n.get("lang")] += 1
            for c in children.get(nid, []):
                f, l, e, s, lg = agg(c)
                files += f
                lines += l
                eps += e
                shas += s
                langs.update(lg)
            if n["kind"] != "file":
                n["stats"] = {"files": files, "lines": lines, "endpoints": eps, "children": len(children.get(nid, []))}
            n["hash"] = hashlib.sha1("".join(sorted(shas)).encode()).hexdigest()[:12] if shas else hashlib.sha1(nid.encode()).hexdigest()[:12]
            n["_langs"] = langs
            return files, lines, eps, shas, langs

        for nid in [x for x in nodes if nodes[x]["parent"] is None]:
            agg(nid)

        talks = defaultdict(set)
        for e in self.edges.values():
            ts, tt = tops[e["source"]], tops[e["target"]]
            if ts == tt:
                continue
            cur = e["source"]
            while cur:
                talks[cur].add(nodes[tt]["name"])
                cur = nodes[cur]["parent"]

        lang_names = {"typescript": "TypeScript", "javascript": "JavaScript", "python": "Python", "csharp": "C#", "sql": "SQL", "prisma": "Prisma"}
        for n in nodes.values():
            langs = n.pop("_langs", Counter())
            lang_txt = ", ".join(lang_names.get(l, str(l)) for l, _ in langs.most_common(3) if l)
            st = n.get("stats", {})
            k = n["kind"]
            t = sorted(talks.get(n["id"], set()))
            talk_txt = f" Talks to: {', '.join(t[:8])}{'…' if len(t) > 8 else ''}." if t else ""
            if n["description"]:
                continue
            if k == "file":
                syms = ", ".join(s["name"] for s in n.get("symbols", [])[:6])
                base = n.get("doc") or f"{lang_names.get(n.get('lang'), '')} file, {n.get('lines', 0)} lines."
                n["description"] = base + (f" Defines {syms}." if syms and not n.get("doc") else "")
            elif k == "module":
                eps = f" {st['endpoints']} endpoints/pages." if st.get("endpoints") else ""
                n["description"] = f"Folder `{n.get('path')}` with {st.get('files', 0)} files ({lang_txt}).{eps}{talk_txt}"
            elif n["id"].startswith("unit:"):
                eps = self._endpoint_summary(n["id"])
                comp = f" Runs as docker-compose service `{'`, `'.join(n['compose'])}`" if n.get("compose") else ""
                ports = f" on port {', '.join(map(str, n['ports']))}" if n.get("ports") and comp else ""
                n["description"] = (f"{n.get('framework') or 'Code'} {KIND_LABEL.get(k, k)} in `{n.get('path')}/` with "
                                    f"{st.get('files', 0)} source files, {st.get('lines', 0):,} lines ({lang_txt}).{eps}{comp}{ports}{'.' if comp else ''}{talk_txt}")
            elif k in KIND_LABEL:
                via = self.res_via.get(n["id"], [])
                n["description"] = f"{n['name']}: {KIND_LABEL[k]}." + (f" Detected from {'; '.join(via[:4])}." if via else "") + talk_txt
            if self.res_via.get(n["id"]):
                n["detected_via"] = self.res_via[n["id"]]


    def _endpoint_summary(self, nid: str) -> str:
        api = pages = 0
        for f in self._descendant_files(nid):
            for ep in f.get("endpoints", []):
                if ep["method"] == "PAGE":
                    pages += 1
                else:
                    api += 1
        parts = []
        if api:
            parts.append(f"{api} API endpoints")
        if pages:
            parts.append(f"{pages} pages")
        return f" Serves {' and '.join(parts)}." if parts else ""

    def _output(self) -> dict:
        nodes = list(self.nodes.values())
        stacks = sorted({t for n in nodes if n["id"].startswith("unit:") for t in n.get("tech", [])[:1]})
        return {
            "version": SCHEMA_VERSION,
            "generator": f"wirehouse {__version__}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project": {
                "name": self.scan.root.name,
                "root": str(self.scan.root),
                "stacks": stacks,
                "files": len(self.scan.sources),
            },
            "repo": repo_info(self.scan.root),
            "layers": LAYERS,
            "edge_kinds": EDGE_KINDS,
            "nodes": nodes,
            "edges": list(self.edges.values()),
            "link_notes": {},
        }


def build_archmap(root: Path, log=print) -> dict:
    t0 = time.time()
    res = scan(root)
    log(f"  scanned {len(res.sources)} source files in {time.time() - t0:.1f}s"
        + (f" (skipped {res.skipped_large} over {MAX_FILE_BYTES // 1000} KB)" if res.skipped_large else ""))
    facts = {sf.rel: analyze(sf) for sf in res.sources}
    units = detect_units(res)
    infra = detect_infra(res)
    log(f"  found {len(units)} code units, {len(infra.compose)} compose services, {len(infra.env)} env entries")
    data, _ = scrub(Builder(res, facts, units, infra).run())
    tops = [n for n in data["nodes"] if n["parent"] is None]
    log(f"  built {len(data['nodes'])} nodes ({len(tops)} top-level blocks) and {len(data['edges'])} edges in {time.time() - t0:.1f}s")
    return data
