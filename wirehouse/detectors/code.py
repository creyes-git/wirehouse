"""Per-file facts: imports, env vars, URLs, symbols, docs, endpoints and tables.

Everything here is regex based on purpose: it is fast, dependency free and
good enough for architecture-level maps. Precision matters more than recall;
the agent's enrichment pass fills the gaps.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from wirehouse.detectors import schema
from wirehouse.scan import SourceFile
from wirehouse.signatures import SIGNATURES


@dataclass
class FileFacts:
    rel: str
    imports: list[tuple[str, int]] = field(default_factory=list)          # raw specifier/module, line
    py_from_names: dict[str, list[str]] = field(default_factory=dict)     # "from X import a, b" -> X: [a, b]
    env: list[tuple[str, int]] = field(default_factory=list)              # explicit env var reads
    upper_literals: list[tuple[str, int]] = field(default_factory=list)   # 'SOME_NAME' string literals
    urls: list[tuple[str, int, str]] = field(default_factory=list)        # host, line, full url
    service_urls: list[tuple[str, int, int]] = field(default_factory=list)  # bare host (api, localhost), port, line
    code_hits: list[tuple[str, int]] = field(default_factory=list)        # signature id, line
    symbols: list[dict] = field(default_factory=list)
    doc: str = ""
    endpoints: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)


class _Lines:
    def __init__(self, text: str):
        self.starts = [0]
        for m in re.finditer("\n", text):
            self.starts.append(m.end())

    def line(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


# ── imports ──────────────────────────────────────────────────────────────────
PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+(?:[ \t]*,[ \t]*[\w.]+)*)", re.M)
PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]+)", re.M)
JS_FROM = re.compile(r"\b(?:import|export)\s[^'\";]*?\bfrom\s*['\"]([^'\"]+)['\"]")
JS_SIDE = re.compile(r"\bimport\s*['\"]([^'\"]+)['\"]")
JS_REQ = re.compile(r"\b(?:require|import)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
CS_USING = re.compile(r"^[ \t]*(?:global[ \t]+)?using[ \t]+(?:static[ \t]+)?([\w.]+)[ \t]*;", re.M)

# ── env vars ─────────────────────────────────────────────────────────────────
ENV_PATTERNS = {
    "js": [
        re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"process\.env\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]"),
        re.compile(r"import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"Deno\.env\.get\(\s*['\"]([A-Za-z0-9_]+)"),
    ],
    "python": [
        re.compile(r"os\.environ\[\s*['\"]([A-Za-z0-9_]+)['\"]"),
        re.compile(r"(?:os\.)?environ\.get\(\s*['\"]([A-Za-z0-9_]+)['\"]"),
        re.compile(r"getenv\(\s*['\"]([A-Za-z0-9_]+)['\"]"),
        re.compile(r"\benv(?:\.str|\.int|\.bool|\.url)?\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    ],
    "csharp": [
        re.compile(r"GetEnvironmentVariable\(\s*\"([A-Za-z0-9_]+)\""),
        re.compile(r"Configuration\[\s*\"([A-Za-z0-9_:]+)\"\s*\]"),
        re.compile(r"GetConnectionString\(\s*\"([A-Za-z0-9_]+)\"\s*\)"),
        re.compile(r"GetValue<[^>]+>\(\s*\"([A-Za-z0-9_:]+)\""),
    ],
}
UPPER_LITERAL = re.compile(r"['\"]([A-Z][A-Z0-9]*_[A-Z0-9_]+)['\"]")

URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?([^\s'\"`)<>]*)")
SERVICE_URL_RE = re.compile(r"(?:https?|grpc|ws)://([A-Za-z0-9_-]+|\d+\.\d+\.\d+\.\d+)(?::(\d+))")

NOISE_HOSTS = (
    "example.com", "example.org", "example.net", "localhost", "w3.org", "www.w3.org", "schema.org", "json-schema.org",
    "github.com", "raw.githubusercontent.com", "gist.github.com", "stackoverflow.com", "developer.mozilla.org",
    "nextjs.org", "react.dev", "reactjs.org", "vercel.com", "nodejs.org", "npmjs.com", "www.npmjs.com", "python.org",
    "docs.python.org", "pypi.org", "learn.microsoft.com", "docs.microsoft.com", "aka.ms", "go.microsoft.com",
    "fonts.googleapis.com", "fonts.gstatic.com", "tailwindcss.com", "shadcn.com", "ui.shadcn.com", "opensource.org",
    "creativecommons.org", "wikipedia.org", "en.wikipedia.org", "twitter.com", "x.com", "linkedin.com", "youtube.com",
    "fastapi.tiangolo.com", "docs.pydantic.dev", "sqlalchemy.org", "docs.sqlalchemy.org", "mozilla.org", "apache.org",
    "eslint.org", "prettier.io", "typescriptlang.org", "jestjs.io", "vitest.dev", "playwright.dev", "test", "invalid",
)

# ── symbols / docs ───────────────────────────────────────────────────────────
PY_SYMBOL = re.compile(r"^(?:async[ \t]+)?(def|class)[ \t]+(\w+)", re.M)
JS_SYMBOL = re.compile(
    r"^export[ \t]+(?:default[ \t]+)?(?:declare[ \t]+)?(?:async[ \t]+)?"
    r"(function\*?|class|const|let|var|interface|type|enum|abstract[ \t]+class)[ \t]+(\w+)", re.M)
CS_SYMBOL = re.compile(
    r"^[ \t]*(?:\[[^\]]*\][ \t]*)*(?:public|internal)[ \t]+(?:(?:static|sealed|abstract|partial|readonly)[ \t]+)*"
    r"(class|interface|record|struct|enum)[ \t]+(\w+)", re.M)

# ── endpoints ────────────────────────────────────────────────────────────────
PY_ROUTE = re.compile(
    r"@(\w+)\.(get|post|put|patch|delete|options|head|api_route|route|websocket)\(\s*(?:path\s*=\s*)?['\"]([^'\"]*)['\"]([^\n]*)")
PY_ROUTER_PREFIX = re.compile(r"(\w+)\s*=\s*(?:APIRouter|Blueprint)\(([^)]*)\)")
DJANGO_PATH = re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]")
JS_ROUTE = re.compile(r"\b(\w+)\.(get|post|put|patch|delete|all)\(\s*['\"`](/[^'\"`]*)['\"`]")
NEXT_METHOD = re.compile(r"^export[ \t]+(?:async[ \t]+)?(?:function[ \t]+|const[ \t]+)(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", re.M)
NEST_CONTROLLER = re.compile(r"@Controller\(\s*(?:['\"]([^'\"]*)['\"])?")
NEST_ROUTE = re.compile(r"@(Get|Post|Put|Patch|Delete|All)\(\s*(?:['\"]([^'\"]*)['\"])?\s*\)")
CS_CLASS_ROUTE = re.compile(r"\[Route\(\s*\"([^\"]*)\"\s*\)\][\s\S]{0,400}?class[ \t]+(\w+)")
CS_HTTP = re.compile(r"\[Http(Get|Post|Put|Patch|Delete)(?:\(\s*\"([^\"]*)\"[^\]]*\))?\]")
CS_MINIMAL = re.compile(r"\.Map(Get|Post|Put|Patch|Delete|Methods)\(\s*\"([^\"]*)\"")

# ── tables ───────────────────────────────────────────────────────────────────
SQLA_TABLE = re.compile(r"__tablename__\s*=\s*['\"](\w+)['\"]")
SQLMODEL_TABLE = re.compile(r"^class[ \t]+(\w+)\([^)]*\btable\s*=\s*True[^)]*\)\s*:", re.M)
DJANGO_MODEL = re.compile(r"^class[ \t]+(\w+)\((?:models\.)?Model\)", re.M)
PRISMA_MODEL = re.compile(r"^model[ \t]+(\w+)[ \t]*\{", re.M)
DRIZZLE_TABLE = re.compile(r"\b(?:pgTable|mysqlTable|sqliteTable)\(\s*['\"](\w+)['\"]")
TYPEORM_ENTITY = re.compile(r"@Entity\(\s*(?:['\"](\w+)['\"])?[^)]*\)\s*(?:export\s+)?class\s+(\w+)")
MONGOOSE_MODEL = re.compile(r"\bmodel(?:<[^>]*>)?\(\s*['\"](\w+)['\"]")
SQL_TABLE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?(TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]]+)",
    re.I)
EF_DBSET = re.compile(r"DbSet<(\w+)>\s+(\w+)")

_CODE_SIGS = [s for s in SIGNATURES if s._code_re]


def _first_paragraph(text: str, limit: int = 320) -> str:
    text = text.strip()
    para = re.split(r"\n\s*\n", text, maxsplit=1)[0]
    para = re.sub(r"\s+", " ", para).strip()
    return para[: limit - 1] + "…" if len(para) > limit else para


def _python_doc(text: str) -> str:
    m = re.match(r'\s*(?:#[^\n]*\n\s*)*(?:[rubRUB]{0,2})("""|\'\'\')(.*?)\1', text, re.S)
    return _first_paragraph(m.group(2)) if m else ""


