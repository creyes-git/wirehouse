# AGENTS.md

## Setup / verify

```bash
pip install -e ".[dev]"   # Python >=3.11, runtime dep is only pyyaml
python -m pytest
```

Single test: `python -m pytest tests/test_wirehouse.py::<name> -v`. No lint, typecheck, or CI config in repo.

## Architecture

Pipeline: `scan` → per-file facts → units → infra → `archmap.raw.json` → + `enrichment.json` → `wirehouse.html`, all in `<project>/wirehouse-out/` (gitignored).

- `wirehouse/cli.py` — entrypoint (`wirehouse.cli:main`, also `python -m wirehouse`). Subcommands `scan|render|build <path> [-o OUT] [--open]`, plus `install` (writes `~/.claude/skills/wirehouse/SKILL.md`). `render` requires `archmap.raw.json`; `build` = scan + render, reusing cached enrichment.
- `wirehouse/scan.py` — honours `.gitignore`, skips `IGNORE_DIRS` (build output, venvs, `wirehouse-out`, dot-dirs except `.github`), files >400KB, `*.d.ts`/`*.min.js`. Source langs: py/ts/js/vue/svelte/astro/cs/sql/prisma. **Never reads real `.env`** — only `.env.example`-style templates.
- `wirehouse/detectors/` — `code.py` (imports, env reads, URLs, endpoints, tables per file), `units.py` (each `package.json`/Python manifest/`.csproj` → unit), `infra.py` (compose, Dockerfiles, env templates, Terraform, K8s, workflows, gateway/hosting configs).
- `wirehouse/build.py` — `build_archmap(root)` is the programmatic entrypoint. ~115 signatures map imports/deps/URLs/env/docker images to blocks. Env values wire files to compose services (`API_URL=http://api:8000`) or resources (`DATABASE_URL=...@db/...`). TS path aliases resolved via JSONC-safe `_strip_jsonc` (must not break globs like `**/*.ts`).
- `wirehouse/model.py` — archmap contract: `node()`/`edge()`/`loc()`, `LAYERS` (clients → edge → services → data → external, ops on side), `KINDS`, `EDGE_KINDS`. Edges stored at file level, rolled up to top-level blocks at render/enrich time.
- `wirehouse/enrich.py` — enrichment entries carry node content `hash`; `write_brief` only lists changed/new blocks (top-level + folders with ≥2 files) and undescribed top links. `merge` applies `add_nodes`/`add_edges` (evidence required) and `remove_*` (top-level pair removal drops all edges between the pair).
- `wirehouse/render/html.py` — inlines `template.html` + `app.css` + `app.js` + `vendor/three.min.js` + fonts + `window.WIREHOUSE = {...}` into one offline `wirehouse.html` (~1.2MB). Placeholders must all be filled; no `<script src=` allowed.
- `wirehouse/skill/SKILL.md` — the `/wirehouse` agent workflow (scan → describe → render); `{{WIREHOUSE_HOME}}` is templated at install time.

## Conventions

- Use absolute imports from the `wirehouse` package.
- Test-only files (`tests/`, `test_*`, `*.spec.*`, `conftest.py`) are flagged `is_test`: their imports must not create blocks or edges (see `test_resources_and_layers`).
- `depends_on` edges are dropped when the same top-level pair already has a real connection.
- Secrets must never reach output: env values, passwords, connection strings are redacted. Any change touching env/URL/connection-string handling must keep `test_secrets_never_leak` and `test_dotnet_and_terraform` passing. `render_html` output is covered by the same check.
- HTML self-containment invariant (`test_html_is_self_contained`): exactly 3 `</script>`, no network loads.
