"""Find the "units" of a project: apps, services, workers and libraries.

A unit is a manifest directory plus a language family (js / python / dotnet).
Each source file belongs to the deepest unit of its family whose directory
contains it. Units become the big top-level blocks in the warehouse.
"""

from __future__ import annotations

import configparser
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from wirehouse.scan import ScanResult, SourceFile, as_dict, as_list, lang_family


@dataclass
class Dep:
    name: str
    manifest: str
    line: int | None = None
    dev: bool = False


@dataclass
class Unit:
    dir: str
    family: str
    manifests: list[str] = field(default_factory=list)
    pkg_name: str = ""
    deps: dict[str, Dep] = field(default_factory=dict)
    project_refs: list[str] = field(default_factory=list)  # .NET ProjectReference dirs
    sdk: str = ""
    props: dict[str, str] = field(default_factory=dict)
    files: list[SourceFile] = field(default_factory=list)
    kind: str = "library"
    framework: str = ""
    tech: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    compose_services: list[str] = field(default_factory=list)
    implicit: bool = False
    name: str = ""

    @property
    def id(self) -> str:
        return f"unit:{self.family}:{self.dir or '.'}"


def _line_of(text: str, needle: str) -> int | None:
    i = text.find(needle)
    return text.count("\n", 0, i) + 1 if i >= 0 else None