def _js_doc(text: str) -> str:
    body = re.sub(r"^\s*(['\"]use (?:client|server|strict)['\"];?\s*)+", "", text)
    m = re.match(r"\s*/\*\*?(.*?)\*/", body, re.S)
    if m:
        inner = re.sub(r"^\s*\*[ \t]?", "", m.group(1), flags=re.M)
        if not re.search(r"eslint|@ts-|copyright|license", inner, re.I):
            return _first_paragraph(inner)
    lines = []
    for raw in body.lstrip().splitlines():
        s = raw.strip()
        if not s.startswith("//"):
            break
        s = s.lstrip("/").strip()
        if re.search(r"eslint|@ts-|prettier-ignore", s):
            continue
        lines.append(s)
    return _first_paragraph("\n".join(lines)) if lines else ""


def _cs_doc(text: str) -> str:
    m = re.search(r"((?:[ \t]*///[^\n]*\n)+)[ \t]*(?:\[[^\n]*\n[ \t]*)*(?:public|internal)", text)
    if not m:
        return ""
    inner = re.sub(r"^[ \t]*///[ \t]?", "", m.group(1), flags=re.M)
    inner = re.sub(r"<[^>]+>", "", inner)
    return _first_paragraph(inner)


def _next_route(rel: str) -> tuple[str, str] | None:
    """Map a Next.js app/pages router file to (kind, url path)."""
    parts = rel.split("/")
    for anchor in ("app", "pages"):
        if anchor in parts[:-1]:
            i = parts.index(anchor)  # first one: works for repo-root, src/ and monorepo apps (web/app/...)
            segs = parts[i + 1:]
            if not segs:
                return None
            fname = segs[-1]
            stem = fname.rsplit(".", 1)[0]
            dirs = [s for s in segs[:-1] if not (s.startswith("(") and s.endswith(")")) and not s.startswith("@") and not s.startswith("_")]
            if anchor == "app":
                if stem == "route":
                    return "api", "/" + "/".join(dirs)
                if stem == "page":
                    return "page", "/" + "/".join(dirs)
                return None
            if stem.startswith("_"):
                return None
            path = "/" + "/".join(dirs + ([] if stem == "index" else [stem]))
            return ("api" if dirs[:1] == ["api"] else "page"), path
    return None


