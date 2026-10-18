# AGENTS.md

## Setup / verify

```bash
pip install -e ".[dev]"   # Python >=3.11, runtime dep is only pyyaml
python -m pytest
```

Single test: `python -m pytest tests/test_wirehouse.py::<name> -v`. No lint, typecheck, or CI config in repo.
Browser tests: `pip install -e ".[browser]"`, then `python -m pytest tests/test_viewer.py` (skipped without Playwright; uses installed Chrome/Edge or Playwright's Chromium). Run them after any `render/app.js` change; `node --check wirehouse/render/app.js` catches syntax errors fast.

## Architecture

Pipeline: `scan` → per-file facts → units → infra → `archmap.raw.json` → + `enrichment.json` → `wirehouse.html`, all in `<project>/wirehouse-out/` (gitignored).

- `wirehouse/cli.py` — entrypoint (`wirehouse.cli:main`, also `python -m wirehouse`). Subcommands `scan|render|build <path> [-o OUT] [--open]`, plus `install` (writes `SKILL.md` to `~/.agents/skills` and every detected agent's skills folder, see `AGENT_SKILL_DIRS`; `--agent`, `--dir`, `--print`). `render` requires `archmap.raw.json`; `build` = scan + render, reusing cached enrichment.
- `wirehouse/scan.py` — honours `.gitignore`, skips `IGNORE_DIRS` (build output, venvs, `wirehouse-out`, dot-dirs except `.github`), files >400KB, `*.d.ts`/`*.min.js`. Source langs: py/ts/js/vue/svelte/astro/cs/sql/prisma. **Never reads real `.env`** — only `.env.example`-style templates.
- `wirehouse/detectors/` — `code.py` (imports, env reads, URLs, endpoints, tables per file), `schema.py` (columns + foreign keys for SQL DDL/Prisma/SQLAlchemy/Django/Drizzle/TypeORM; never keeps defaults), `units.py` (each `package.json`/Python manifest/`.csproj` → unit), `infra.py` (compose, Dockerfiles, env templates, Terraform, K8s, workflows, gateway/hosting configs).
- `wirehouse/build.py` — `build_archmap(root)` is the programmatic entrypoint. ~115 signatures map imports/deps/URLs/env/docker images to blocks. Env values wire files to compose services (`API_URL=http://api:8000`) or resources (`DATABASE_URL=...@db/...`). TS path aliases resolved via JSONC-safe `_strip_jsonc` (must not break globs like `**/*.ts`).
- `wirehouse/repo.py` — git remote/commit/dirty files → `archmap["repo"]` for commit-pinned web links (GitHub/GitLab/Bitbucket/Azure DevOps). Never stores the raw remote URL (it can carry credentials).
- `wirehouse/guide.py` — `apply(data, enrichment)` (called by `cli render`): validates the agent's `tours`/`quests` into `data["diagnostics"]` (`{code, severity, subject, message, fix}`), drops invalid parts, redacts secret-like text, and makes auto tours/quests when none are written.
- `wirehouse/model.py` — archmap contract: `node()`/`edge()`/`loc()`, `LAYERS` (clients → edge → services → data → external, ops on side), `KINDS`, `EDGE_KINDS`. Edges stored at file level, rolled up to top-level blocks at render/enrich time.
- `wirehouse/enrich.py` — enrichment entries carry node content `hash`; `write_brief` only lists changed/new blocks (top-level + folders with ≥2 files) and undescribed top links. `merge` applies `add_nodes`/`add_edges` and `remove_*` (top-level pair removal drops all edges between the pair). Added edges need at least one citation that `guide.Evidence` accepts, or they are left out with an `edge/*` diagnostic; agent text goes through `guide._clean`.
- `wirehouse/redact.py`: `scrub(data, share=, root=)` is the last pass over every key and value before output (`build_archmap`, `cli render`, `render_html`): redacts `SECRET_LIKE` text and, with `--share`, the project root and home folders. Keep new output fields covered by it, never by per-field checks alone.
- `wirehouse/render/app.js` — one IIFE in sections. Later sections plug in through hook lists declared early (`BUILD_HOOKS`, `SELECT_HOOKS`, `FILTER_HOOKS`, `HASH_PARTS`/`HASH_APPLY`, `PANEL_ACTS`, `KEYS`, `onEscape(prio, ...)`); a `const` used at load time must be declared above its first use. Traces (`walk()`) follow recorded edges only, minus `NOT_TRAFFIC` (`depends_on`, `provisions`); containers expand to their contents; hops count top-level block boundaries. `window.__wirehouse` is the test hook.
- `wirehouse/render/html.py` — inlines `template.html` + `app.css` + `app.js` + `vendor/three.min.js` + fonts + `window.WIREHOUSE = {...}` into one offline `wirehouse.html` (~1.2MB). Placeholders must all be filled; no `<script src=` allowed.
- `wirehouse/skill/SKILL.md` — the `/wirehouse` agent workflow (scan → describe → render) in the open SKILL.md format. Keep it agent-neutral: never name one agent; `{{WIREHOUSE_HOME}}` is templated at install time.

## Conventions

- Use absolute imports from the `wirehouse` package.
- Test-only files (`tests/`, `test_*`, `*.spec.*`, `conftest.py`) are flagged `is_test`: their imports must not create blocks or edges (see `test_resources_and_layers`).
- `depends_on` edges are dropped when the same top-level pair already has a real connection.
- Secrets must never reach output: env values, passwords, connection strings are redacted. Any change touching env/URL/connection-string handling must keep `test_secrets_never_leak` and `test_dotnet_and_terraform` passing. `render_html` output is covered by the same check.
- HTML self-containment invariant (`test_html_is_self_contained`): exactly 3 `</script>`, no network loads. Links out to code hosts are plain `<a href>`, never loads.
- Truth before spectacle: anything the viewer lights, counts or narrates (traces, routes, tours, quests, share cards) must come from recorded edges or validated enrichment, and must say so when it is loose or inferred.
- `archify/` is a third-party reference copy (gitignored), not part of Wirehouse.
- Anything published (the demo in `docs/demo/`, screenshots) is rendered with `--share`, so no local paths leak. `docs/brand/` is the brand kit (logo, favicons, social, README art; see its README for usage rules). The viewer inlines `render/vendor/favicon.svg` and draws the symbol in the top bar.
