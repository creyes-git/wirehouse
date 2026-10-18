# Improvement log

Wirehouse improves in passes. Each pass audits the code, offers the maintainer a menu of fixes and
improvements, builds the chosen ones and records the rest. This log keeps one entry per pass: what was
looked at, what was found, what was chosen and done, and what was put off and why. Later passes start
here, so they build on earlier ones instead of repeating them. The changes themselves are listed in
[CHANGELOG.md](CHANGELOG.md), and open items in [TODO.md](TODO.md).

Severity in the audit summaries: **High** means a secret or local path could leak, or a common input
broke the map; **Medium** means a wrong claim on the map, a crash or a hang on unusual input; **Low**
means polish, docs or edge cases.

## Pass 1 - 2026-10-18

**Goal:** Wirehouse is a local, offline Python CLI and agent skill that scans a repository, maps its
architecture from code evidence, and renders it as one self-contained 3D "warehouse" HTML page with
traces, routes, tours and quests. It is for developers, and the coding agents they work with, who need
to onboard to, review or explain a codebase, with every pipe backed by a file and line.

**Areas covered:** all of `wirehouse/` (scan, detectors, build, signatures, model, enrich, guide, repo,
cli, render/html.py, template.html, app.js, app.css, skill/SKILL.md) and both test files.

**Audit summary:** 4 High, 11 Medium, about 25 Low (grouped into 6 menu items). The weak spots were
secrets and local paths reaching the output, agent-written data skipping the checks, and unusual input
crashing the scan or the page. The tests were 19 end-to-end checks with few edge cases.

**Menu offered:**
- Fixes: A1 SQLite and ADO connection strings leaked into ids · A2 agent `add_edges` skipped evidence
  and redaction · A3 diagnostics echoed raw agent input · A4 a `#plan=1` link crashed a fresh page · A5
  gitignored configs were read · A6 unusual config shapes crashed the scan · A7 malformed enrichment
  crashed render · A8 a quadratic `JS_FROM` regex · A9 placeholder injection in html.py · A10 files with
  a BOM were skipped or rejected · A11 `NEXT_PUBLIC_API_URL` and CORS lines dropped edges · A12 URLs in
  comments drawn as calls · A13 `remove_edges` worked in one direction only · A14 upstream traces and
  nested routes overstated reach · A15 GPU memory leaks · A16 small detector mistakes · A17 small
  enrichment and git gaps · A18 small viewer bugs · A19 dead code · A20 docs drift · A21 partial
  gitignore support
- Hardening: B1 one redaction pass over all output · B2 shape checks at every input · B3 a "nasty
  repository" test
- Features: C1 surface the checks (`--strict`, Checks panel) · C2 Markdown and Mermaid export · C3 Go
  support · C4 a GitHub Action · C5 change review

**Chosen and done:** everything except C4.
- A1 to A3 and B1: `wirehouse/redact.py` scrubs every key and value before any output; SQLite strings
  keep only the file name; agent edges need a citation that checks out.
- A5, A6, A7, A10, A17, A21 and B2: git-style `.gitignore` (nested files, `!`), `as_dict`/`as_list`
  guards, `enrich.normalize` turns wrong shapes into `enrichment/wrong-shape` diagnostics, BOM-tolerant
  reads, fsmonitor off and SHA-256 commits for git.
- A8, A11, A12 and A16: the import regex is linear (a 20,000-line file went from about 90 s to 0.3 s);
  the self-URL filter is fixed; comment URLs are skipped; eight small detector fixes.
- A9 and A13: one-pass template fill; `remove_edges` works both ways.
- A4, A14, A15, A18 and the viewer half of A19: plan links, truthful upstream traces and routes, GPU
  memory freed, keyboard, export and progress fixes.
- A19 and A20: dead scanner code removed; the installed skill no longer points a pip install at
  site-packages.
- B3: `tests/test_nasty_repo.py`.
- C1: the Checks button and `--strict`. C2: `wirehouse export` (`architecture.md` / `.mmd`). C3: Go
  modules, imports, routes, env reads and about 30 drivers and SDKs. C5: `--against <archmap.json>` with
  a Changes panel (`V`), floor badges and an export section.
- Also: viewer tests close their pages (the suite went from about 140 s with random timeouts to about
  15 s).
- Tests: from 19 to 64, all passing.

**Deferred:**
- C4, the GitHub Action (the maintainer chose to skip it this pass).
- From the audit but not on the menu: Python units count dev and optional dependencies when classifying
  while JavaScript units do not (`units.py` `_classify`); some EXTRACTED edges carry no evidence (Prisma
  datasource, Kubernetes image `provisions`, ORM edges in `build.py`).
- Found while testing: mapping Wirehouse itself turns `wirehouse/signatures.py` (the pattern table)
  into "uses PostgreSQL / SQLite / ASP.NET Identity" edges, because code-pattern regexes match their own
  definitions.