def analyze(sf: SourceFile) -> FileFacts:
    f = FileFacts(rel=sf.rel)
    text = sf.text
    L = _Lines(text)
    lang = sf.lang

    if lang == "python":
        for m in PY_IMPORT.finditer(text):
            for mod in m.group(1).split(","):
                f.imports.append((mod.strip(), L.line(m.start())))
        for m in PY_FROM.finditer(text):
            mod = m.group(1)
            names = [n.strip().split(" as ")[0].strip() for n in m.group(2).strip("() \t").replace("\n", ",").split(",")]
            names = [n for n in names if n and n != "*" and not n.startswith("#")]
            f.imports.append((mod, L.line(m.start())))
            f.py_from_names.setdefault(mod, []).extend(names)
        f.doc = _python_doc(text)
        for m in PY_SYMBOL.finditer(text):
            if not m.group(2).startswith("_"):
                f.symbols.append({"name": m.group(2), "kind": m.group(1), "line": L.line(m.start())})
        env_key = "python"
    elif lang in ("typescript", "javascript"):
        seen = set()
        for rx in (JS_FROM, JS_SIDE, JS_REQ):
            for m in rx.finditer(text):
                spec = m.group(1)
                if (spec, m.start()) not in seen:
                    seen.add((spec, m.start()))
                    f.imports.append((spec, L.line(m.start())))
        f.doc = _js_doc(text)
        for m in JS_SYMBOL.finditer(text):
            kind = m.group(1).replace("abstract ", "").strip()
            f.symbols.append({"name": m.group(2), "kind": kind, "line": L.line(m.start())})
        env_key = "js"
    elif lang == "csharp":
        for m in CS_USING.finditer(text):
            f.imports.append((m.group(1), L.line(m.start())))
        f.doc = _cs_doc(text)
        for m in CS_SYMBOL.finditer(text):
            f.symbols.append({"name": m.group(2), "kind": m.group(1), "line": L.line(m.start())})
        env_key = "csharp"
    else:
        env_key = None

    if env_key:
        for rx in ENV_PATTERNS[env_key]:
            for m in rx.finditer(text):
                f.env.append((m.group(1), L.line(m.start())))
        for m in UPPER_LITERAL.finditer(text):
            f.upper_literals.append((m.group(1), L.line(m.start())))
        for m in URL_RE.finditer(text):
            host = m.group(1).lower().rstrip(".")
            f.urls.append((host, L.line(m.start()), m.group(0)))
        for m in SERVICE_URL_RE.finditer(text):
            f.service_urls.append((m.group(1).lower(), int(m.group(2)), L.line(m.start())))
        for sig in _CODE_SIGS:
            for rx in sig._code_re:
                m = rx.search(text)
                if m:
                    f.code_hits.append((sig.id, L.line(m.start())))
                    break

    if not sf.is_test:
        _endpoints(sf, f, L)
        _tables(sf, f, L)
    f.symbols = f.symbols[:40]
    return f


