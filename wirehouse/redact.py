"""The last check before anything is written: no credential-looking text, and with `--share` no local paths.

Detectors and enrichment each avoid secrets on their own, but every new field is one more way for a
value to slip through. `scrub` walks the finished archmap once (keys and values) just before it is
written, so a slip in one place cannot reach the output.
"""

from __future__ import annotations

import re
from pathlib import Path

# Values that look like credentials. Authored text should never carry them; if it does, they are cut out.
SECRET_LIKE = re.compile(
    r"\b(?:sk|pk|rk|whsec)_(?:live|test)?_?[A-Za-z0-9_]{8,}|\bghp_[A-Za-z0-9]{10,}|\bgithub_pat_[A-Za-z0-9_]{10,}|\bAKIA[0-9A-Z]{16}\b"
    r"|\bxox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b[a-z]+://[^\s:/@]+:[^\s@]+@"
    r"|(?i:\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|token)\s*[:=]\s*['\"]?[^\s'\",;]{4,})")
REDACTED = "[redacted]"
# A home folder names the person who ran the scan: C:\Users\<name>, /Users/<name>, /home/<name>.
HOME_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]+Users|(?<![\w.])/(?:Users|home))[\\/]+[^\\/\s\"'<>`]+", re.I)


def _walk(value, fix):
    if isinstance(value, str):
        return fix(value)
    if isinstance(value, dict):
        return {fix(k) if isinstance(k, str) else k: _walk(v, fix) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, fix) for v in value]
    return value


def scrub(data: dict, *, share: bool = False, root: str | Path | None = None) -> tuple[dict, int]:
    """A copy of `data` with secret-like text redacted -> (data, number of strings redacted).

    With `share`, the project root and home folders are cut out of every string as well.
    """
    hits = 0
    roots = []
    if share and root:
        r = str(root).rstrip("\\/")
        roots = sorted({r, r.replace("\\", "/"), r.replace("/", "\\")}, key=len, reverse=True)

    def fix(text: str) -> str:
        nonlocal hits
        out = SECRET_LIKE.sub(REDACTED, text)
        if out != text:
            hits += 1
        if share:
            for r in roots:
                out = out.replace(r + "/", "").replace(r + "\\", "").replace(r, ".")
            out = HOME_PATH.sub("~", out)
        return out

    return _walk(data, fix), hits