- The demo in `docs/demo/` was rendered by an older version and needs regenerating with `--share`.
- Change review straight from git (`--against main` without a saved map).

**Rejected:** none.

**Next pass focus:** detector precision on code that describes technologies (signature tables, fixtures,
docs) and the EXTRACTED edges without evidence, since both put claims on the map that the page presents
as found in code.

## Pass 2 - 2026-10-18

**Goal:** make Wirehouse ready to publish (a security and precision audit of everything a stranger's
repository can feed it) and make the viewer smooth on ordinary laptops while keeping truth before
spectacle.

**Areas covered:** `redact.py`, `scan.py`, `repo.py`, `cli.py`, `enrich.py`, the detectors (`code.py`,
`schema.py`, `infra.py`, `units.py`), `build.py` import resolution, the release and CI workflows, the
docs, and the viewer's renderer, shadows, labels, camera, input and progress code. A regex fuzzer ran
every compiled pattern in the detectors against repeated hostile units.

**Audit summary:** 2 High, 9 Medium (plus 2 more found while fixing), about 20 Low.
- High: credential formats missing from the redaction pattern (GitHub `gho_`/`ghs_`, `ASIA` keys, JWTs,
  `sk-` keys, webhook URLs, Azure keys, auth headers, `DB_PASSWORD=`); `--share` turning API routes such
  as `GET /users/{id}` into `~`.
- Medium: a repository's own `enrichment.json` applied silently; `git status` running filters named by
  an untrusted `.git/config`; the scan following links out of the project and hanging on pipes;
  quadratic regexes (up to 174 s for one file); a YAML alias bomb hanging the build; a crash on odd
  Kubernetes `metadata`; every `app.yaml` taken for App Engine; client `api.get(...)` calls drawn as
  served endpoints; monorepo imports making no edges. Found while fixing: three more quadratic patterns
  (`TYPEORM_PROP`, `_GO_REQUIRE`, `URL_ANY`) and a Pass 1 bound that cut off long generated export lists.
- Low: listed in TODO.md with location and suggested fix.
- Viewer baseline (test page, main floor, day shift): 273 draw calls per frame, 124 shadow casters drawn
  every frame, pixel ratio 2 with MSAA.

**Menu offered:** fix every High and Medium finding; record the Low ones; cut release 0.3.0 with CI
updates and a regenerated demo; and for the viewer, four groups: performance (adaptive resolution,
static shadow map, idle throttle, instancing), visuals (readable room labels, contact shadows, pipe
streaks, a concrete floor), game feel (camera smoothing and collision, click feedback, worker
animation, optional sound) and mechanics (trace ripple, a first-shift checklist, exploration marks).

**Chosen and done:** all of it, in seven stacked pull requests.
- Security: a wider credential pattern and real-home-folder matching (`/users/{id}` routes survive
  `--share`); a loud warning and an `enrichment/removed-*` check for every removal when
  `enrichment.json` is tracked by git; no `git status` when the checkout defines its own filters; reads
  confined to regular files inside the project with a size cap; linear regexes with a timing test per
  case; scalar-only YAML values; control characters stripped from output.
- Detection: `as_dict` for k8s `metadata`; App Engine only with `runtime:`; routes need a server import
  or a handler; workspace packages, `extends` chains and `tsconfig.base.json` resolve; Go named in
  descriptions; long `{ ... }` export lists read again.
- Release: 0.3.0 with compare links; `github-release` waits for PyPI; actions on their current majors;
  `setuptools>=77`; the demo rendered by 0.3.0 with its enrichment kept beside it; TODO.md, the README
  install table and this log reworded for a public repository.
- Viewer: on the test page's main floor in day mode, draw calls went from 273 to 132 per frame with
  shadow casters drawn once per room instead of every frame, at pixel ratio 1.5 (stepping to 1 on slow
  devices); night shift from 167 to 150. Labels are readable from a room's door, blocks stand on
  contact shadows, pipes show direction, the camera eases and stays out of blocks, clicks answer, the
  worker leans and looks, sound is optional, traces ripple in hop order, and the Clipboard has a
  four-step first-shift checklist with no scores.
- Tests: from 68 to 153, all passing, including 17 new viewer tests that measure through
  `window.__wirehouse`.

**Deferred:** the Low findings (TODO.md); the night shift's remaining draw calls (one per glow edge line
and label sprite); measuring on real integrated GPUs and phones (the numbers here come from headless
SwiftShader, which shows draw calls exactly but pixel cost only relatively); the items carried over from
Pass 1 (a GitHub Action, change review straight from git, unit classification of dev dependencies).

**Rejected:** none.

**Next pass focus:** precision on code that describes technologies (signature tables, fixtures, docs)
and on EXTRACTED edges without evidence. They are the last places where the map states something as
found in code that the code does not do, which matters more than any further polish.
