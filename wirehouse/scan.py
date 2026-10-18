"""Walk a project and collect the files Wirehouse cares about.

Two buckets come out of a scan:
- source files (code that becomes file nodes inside rooms)
- config files (manifests, compose, Dockerfiles, Terraform, workflows, .env templates)

Real `.env` files are never read: only templates such as `.env.example`.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

IGNORE_DIRS = {
    "node_modules", ".git", ".hg", ".svn", ".next", ".nuxt", ".svelte-kit", ".output", ".vercel", ".turbo",
    "dist", "build", "out", "coverage", ".cache", ".parcel-cache", "storybook-static",
    ".venv", "venv", "env", ".env", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox",
    "site-packages", ".eggs", "bin", "obj", "target", ".gradle", ".idea", ".vscode", ".vs",
    ".cursor", ".claude", "wirehouse-out", "graphify-out", ".terraform", "migrations_backup",
}

SOURCE_EXT = {
    ".py": "python", ".pyi": None,
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".vue": "javascript", ".svelte": "javascript", ".astro": "javascript",
    ".cs": "csharp",
    ".sql": "sql", ".prisma": "prisma",
}

JS_LANGS = {"typescript", "javascript"}

ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template", ".env.dist", ".env.defaults", "example.env", "sample.env"}

MAX_FILE_BYTES = 400_000


def as_dict(value) -> dict:
    """A parsed config section when it has the expected shape, else empty: odd files must not stop a scan."""
    return value if isinstance(value, dict) else {}


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def lang_family(lang: str | None) -> str | None:
    if lang in JS_LANGS:
        return "js"
    if lang in ("python",):
        return "python"
    if lang == "csharp":
        return "dotnet"
    return None


@dataclass
class SourceFile:
    rel: str
    lang: str
    size: int
    text: str
    sha: str
    lines: int
    is_test: bool = False

    @property
    def dir(self) -> str:
        d = os.path.dirname(self.rel)
        return d.replace("\\", "/")


@dataclass
class ScanResult:
    root: Path
    sources: list[SourceFile] = field(default_factory=list)
    configs: dict[str, list[str]] = field(default_factory=dict)  # category -> rel paths
    skipped_large: int = 0

    def read(self, rel: str) -> str:
        try:
            return (self.root / rel).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ""


@dataclass(frozen=True)
class IgnoreRule:
    base: str          # folder of the .gitignore that holds the rule ("" for the root)
    pattern: str
    negate: bool
    dir_only: bool
    anchored: bool


def _load_gitignore(root: Path, rel_dir: str = "") -> list[IgnoreRule]:
    rules: list[IgnoreRule] = []
    gi = root / rel_dir / ".gitignore"
    if gi.is_file():
        for raw in gi.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            line = line[1:] if negate else line
            dir_only = line.endswith("/")
            pat = line.rstrip("/")
            if pat:
                rules.append(IgnoreRule(rel_dir, pat.lstrip("/"), negate, dir_only, pat.startswith("/") or "/" in pat))
    return rules


def _rule_matches(rule: IgnoreRule, rel: str) -> bool:
    sub = rel[len(rule.base) + 1:] if rule.base else rel
    name = sub.rsplit("/", 1)[-1]
    pat = rule.pattern
    if pat.startswith("**/"):   # "**/x" matches x at any depth, the top included
        return fnmatch.fnmatch(sub, pat) or fnmatch.fnmatch(name, pat[3:]) or fnmatch.fnmatch(sub, pat[3:])
    if rule.anchored:
        return fnmatch.fnmatch(sub, pat) or fnmatch.fnmatch(sub, pat + "/**")
    return fnmatch.fnmatch(name, pat)


def _ignored(rel: str, is_dir: bool, rules: list[IgnoreRule]) -> bool:
    """Git's rule: the last pattern that matches decides, and `!pattern` re-includes."""
    hit = False
    for rule in rules:
        if rule.dir_only and not is_dir:
            continue
        if rule.base and not rel.startswith(rule.base + "/"):
            continue
        if _rule_matches(rule, rel):
            hit = not rule.negate
    return hit


