"""The last check before anything is written: no credential-looking text, and with `--share` no local paths.

Detectors and enrichment each avoid secrets on their own, but every new field is one more way for a
value to slip through. `scrub` walks the finished archmap once (keys and values) just before it is
written, so a slip in one place cannot reach the output.
"""

from __future__ import annotations

import re
from pathlib import Path

# Values that look like credentials. Authored text should never carry them; if it does, they are cut out.
# Token prefixes use `(?<![A-Za-z0-9])` rather than `\b`, which fails after `_` (`KEY_ghp_...`).
_TOKENS = (
    r"(?:sk|pk|rk|whsec)_(?:live|test)?_?[A-Za-z0-9_]{8,}",
    r"gh[pousr]_[A-Za-z0-9]{10,}", r"github_pat_[A-Za-z0-9_]{10,}",
    r"(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])",
    r"xox[abpr]-[A-Za-z0-9-]{10,}",
    r"eyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*",            # JWT
    r"sk-(?:proj-|ant-|svcacct-)?(?=[A-Za-z_-]{0,200}\d)[A-Za-z0-9_-]{20,}",  # OpenAI, Anthropic
    r"AIza[0-9A-Za-z_-]{35}", r"glpat-[0-9A-Za-z_-]{20,}", r"npm_[A-Za-z0-9]{36}",
    r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}", r"hf_[A-Za-z0-9]{30,}",
    r"SK[0-9a-fA-F]{32}(?![0-9a-fA-F])",                                      # Twilio API key
)
# Settings whose value is the secret. `(?<![A-Za-z])` lets `DB_PASSWORD=` and `client_secret=` match, and
# `["']?` before the separator covers JSON and YAML keys (`"password": "x"`).
_KEYS = (r"password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|token|access[_-]?key"
         r"|secret[_-]?access[_-]?key|account[_-]?key|shared[_-]?access[_-]?key|private[_-]?key|sig")
SECRET_LIKE = re.compile(
    r"(?<![A-Za-z0-9])(?:" + "|".join(_TOKENS) + ")"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b[a-z]+://[^\s:/@]+:[^\s@]+@"
    r"|https://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9/_-]+"
    r"|https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"
    r"|\b(?:[Bb]earer|Basic)[ \t]+(?=[A-Za-z0-9._~+/-]{0,500}[0-9+/=])[A-Za-z0-9._~+/-]{12,}=*"
    r"|(?i:(?<![A-Za-z])(?:" + _KEYS + r")['\"]?\s*[:=]\s*['\"]?[^\s'\",;]{4,})")
REDACTED = "[redacted]"
# A home folder names the person who ran the scan. Windows paths carry a drive letter. POSIX ones are
# only taken where a path starts (string start, space, quote, backtick, `=`, `(` or `[`), with the real
# capitals and not after an HTTP method, so routes such as `GET /users/{id}` or `GET /home/dashboard`
# stay as they are (endpoint paths are skipped entirely).
_METHODS = ("GET", "PUT", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS", "ANY", "PAGE", "WS")
_PATH_START = r"(?<![^\s\"'`=(\[])" + "".join(f"(?<!{m} )" for m in _METHODS)
HOME_PATH = re.compile(
    r"(?i:\b[A-Za-z]:[\\/]+(?:Users|Documents and Settings))[\\/]+[^\\/\s\"'<>`]+"
    r"|" + _PATH_START + r"(?:/(?:mnt/)?[A-Za-z]/Users|/Users|/(?:var/|export/)?home)/[^/\s\"'<>`]+"
    r"|" + _PATH_START + r"/root(?=[/\s\"'<>`]|$)")

# Control characters (not tab or newline): an id or name holding `\x1b[...` would drive the terminal
# when diagnostics are printed, and no map text needs them.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _walk(value, fix, route=False):
    if isinstance(value, str):
        return fix(value, route)
    if isinstance(value, dict):
        return {fix(k, route) if isinstance(k, str) else k: _walk(v, fix, route or k == "endpoints") for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, fix, route) for v in value]
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

    def fix(text: str, route: bool) -> str:
        nonlocal hits
        out = SECRET_LIKE.sub(REDACTED, text)
        if out != text:
            hits += 1
        out = CONTROL.sub("", out)
        if share:
            for r in roots:
                out = out.replace(r + "/", "").replace(r + "\\", "").replace(r, ".")
            if not route:   # an endpoint path is a URL, never a folder on this machine
                out = HOME_PATH.sub("~", out)
        return out

    return _walk(data, fix), hits
