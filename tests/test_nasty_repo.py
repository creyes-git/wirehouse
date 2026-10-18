"""One repository full of everything that has gone wrong before, mapped end to end.

Each case also has a focused test in test_wirehouse.py. This one guards the invariants together:
a scan of hostile input finishes quickly, and no secret or local path reaches any output file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from wirehouse.cli import main

BOM = "\ufeff"
SECRETS = [
    "sk_live_NASTY_0000000001", "hunter2SECRET", "pw_in_url_secret", "ghp_nastytoken1234567890",
    "AKIANASTYKEY00000000", "agent_pw_secret", "token_in_tech_secret", "remote_pw_secret",
    # newer formats, built from pieces so this file holds nothing that looks like a live credential
    "gh" + "s_" + "nastyDocstring0000000000", "sk-" + "proj-" + "nastyWorkflow000000001", "glp" + "at-" + "nastyEndpoint0000001",
    "eyJ" + "hbGciOiJub25lIn0.eyJ" + "zdWIiOiJuYXN0eSJ9.", "nastyDbPassword9",
]
FILES = {
    # secrets in every format the scanner reads
    ".env.example": f"STRIPE_SECRET_KEY={SECRETS[0]}\nDATABASE_URL=postgresql://app:{SECRETS[2]}@db:5432/app\n",
    ".env": "REAL=never_read_secret\n",
    "src/Api/Api.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"><ItemGroup>'
                          '<PackageReference Include="Microsoft.EntityFrameworkCore.Sqlite" Version="8.0.0" /></ItemGroup></Project>',
    "src/Api/appsettings.json": BOM + json.dumps({"ConnectionStrings": {"Main": f"Data Source=app.sqlite;Password={SECRETS[1]}"}}),
    "src/Api/Program.cs": 'var cs = builder.Configuration.GetConnectionString("Main");\n',
    "web/package.json": BOM + json.dumps({"name": "web", "dependencies": {"next": "15.0.0"}, "scripts": ["oops"]}),
    "web/lib/github.ts": f'const token = "{SECRETS[3]}";\nexport const repos = () => fetch("https://api.github.com/user/repos");\n',
    "web/lib/aws.ts": f'export const key = "{SECRETS[4]}";\n',
    "web/lib/creds.ts": f'export const ping = () => fetch("https://deploy:{SECRETS[7]}@api.acme.io/v1");\n',
    # where code text reaches the page: docstrings, workflow names, endpoint paths
    "worker/sync.py": f'"""Nightly sync with {SECRETS[8]}.\n\nDB_PASSWORD={SECRETS[12]} token {SECRETS[11]}"""\n'
                      f'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/hooks/{SECRETS[10]}")\ndef hook():\n    return 1\n',
    ".github/workflows/deploy.yml": f"name: deploy {SECRETS[9]}\non: push\njobs:\n  ship:\n    runs-on: ubuntu-latest\n",
    # odd shapes
    "docker-compose.yml": "services:\n  - web\n",
    "tools/tsconfig.json": "[]",
    "tools/pyproject.toml": 'project = "x"\n',
    ".github/workflows/ci.yml": "jobs:\n  - test\n",
    # comments are not calls
    "worker/main.py": "# see https://api.openai.com/v1/models\nimport os\nprint(os.environ.get('X'))\n",
    # a long file with no `from` after its exports
    "web/lib/big.ts": "import x from 'y'\n" + "export const A = 1\n" * 20_000,
}
ENRICHMENT = {
    "nodes": {"unit:js:web": {"description": f"password={SECRETS[5]}", "tech": [f"token={SECRETS[6]}"]}},
    "add_nodes": [{"id": "res:mailer", "name": "Mailer", "locations": [{"file": "C:/Users/nasty-person/x.py"}]}],
    "add_edges": [{"source": "unit:js:web", "target": "res:mailer", "description": f"api_key={SECRETS[5]}",
                   "evidence": [{"file": "/home/nasty-person/y.py", "line": 1}]}],
    "tours": [{"title": "Broken", "stops": [{"node": "unit:js:web", "text": f"secret={SECRETS[5]}",
                                            "evidence": [{"file": "web/package.json", "line": float("inf")}]}]}],
    "links": {"unit:js:web->res:mailer": f"token={SECRETS[6]}"},
}


@pytest.fixture(scope="module")
def nasty(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("nasty")
    for rel, body in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    out = root / "wirehouse-out"
    out.mkdir()
    (out / "enrichment.json").write_text(BOM + json.dumps(ENRICHMENT), encoding="utf-8")
    return root, out


def test_hostile_repo_maps_quickly_and_leaks_nothing(nasty):
    root, out = nasty
    t0 = time.perf_counter()
    assert main(["build", str(root), "--share"]) == 0
    assert time.perf_counter() - t0 < 30
    outputs = {p.name: p.read_text(encoding="utf-8") for p in out.iterdir() if p.name != "enrichment.json"}
    assert {"archmap.raw.json", "archmap.json", "wirehouse.html", "enrich-brief.md"} <= set(outputs)
    for name, text in outputs.items():
        for secret in SECRETS + ["never_read_secret"]:
            assert secret not in text, (name, secret)
    for name in ("archmap.json", "wirehouse.html"):   # --share: no local folders in what gets published
        for local in ("nasty-person", str(root), str(root).replace("\\", "/"), json.dumps(str(root))[1:-1]):
            assert local not in outputs[name], (name, local)
    data = json.loads(outputs["archmap.json"])
    assert any(d["code"].startswith("enrichment/") or d["code"].startswith("evidence/") for d in data["diagnostics"])
    assert not [e for e in data["edges"] if e.get("source_tag") == "agent"]     # the added edge cited nothing real
    assert "res:openai" not in {n["id"] for n in data["nodes"]}