def _is_test(rel: str) -> bool:
    low = rel.lower()
    parts = low.split("/")
    name = parts[-1]
    if any(p in ("tests", "test", "__tests__", "e2e", "spec", "specs") for p in parts[:-1]):
        return True
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or name.endswith("tests.cs")
        or name == "conftest.py"
    )


def _config_category(rel: str, name: str) -> str | None:
    low = name.lower()
    rl = rel.lower()
    if low == "package.json":
        return "package_json"
    if low in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "pipfile") or (
        low.startswith("requirements") and low.endswith(".txt")
    ):
        return "python_manifest"
    if low.endswith(".csproj") or low.endswith(".fsproj"):
        return "csproj"
    if low.endswith(".sln"):
        return "sln"
    if (low.startswith("docker-compose") or low.startswith("compose")) and low.endswith((".yml", ".yaml")):
        return "compose"
    if low == "dockerfile" or low.startswith("dockerfile.") or low.endswith(".dockerfile"):
        return "dockerfile"
    if low.endswith(".tf"):
        return "terraform"
    if "/.github/workflows/" in "/" + rl and low.endswith((".yml", ".yaml")):
        return "workflow"
    if low in (".gitlab-ci.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml", "jenkinsfile"):
        return "workflow"
    if low in ENV_TEMPLATES:
        return "env_template"
    if low.startswith("appsettings") and low.endswith(".json"):
        return "appsettings"
    if low in ("tsconfig.json", "jsconfig.json"):
        return "tsconfig"
    if low in ("nginx.conf", "caddyfile", "traefik.yml", "traefik.yaml") or low.endswith(".nginx.conf"):
        return "gateway_config"
    if low in ("vercel.json", "netlify.toml", "fly.toml", "render.yaml", "railway.json", "railway.toml",
               "app.yaml", "serverless.yml", "serverless.yaml", "firebase.json", "wrangler.toml", "Procfile".lower()):
        return "platform"
    if low.endswith((".yml", ".yaml")) and any(seg in rl for seg in ("k8s", "kube", "helm", "manifests", "deploy")):
        return "k8s"
    return None


def scan(root: Path) -> ScanResult:
    root = root.resolve()
    result = ScanResult(root=root)
    rules_for: dict[str, list[IgnoreRule]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        # each folder's .gitignore applies below it, after the rules of the folders above
        patterns = rules_for.pop(rel_dir, []) + _load_gitignore(root, rel_dir)
        keep = []
        for d in dirnames:
            rd = f"{rel_dir}/{d}" if rel_dir else d
            if d in IGNORE_DIRS or d.endswith(".egg-info") or (d.startswith(".") and d not in (".github",)):
                continue
            if _ignored(rd, True, patterns):
                continue
            keep.append(d)
            rules_for[rd] = patterns
        dirnames[:] = sorted(keep)
        for fn in sorted(filenames):
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            if _ignored(rel, False, patterns):
                continue
            cat = _config_category(rel, fn)
            if cat:
                result.configs.setdefault(cat, []).append(rel)
            ext = os.path.splitext(fn)[1].lower()
            lang = SOURCE_EXT.get(ext)
            if not lang or fn.endswith(".d.ts") or fn.endswith(".min.js"):
                continue
            full = Path(dirpath) / fn
            try:
                size = full.stat().st_size
                if size > MAX_FILE_BYTES:
                    result.skipped_large += 1
                    continue
                raw = full.read_bytes()
            except OSError:
                continue
            text = raw.decode("utf-8-sig", errors="replace")   # editors on Windows often write a BOM
            result.sources.append(
                SourceFile(
                    rel=rel,
                    lang=lang,
                    size=size,
                    text=text,
                    sha=hashlib.sha1(raw).hexdigest()[:16],
                    lines=text.count("\n") + 1,
                    is_test=_is_test(rel),
                )
            )
    return result