def _endpoints(sf: SourceFile, f: FileFacts, L: _Lines) -> None:
    text, rel = sf.text, sf.rel
    if sf.lang == "python":
        prefixes = {}
        for m in PY_ROUTER_PREFIX.finditer(text):
            pm = re.search(r"(?:url_)?prefix\s*=\s*['\"]([^'\"]*)['\"]", m.group(2))
            prefixes[m.group(1)] = pm.group(1) if pm else ""
        for m in PY_ROUTE.finditer(text):
            obj, verb, path, rest = m.groups()
            if verb in ("route", "api_route"):
                mm = re.search(r"methods\s*=\s*\[([^\]]*)\]", rest)
                verbs = re.findall(r"['\"](\w+)['\"]", mm.group(1)) if mm else ["GET"]
                method = "/".join(v.upper() for v in verbs)
            elif verb == "websocket":
                method = "WS"
            else:
                method = verb.upper()
            full = (prefixes.get(obj, "") + path) or "/"
            f.endpoints.append({"method": method, "path": full, "line": L.line(m.start())})
        if rel.endswith("urls.py"):
            for m in DJANGO_PATH.finditer(text):
                f.endpoints.append({"method": "ANY", "path": "/" + m.group(1).lstrip("^/"), "line": L.line(m.start())})
    elif sf.lang in ("typescript", "javascript"):
        nr = _next_route(rel)
        if nr:
            kind, path = nr
            if kind == "api":
                methods = NEXT_METHOD.findall(text) or ["ANY"]
                for meth in methods:
                    mm = re.search(rf"^export[ \t]+(?:async[ \t]+)?(?:function[ \t]+|const[ \t]+){meth}\b", text, re.M)
                    f.endpoints.append({"method": meth, "path": path, "line": L.line(mm.start()) if mm else 1})
            else:
                f.endpoints.append({"method": "PAGE", "path": path, "line": 1})
        for m in JS_ROUTE.finditer(text):
            obj = m.group(1)
            if obj in ("app", "router", "server", "api", "routes", "r") or obj.endswith(("Router", "router", "App", "app")):
                f.endpoints.append({"method": m.group(2).upper(), "path": m.group(3), "line": L.line(m.start())})
        cm = NEST_CONTROLLER.search(text)
        if cm:
            base = "/" + (cm.group(1) or "").strip("/")
            for m in NEST_ROUTE.finditer(text):
                sub = (m.group(2) or "").strip("/")
                f.endpoints.append({"method": m.group(1).upper(), "path": (base.rstrip("/") + "/" + sub).rstrip("/") or "/",
                                    "line": L.line(m.start())})
    elif sf.lang == "csharp":
        cm = CS_CLASS_ROUTE.search(text)
        base = ""
        if cm:
            ctrl = re.sub(r"Controller$", "", cm.group(2)).lower()
            base = "/" + cm.group(1).replace("[controller]", ctrl).strip("/")
        for m in CS_HTTP.finditer(text):
            sub = (m.group(2) or "").strip("/")
            if sub.startswith("~/"):
                path = sub[1:]
            else:
                path = (base.rstrip("/") + "/" + sub).rstrip("/") or "/"
            f.endpoints.append({"method": m.group(1).upper(), "path": path, "line": L.line(m.start())})
        for m in CS_MINIMAL.finditer(text):
            f.endpoints.append({"method": m.group(1).upper().replace("METHODS", "ANY"), "path": m.group(2) or "/",
                                "line": L.line(m.start())})


