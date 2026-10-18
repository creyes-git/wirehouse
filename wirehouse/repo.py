"""Git identity for commit-pinned source links.

The viewer links each file and line to the code host at the exact commit that was
scanned, so a shared wirehouse.html keeps pointing at the code it was drawn from.
Only the host, the repository path and the commit are kept. The raw remote URL is
never stored: remotes can carry credentials (`https://user:token@host/...`).

Everything here is best effort. No git, no remote or an unknown host simply means
no web links; the VS Code links still work on the machine that ran the scan.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

PROVIDERS = {"github": "GitHub", "gitlab": "GitLab", "bitbucket": "Bitbucket", "azure": "Azure DevOps"}
MAX_DIRTY = 2000

_SCP = re.compile(r"^(?:ssh://)?[\w.~-]+@(?P<host>[\w.-]+)(?::\d+)?[:/](?P<path>[^?#]+?)(?:\.git)?/?$")
_HTTP = re.compile(r"^https?://(?:[^@/]+@)?(?P<host>[\w.-]+)(?::\d+)?/(?P<path>[^?#]+?)(?:\.git)?/?$")
_SAFE_PATH = re.compile(r"^[\w.~%-]+(?:/[\w.~%-]+)*$")


def parse_remote(url: str) -> dict | None:
    """`git remote` URL -> {"provider", "web"} (https base of the repo), or None if the host is unknown."""
    url = (url or "").strip()
    m = _HTTP.match(url) or _SCP.match(url)
    if not m:
        return None
    host, path = m.group("host").lower(), m.group("path").strip("/")
    if "." not in host or not _SAFE_PATH.match(path):
        return None   # ssh config aliases ("github-work") and odd paths: no guessing
    if host == "ssh.dev.azure.com":
        parts = path.split("/")   # v3/org/project/repo
        if len(parts) == 4 and parts[0] == "v3":
            return {"provider": "azure", "web": f"https://dev.azure.com/{parts[1]}/{parts[2]}/_git/{parts[3]}"}
        return None
    if host == "dev.azure.com" or host.endswith(".visualstudio.com"):
        if "/_git/" not in f"/{path}":
            return None
        return {"provider": "azure", "web": f"https://{host}/{path}"}
    for key in ("github", "gitlab", "bitbucket"):
        if key in host:
            if path.count("/") < 1:
                return None
            return {"provider": key, "web": f"https://{host}/{path}"}
    return None


def _git(root: Path, *args: str, ok: tuple[int, ...] = (0,)) -> str | None:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        # core.fsmonitor would run a command named by the scanned repo's own config: never for a scan
        r = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode in ok else None


def _repo_sets_filters(root: Path) -> bool:
    """True when the checkout's own config (not the user's or the system's) defines a clean/smudge filter.

    `git status` runs those filters, so a `.git/config` that came with an archive or a copied folder could
    run any command during a scan. Unknown means yes: the dirty list is then skipped.
    """
    out = _git(root, "config", "--show-scope", "--includes", "--get-regexp", r"^filter\.", ok=(0, 1))
    if out is None:
        return True
    return any(line.split("\t", 1)[0] in ("local", "worktree") for line in out.splitlines())


def repo_info(root: Path) -> dict | None:
    """What the viewer needs to build web links for files under `root`, or None outside a git checkout."""
    top = _git(root, "rev-parse", "--show-toplevel")
    rev = _git(root, "rev-parse", "HEAD")
    if not top or not rev or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", rev.strip()):
        return None
    rev = rev.strip()
    try:
        prefix = Path(root).resolve().relative_to(Path(top.strip()).resolve()).as_posix()
    except ValueError:
        return None
    prefix = "" if prefix == "." else prefix
    remote = None
    remotes = (_git(root, "remote") or "").split()
    for name in (["origin"] if "origin" in remotes else []) + [r for r in remotes if r != "origin"]:
        remote = parse_remote(_git(root, "remote", "get-url", name) or "")
        if remote:
            break
    info = {"revision": rev, "short": rev[:7], "prefix": prefix}
    if remote:
        info.update(remote, host_name=PROVIDERS[remote["provider"]])
        info["pushed"] = bool((_git(root, "branch", "-r", "--contains", rev) or "").strip())
    # Files whose working copy differs from the commit: their web link shows older code.
    status = None if _repo_sets_filters(root) else _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    dirty, entries = [], (status or "").split("\0")
    complete = status is not None
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        if e[0] in "RC":
            i += 1   # renames carry the old path as the next entry
        path = e[3:]
        if prefix:
            if not path.startswith(prefix + "/"):
                continue
            path = path[len(prefix) + 1:]
        dirty.append(path)
        if len(dirty) >= MAX_DIRTY:
            complete = False
            break
    info["dirty"] = sorted(dirty)
    info["dirty_complete"] = complete   # False: git failed or the list was cut, so a file missing from it may still be changed
    return info
