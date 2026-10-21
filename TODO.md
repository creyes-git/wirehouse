# TODO

Known gaps and deferred work. Each entry has a date, what is wrong or missing, where it is, and a
suggested fix. Fixed items move to [CHANGELOG.md](CHANGELOG.md); the reasoning behind each pass is in
[IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md).

## Features and precision

- **Date:** 2026-10-18 · **What:** A GitHub Action that builds the map and posts `wirehouse export` on
  pull requests (C4 in Pass 1, skipped by choice). · **Where:** new `action.yml`. · **Suggested fix:** a
  composite action that runs `wirehouse build --against` on the base branch's map and comments the
  Changes section.
- **Date:** 2026-10-18 · **What:** Change review straight from git (`--against main` without a saved
  map). · **Where:** `wirehouse/cli.py`, `wirehouse/delta.py`. · **Suggested fix:** check the ref out
  into a temporary worktree, scan it, and compare.
- **Date:** 2026-10-18 · **What:** Mapping code that describes technologies (signature tables, fixtures,
  docs) draws edges to those technologies: mapping Wirehouse itself says `signatures.py` "uses
  PostgreSQL". · **Where:** `wirehouse/build.py` code-pattern matching, `wirehouse/signatures.py`.
  · **Suggested fix:** skip string literals inside large constant tables, or require an import or call
  next to the pattern.
- **Date:** 2026-10-18 · **What:** Some EXTRACTED edges carry no evidence (Prisma datasource, Kubernetes
  image `provisions`, ORM edges). · **Where:** `wirehouse/build.py`. · **Suggested fix:** attach the
  manifest or schema line that produced each edge, or mark it INFERRED.
- **Date:** 2026-10-18 · **What:** Python units count dev and optional dependencies when classifying a
  unit; JavaScript units do not. · **Where:** `wirehouse/detectors/units.py` `_classify`.
  · **Suggested fix:** ignore `Dep.dev` entries the same way for both.
- **Date:** 2026-10-18 · **What:** On the night shift most draw calls are glow-mode edge lines and label
  sprites, one each. · **Where:** `wirehouse/render/app.js` `box()` and `label()`. · **Suggested fix:**
  merge a room's edge lines into one `LineSegments`, and put labels in a texture atlas drawn as
  instanced quads.

## Low findings from the Pass 2 audit

- **Date:** 2026-10-18 · **What:** In `.gitignore` handling, `*` crosses `/` (fnmatch) and `**/` misses
  the zero-folder case inside a pattern (`a/**/b` should match `a/b`). · **Where:** `wirehouse/scan.py`
  `_rule_matches`. · **Suggested fix:** translate patterns to a regex where `*` is `[^/]*` and `**/` is
  `(?:.*/)?`.
- **Date:** 2026-10-18 · **What:** A .NET block can say "declares dependency (no import found)" while an
  Entity Framework Core edge from its code exists. · **Where:** `wirehouse/build.py` around the
  dependency-only edges (about lines 649-665 before Pass 2). · **Suggested fix:** drop the
  "no import found" label when any code edge between the same pair exists.
- **Date:** 2026-10-18 · **What:** An `--against` file that is JSON with `nodes` but no `edges` prints a
  traceback (`KeyError: 'edges'`). · **Where:** `wirehouse/cli.py` `_load_map`, `wirehouse/delta.py`.
  · **Suggested fix:** require `edges` to be a list in `_load_map`, with the same clear error.
- **Date:** 2026-10-18 · **What:** `wirehouse export` prefers `archmap.json` even when
  `archmap.raw.json` is newer (a scan after the last render). · **Where:** `wirehouse/cli.py`
  `cmd_export`. · **Suggested fix:** compare modification times and say which file was used.
- **Date:** 2026-10-18 · **What:** `_join` drops a leading `..`, so a compose `build: ../x` resolves
  inside the project; a Dockerfile named by compose skips the gitignore check. · **Where:**
  `wirehouse/detectors/infra.py` `_join`, `detect_infra`. · **Suggested fix:** return None for paths
  that leave the project, and run named Dockerfiles through the scan's ignore rules (reads are already
  confined to the project by `read_inside`).
- **Date:** 2026-10-18 · **What:** Root units read "in `./`"; .NET ProjectReference evidence has no line;
  `wirehouse --help` lists subcommands without help text. · **Where:** `wirehouse/build.py`
  descriptions, `wirehouse/detectors/units.py`, `wirehouse/cli.py`. · **Suggested fix:** say "at the
  project root", record the line of each `<ProjectReference>`, add `help=` to every subparser.
- **Date:** 2026-10-18 · **What:** Markdown export `_cell` escapes only `|`, so a name with `<`, `>`, `[`,
  `]`, `(`, `)`, backticks, `*` or `_` can change the table's formatting. · **Where:**
  `wirehouse/export.py` `_cell`. · **Suggested fix:** backslash-escape those characters too.
- **Date:** 2026-10-18 · **What:** The schema diagram is `aria-modal` but Tab can leave it, and closing it
  does not return focus to the button that opened it. · **Where:** `wirehouse/render/app.js` schema
  section (`openErd`). · **Suggested fix:** trap Tab like the welcome card does, and remember and
  restore the opener.
- **Date:** 2026-10-18 · **What:** The README snippet in the brand kit points at `docs/brand/readme-*.svg`,
  but the files are in `docs/brand/readme/`. · **Where:** `docs/brand/snippets/README-snippet.md`.
  · **Suggested fix:** add the `readme/` folder to each path.

Fixed in Pass 2 although they were Low, because they were trivial and in files already being changed:
`setuptools>=77` for the PEP 639 license fields, `go` in the language names, the dead `L0` line index
and second `_balanced` docstring, and control characters in output (now stripped by `redact.scrub`).