def _tables(sf: SourceFile, f: FileFacts, L: _Lines) -> None:
    text = sf.text
    found: dict[str, dict] = {}

    def add(name: str, line: int, how: str, kind: str = "table"):
        name = name.strip('"`[]')
        if "." in name:
            name = name.split(".")[-1].strip('"`[]')
        if not name or name.lower() in found or name.upper() in ("IF", "AS", "SELECT", "TABLE"):
            return
        found[name.lower()] = {"name": name, "line": line, "via": how, "kind": kind}

    if sf.lang == "python":
        for m in SQLA_TABLE.finditer(text):
            add(m.group(1), L.line(m.start()), "SQLAlchemy model")
        if "sqlmodel" in text.lower():
            for m in SQLMODEL_TABLE.finditer(text):
                body = text[m.end():m.end() + 2000]
                if not re.search(r"^\s+__tablename__", body.split("\nclass ", 1)[0], re.M):
                    add(m.group(1).lower(), L.line(m.start()), "SQLModel model")
        if "models" in sf.rel:
            for m in DJANGO_MODEL.finditer(text):
                add(m.group(1), L.line(m.start()), "Django model")
    if sf.lang == "prisma":
        for m in PRISMA_MODEL.finditer(text):
            add(m.group(1), L.line(m.start()), "Prisma model")
    if sf.lang in ("typescript", "javascript"):
        for m in DRIZZLE_TABLE.finditer(text):
            add(m.group(1), L.line(m.start()), "Drizzle table")
        for m in TYPEORM_ENTITY.finditer(text):
            add(m.group(1) or m.group(2), L.line(m.start()), "TypeORM entity")
        if "mongoose" in text:
            for m in MONGOOSE_MODEL.finditer(text):
                add(m.group(1), L.line(m.start()), "Mongoose model")
    if sf.lang == "csharp":
        for m in EF_DBSET.finditer(text):
            add(m.group(2), L.line(m.start()), f"EF Core DbSet<{m.group(1)}>")
    for m in SQL_TABLE.finditer(text):
        add(m.group(2), L.line(m.start()), "SQL DDL", "view" if m.group(1).upper() == "VIEW" else "table")
    f.tables = list(found.values())[:80]
    schema.attach(sf.lang, text, f.tables, L.starts)
