# Contributing to Wirehouse

Thanks for helping. Wirehouse is small on purpose: one Python package with a single runtime
dependency, and one offline HTML page. Contributions that keep it that way are the easiest to merge.

## The fastest way to help: a wrong map

The scanner is regex based, so the most valuable report is a project where the map is wrong: a
missing database, a connection that is not real, a service in the wrong zone. Open a
**"The map is wrong"** issue with:

- the stack (framework, ORM, how it is deployed),
- what Wirehouse drew and what is really there,
- a minimal snippet (or a public repo + commit) that reproduces it.

Fixes for these come with a test that builds a tiny repo in a temp folder (see
`test_template_style_repo` in `tests/test_wirehouse.py` for the pattern).

## Setup

```bash
git clone https://github.com/creyes-git/wirehouse
cd wirehouse
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest
```

Viewer (browser) tests are optional and need Playwright plus Chrome, Edge or Playwright's Chromium:

```bash
pip install -e ".[browser]"
python -m playwright install chromium   # skip if Chrome or Edge is installed
python -m pytest tests/test_viewer.py
```

Try your change on a real project:

```bash
wirehouse build path/to/project --open
```

## Where things live

| Path | What it does |
|------|--------------|
| `wirehouse/scan.py` | Walks the repo, honours `.gitignore`, never reads real `.env` files |
| `wirehouse/detectors/` | Per-file facts, units (apps and packages), infra, table columns |
| `wirehouse/signatures.py` | About 115 technologies: imports, packages, URLs, images to blocks |
| `wirehouse/build.py` | Turns facts into the archmap (blocks, rooms, connections) |
| `wirehouse/enrich.py`, `guide.py` | The agent's brief, merging enrichment, checking tours and citations |
| `wirehouse/render/` | The viewer: `template.html`, `app.css`, `app.js` (Three.js r149, vendored) |
| `wirehouse/skill/SKILL.md` | The `/wirehouse` instructions the agent follows |

`AGENTS.md` has the architecture notes and conventions in more detail.

## Ground rules

- **Truth before spectacle.** Anything the page lights up, counts or narrates must come from a
  recorded connection or checked enrichment, and must say so when it is loose or inferred.
  Prefer missing a connection over drawing a wrong one.
- **Secrets never reach the output.** Env values, passwords, connection strings and column
  defaults are not stored. `test_secrets_never_leak` must keep passing.
- **One offline file.** No network loads, no CDNs, exactly three `</script>` tags
  (`test_html_is_self_contained`). Links out are plain `<a href>`.
- **Small dependency footprint.** The runtime needs `pyyaml` only. Ask before adding anything.
- **Accessible by default.** Keyboard reachable, visible focus, no meaning carried by color alone,
  `prefers-reduced-motion` respected.

## Adding a technology

Most new stacks are a line in `wirehouse/signatures.py` (an import, a package name, a URL host or a
docker image mapped to a block kind). Add a case to a test fixture that proves it is detected and
that a test-only import does not create a block.

## Changing the viewer

`app.js` is one file in sections. Later sections plug in through hook lists declared near the top
(`BUILD_HOOKS`, `SELECT_HOOKS`, `HASH_PARTS`, `PANEL_ACTS`, `KEYS`, `onEscape`). Run
`node --check wirehouse/render/app.js` and the browser tests after a change, and attach a
screenshot or short clip to the pull request.

## Pull requests

- One topic per pull request, with a test for behaviour changes.
- Update `CHANGELOG.md` under **Unreleased**.
- Keep commit messages in the imperative ("Add Go module detection").

By contributing you agree that your work is released under the [MIT License](LICENSE) and that you
will follow the [Code of Conduct](CODE_OF_CONDUCT.md).