def _parent_dir(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def _parse_package_json(scan: ScanResult, rel: str, u: Unit) -> None:
    text = scan.read(rel)
    try:
        data = as_dict(json.loads(text))
    except ValueError:
        return
    u.pkg_name = u.pkg_name or str(data.get("name") or "")
    for section, dev in (("dependencies", False), ("devDependencies", True), ("peerDependencies", False), ("optionalDependencies", False)):
        for name in as_dict(data.get(section)):
            if name not in u.deps or (u.deps[name].dev and not dev):
                u.deps[name] = Dep(name, rel, _line_of(text, f'"{name}"'), dev)
    if data.get("bin"):
        u.props["bin"] = "1"
    if data.get("workspaces"):
        u.props["workspaces"] = "1"
    scripts = as_dict(data.get("scripts"))
    for key in ("start", "dev", "serve"):
        m = re.search(r"(?:--port|-p|PORT=)\s*(\d{2,5})", str(scripts.get(key, "")))
        if m:
            u.ports.append(int(m.group(1)))


_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _parse_python_manifest(scan: ScanResult, rel: str, u: Unit) -> None:
    text = scan.read(rel)
    low = rel.lower()
    if low.endswith(".txt"):
        dev = "dev" in low.rsplit("/", 1)[-1] or "test" in low.rsplit("/", 1)[-1]
        for i, raw in enumerate(text.splitlines(), 1):
            s = raw.strip()
            if not s or s.startswith(("#", "-")):
                continue
            m = _REQ_LINE.match(s)
            if m and m.group(1).lower() not in u.deps:
                u.deps[m.group(1).lower()] = Dep(m.group(1), rel, i, dev)
        return
    if low.endswith("pyproject.toml") or low.endswith("pipfile"):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return
        names: list[tuple[str, bool]] = []
        proj = as_dict(data.get("project"))
        u.pkg_name = u.pkg_name or str(proj.get("name") or "")
        names += [(d, False) for d in as_list(proj.get("dependencies"))]
        for group in as_dict(proj.get("optional-dependencies")).values():
            names += [(d, True) for d in as_list(group)]
        poetry = as_dict(as_dict(data.get("tool")).get("poetry"))
        u.pkg_name = u.pkg_name or str(poetry.get("name") or "")
        names += [(d, False) for d in as_dict(poetry.get("dependencies")) if d.lower() != "python"]
        names += [(d, False) for d in as_dict(data.get("packages"))]  # Pipfile
        names += [(d, True) for d in as_dict(data.get("dev-packages"))]
        for spec, dev in names:
            m = _REQ_LINE.match(spec) if isinstance(spec, str) else None
            if m and m.group(1).lower() not in u.deps:
                u.deps[m.group(1).lower()] = Dep(m.group(1), rel, _line_of(text, m.group(1)), dev)
        return
    if low.endswith("setup.cfg"):
        cfg = configparser.ConfigParser(interpolation=None)
        try:
            cfg.read_string(text)
        except configparser.Error:
            return
        for spec in cfg.get("options", "install_requires", fallback="").splitlines():
            m = _REQ_LINE.match(spec)
            if m and m.group(1).lower() not in u.deps:
                u.deps[m.group(1).lower()] = Dep(m.group(1), rel, _line_of(text, m.group(1)))
        return
    if low.endswith("setup.py"):
        # only the strings inside install_requires=[...], not version="1.0" further down
        block = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
        for m in re.finditer(r"['\"]([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:[<>=~!;\[][^'\"]*)?['\"]", block.group(1) if block else ""):
            if m.group(1).lower() not in u.deps:
                u.deps[m.group(1).lower()] = Dep(m.group(1), rel, _line_of(text, m.group(0)))


def _parse_csproj(scan: ScanResult, rel: str, u: Unit) -> None:
    text = scan.read(rel)
    try:
        root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", text, count=1))
    except ET.ParseError:
        return
    u.sdk = root.get("Sdk", "") or u.sdk
    u.pkg_name = u.pkg_name or rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for el in root.iter():
        tag = el.tag
        if tag == "PackageReference" and el.get("Include"):
            name = el.get("Include")
            u.deps[name.lower()] = Dep(name, rel, _line_of(text, name))
        elif tag == "ProjectReference" and el.get("Include"):
            ref = el.get("Include").replace("\\", "/")
            base = _parent_dir(rel)
            parts = (base.split("/") if base else []) + ref.split("/")
            out: list[str] = []
            for p in parts:
                if p == "..":
                    out and out.pop()
                elif p and p != ".":
                    out.append(p)
            u.project_refs.append(_parent_dir("/".join(out)))
        elif tag in ("OutputType", "UseWPF", "UseWindowsForms", "UseMaui", "IsTestProject", "AssemblyName", "AzureFunctionsVersion"):
            if el.text:
                u.props[tag] = el.text.strip()


JS_FRAMEWORKS = [
    # (dependency, kind, framework label)
    ("expo", "mobile", "Expo"), ("react-native", "mobile", "React Native"),
    ("electron", "desktop", "Electron"), ("@tauri-apps/api", "desktop", "Tauri"),
    # email templates rendered by a backend, not an app people open
    ("react-email", "library", "React Email"), ("@react-email/components", "library", "React Email"), ("mjml", "library", "MJML emails"),
    ("next", "frontend", "Next.js"), ("nuxt", "frontend", "Nuxt"), ("@sveltejs/kit", "frontend", "SvelteKit"),
    ("@remix-run/react", "frontend", "Remix"), ("@react-router/dev", "frontend", "React Router"), ("astro", "frontend", "Astro"),
    ("gatsby", "frontend", "Gatsby"), ("@angular/core", "frontend", "Angular"),
    ("@nestjs/core", "service", "NestJS"), ("express", "service", "Express"), ("fastify", "service", "Fastify"),
    ("koa", "service", "Koa"), ("hono", "service", "Hono"), ("@hapi/hapi", "service", "hapi"),
    ("@apollo/server", "service", "Apollo GraphQL"), ("apollo-server", "service", "Apollo GraphQL"), ("graphql-yoga", "service", "GraphQL Yoga"),
    ("firebase-functions", "function", "Firebase Functions"), ("@azure/functions", "function", "Azure Functions"),
    ("vue", "frontend", "Vue"), ("svelte", "frontend", "Svelte"), ("solid-js", "frontend", "Solid"),
    ("react-dom", "frontend", "React"), ("bullmq", "worker", "BullMQ worker"),
]
PY_FRAMEWORKS = [
    ("fastapi", "service", "FastAPI"), ("django", "service", "Django"), ("flask", "service", "Flask"),
    ("litestar", "service", "Litestar"), ("starlette", "service", "Starlette"), ("sanic", "service", "Sanic"),
    ("aiohttp", "service", "aiohttp"), ("tornado", "service", "Tornado"), ("quart", "service", "Quart"), ("falcon", "service", "Falcon"),
    ("streamlit", "frontend", "Streamlit"), ("gradio", "frontend", "Gradio"), ("dash", "frontend", "Dash"),
    ("azure-functions", "function", "Azure Functions"),
    ("celery", "worker", "Celery worker"), ("dramatiq", "worker", "Dramatiq worker"), ("rq", "worker", "RQ worker"),
    ("arq", "worker", "arq worker"), ("apscheduler", "worker", "APScheduler"), ("prefect", "worker", "Prefect flows"),
    ("dagster", "worker", "Dagster"), ("apache-airflow", "worker", "Airflow"),
]
DEFAULT_PORTS = {"Next.js": 3000, "Nuxt": 3000, "Remix": 3000, "SvelteKit": 5173, "Vue": 5173, "React": 5173, "Astro": 4321,
                 "FastAPI": 8000, "Django": 8000, "Flask": 5000, "Express": 3000, "NestJS": 3000, "Streamlit": 8501}


def _classify(u: Unit) -> None:
    deps = {k.lower(): v for k, v in u.deps.items() if not v.dev}
    all_deps = {k.lower() for k in u.deps}
    if u.family == "js":
        for dep, kind, label in JS_FRAMEWORKS:
            if dep in deps or (dep == "next" and dep in all_deps):
                u.kind, u.framework = kind, label
                break
        else:
            u.kind = "worker" if u.props.get("bin") else "library"
            u.framework = "Node CLI" if u.props.get("bin") else ""
        if any(f.lang == "typescript" for f in u.files):
            u.tech.append("TypeScript")
        else:
            u.tech.append("JavaScript")
    elif u.family == "python":
        for dep, kind, label in PY_FRAMEWORKS:
            if dep in deps or dep in all_deps:
                u.kind, u.framework = kind, label
                break
        else:
            imports_fw = None
            for f in u.files:
                m = re.search(r"^(?:from|import)\s+(fastapi|flask|django|celery|streamlit)\b", f.text, re.M)
                if m:
                    imports_fw = m.group(1)
                    break
            fw = {"fastapi": ("service", "FastAPI"), "flask": ("service", "Flask"), "django": ("service", "Django"),
                  "celery": ("worker", "Celery worker"), "streamlit": ("frontend", "Streamlit")}
            if imports_fw:
                u.kind, u.framework = fw[imports_fw]
            elif any(f.rel.rsplit("/", 1)[-1] in ("__main__.py", "cli.py", "main.py") or "if __name__ ==" in f.text for f in u.files if not f.is_test):
                u.kind, u.framework = "worker", "Python job / CLI"
            else:
                u.kind, u.framework = "library", "Python package"
        if u.files and not any(f.lang == "python" for f in u.files):
            # a folder of only SQL or Prisma files lands in the fallback family, but it is not Python
            u.kind, u.framework = "library", "Database schema"
            u.tech.append("Prisma" if all(f.lang == "prisma" for f in u.files) else "SQL")
        else:
            u.tech.append("Python")
    elif u.family == "dotnet":
        sdk = u.sdk.lower()
        out = u.props.get("OutputType", "").lower()
        if u.props.get("IsTestProject", "").lower() == "true" or any(d in all_deps for d in ("xunit", "nunit", "mstest.testframework", "microsoft.net.test.sdk")):
            u.kind, u.framework = "tests", "Test project"
        elif "blazorwebassembly" in sdk:
            u.kind, u.framework = "frontend", "Blazor WebAssembly"
        elif sdk.endswith(".web") or "microsoft.net.sdk.web" in sdk:
            u.kind, u.framework = "service", "ASP.NET Core"
        elif "worker" in sdk:
            u.kind, u.framework = "worker", ".NET Worker Service"
        elif "functions" in sdk or u.props.get("AzureFunctionsVersion") or "microsoft.azure.functions.worker" in all_deps:
            u.kind, u.framework = "function", "Azure Functions"
        elif u.props.get("UseMaui", "").lower() == "true":
            u.kind, u.framework = "mobile", ".NET MAUI"
        elif u.props.get("UseWPF", "").lower() == "true" or u.props.get("UseWindowsForms", "").lower() == "true":
            u.kind, u.framework = "desktop", "WPF" if u.props.get("UseWPF") else "WinForms"
        elif out in ("exe", "winexe"):
            u.kind, u.framework = "worker", ".NET console app"
        else:
            u.kind, u.framework = "library", ".NET class library"
        u.tech.append("C#")
    if u.framework and u.framework not in u.tech:
        u.tech.insert(0, u.framework)
    for f in u.files:
        m = re.search(r"(?:uvicorn\.run|app\.run|\.listen)\([^)]*?(?:port\s*=\s*)?(\d{4,5})", f.text)
        if m:
            u.ports.append(int(m.group(1)))
            break
    if not u.ports and u.framework in DEFAULT_PORTS:
        u.props["default_port"] = str(DEFAULT_PORTS[u.framework])


def detect_units(scan: ScanResult) -> list[Unit]:
    units: dict[tuple[str, str], Unit] = {}

    def get(d: str, fam: str) -> Unit:
        key = (d, fam)
        if key not in units:
            units[key] = Unit(dir=d, family=fam)
        return units[key]

    for rel in scan.configs.get("package_json", []):
        u = get(_parent_dir(rel), "js")
        u.manifests.append(rel)
        _parse_package_json(scan, rel, u)
    for rel in scan.configs.get("python_manifest", []):
        u = get(_parent_dir(rel), "python")
        u.manifests.append(rel)
        _parse_python_manifest(scan, rel, u)
    for rel in scan.configs.get("csproj", []):
        u = get(_parent_dir(rel), "dotnet")
        u.manifests.append(rel)
        _parse_csproj(scan, rel, u)

    # Assign files to the deepest unit of the same family; collect orphans.
    by_family: dict[str, list[Unit]] = {}
    for u in units.values():
        by_family.setdefault(u.family, []).append(u)
    for lst in by_family.values():
        lst.sort(key=lambda x: -len(x.dir))

    def owner(rel: str, fam: str | None) -> Unit | None:
        cands = by_family.get(fam, []) if fam else sorted(units.values(), key=lambda x: -len(x.dir))
        for u in cands:
            if not u.dir or rel.startswith(u.dir + "/"):
                return u
        return None

    orphans: list[SourceFile] = []
    for sf in scan.sources:
        u = owner(sf.rel, lang_family(sf.lang))
        if u is None and lang_family(sf.lang) is None:
            u = owner(sf.rel, None)
        if u is None:
            orphans.append(sf)
        else:
            u.files.append(sf)

    # Files with no manifest: one implicit unit per top-level folder and family.
    for sf in orphans:
        fam = lang_family(sf.lang) or "python"
        top = sf.rel.split("/", 1)[0] if "/" in sf.rel else ""
        u = get(top, fam)
        u.implicit = u.implicit or not u.manifests
        u.files.append(sf)

    out = []
    for u in units.values():
        real = [f for f in u.files if not f.is_test and not re.search(r"\.config\.\w+$|^next-env|setup\.py$|conftest\.py$", f.rel.rsplit("/", 1)[-1])]
        if not real and u.family != "dotnet":
            continue
        if u.family == "dotnet" and not u.files:
            continue
        _classify(u)
        out.append(u)
    out.sort(key=lambda x: (x.dir, x.family))
    return out
