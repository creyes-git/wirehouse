# Improvement log

One entry per pass of the improvement cycle: what was audited, offered, done, deferred and rejected.
Later passes read this first, so they build on earlier ones instead of repeating them.

## Pass 1 - 2026-10-18

**Goal statement:** Wirehouse is a local, offline Python CLI and agent skill that scans a repository,
maps its architecture from code evidence, and renders it as one self-contained 3D "warehouse" HTML page
with traces, routes, tours and quests. It serves developers (and their coding agents) who need to
onboard to, review or explain a codebase, with every pipe backed by a file:line citation.

**Areas covered:** all of `wirehouse/` (scan, detectors, build, signatures, model, enrich, guide, repo,
cli, render/html.py, template.html, app.js, app.css, skill/SKILL.md) and both test files.

**Audit summary:** 4 High, 11 Medium, about 25 Low (batched into 6 menu items). Core weak spots were
secrets and local paths reaching output, agent-written data skipping checks, and odd input crashing the
scan or render. Tests were 19 end-to-end checks with almost no edge cases.

**Menu offered:**
- A1 SQLite/ADO connection strings leaked into ids · A2 agent add_edges skipped evidence and redaction ·
  A3 diagnostics echoed raw agent input · A4 `#plan=1` link crashed a fresh page · A5 gitignored configs
  read · A6 odd config shapes crashed the scan · A7 malformed enrichment crashed render · A8 quadratic
  `JS_FROM` regex · A9 placeholder injection in html.py · A10 BOM files skipped/rejected · A11
  `NEXT_PUBLIC_API_URL`/cors lines dropped edges · A12 comment URLs drawn as calls · A13 `remove_edges`
  one direction only · A14 upstream traces and nested routes overstated reach · A15 GPU leaks · A16 small
  detector mistakes · A17 small enrichment/git gaps · A18 small viewer bugs · A19 dead code · A20 docs
  drift · A21 partial gitignore support
- B1 one redaction pass over all output · B2 shape checks at the edges · B3 "nasty repo" test
- C1 surface checks (`--strict`, Checks panel) · C2 Markdown/Mermaid export · C3 Go support · C4 GitHub
  Action · C5 change review

**Chosen & done:** everything except C4, on local branches merged into `main` (not pushed: no remote yet).
- A1-A3 + B1: `wirehouse/redact.py` scrubs every key and value before any output; SQLite strings keep
  only the file name; agent edges need a citation that checks out.
- A5, A6, A7, A10, A17, A21, B2: git-style `.gitignore` (nested, `!`), `as_dict`/`as_list` guards,
  `enrich.normalize` turns wrong shapes into `enrichment/wrong-shape` diagnostics, BOM-tolerant reads,
  fsmonitor off and SHA-256 commits for git.
- A8, A11, A12, A16: import regex is linear (20k-line file: ~90 s to 0.3 s); self-URL filter fixed;
  comment URLs skipped; eight small detector fixes.
- A9, A13: one-pass template fill; `remove_edges` both ways.
- A4, A14, A15, A18 + viewer half of A19: plan links, truthful upstream/routes, GPU memory freed,
  keyboard/export/progress fixes.
- A19, A20: dead scanner code removed; installed skill no longer points a pip install at site-packages.
- B3: `tests/test_nasty_repo.py`.
- C1: Checks button and `--strict`. C2: `wirehouse export` (`architecture.md` / `.mmd`).
  C3: Go modules, imports, routes, env reads, ~30 drivers/SDKs. C5: `--against <archmap.json>` with a
  Changes panel (`V`), floor badges and an export section.
- Also: viewer tests close their pages (suite went from ~140 s with random timeouts to ~15 s).
- Tests: 19 to 64 (plus the hostile-repo test), all passing.

**Deferred:**
- C4 GitHub Action (user chose to skip this pass).
- From the audit but not on the menu: Python units count dev/optional deps when classifying while JS
  does not (`units.py` `_classify`); some EXTRACTED edges carry no evidence (Prisma datasource, k8s image
  `provisions`, ORM edges in `build.py`).
- Found while testing: mapping Wirehouse itself turns `wirehouse/signatures.py` (the pattern table) into
  "uses PostgreSQL / SQLite / ASP.NET Identity" edges, because code-pattern regexes match their own
  definitions.
- `docs/demo/index.html` was rendered by the old version; regenerate it (with `--share`) before
  publishing.
- Change review straight from git (`--against main` without a saved map).

**Rejected:** none.

**Next pass focus:** detector precision on self-describing code (signature tables, fixtures, docs) and
the EXTRACTED-without-evidence edges, since both put claims on the map that the page presents as found
in code.
