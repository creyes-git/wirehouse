# Changelog

All notable changes to Wirehouse are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **TODO.md** (2026-10-17)
  - Summary: Lists deferred work, starting with creating the GitHub repository and the first push.
  - Why: the repository is not created yet, so the published links do not resolve until then.
- **`wirehouse install` reaches any coding agent** (2026-10-16)
  - Summary: The skill is written to the shared `~/.agents/skills` folder and to the skills folder of
    every agent found in the home folder (Claude Code, Codex, Cursor, OpenCode, Gemini CLI,
    Antigravity, GitHub Copilot). `--agent` picks agents, `--dir` adds any other folder, `--print`
    prints the instructions for agents without skills support.
  - Why: Wirehouse is built for any agent, not one vendor's; installing only for one left everyone
    else to copy files by hand.

### Changed
- **Repository links and author filled in** (2026-10-17)
  - Summary: Links now point at `github.com/creyes-git/wirehouse` and its GitHub Pages demo; the
    license and package name Carlos Reyes as the author.
  - Why: the placeholders were kept until the GitHub account was known, so the README, badges,
    install command and issue links work once the repository is published.

### Security
- **One last redaction pass over everything written** (2026-10-18)
  - Summary: New `wirehouse/redact.py` scrubs every key and value of the archmap for credential-looking
    text before `archmap.raw.json`, `archmap.json` and `wirehouse.html` are written; with `--share` it
    also cuts the project folder and home folders (`C:\Users\<name>`, `/home/<name>`) out of every string.
  - Why: secrets were checked field by field, so each new field was a new way to leak; three leaks of
    that kind were found in an audit (below).
- **SQLite and other file databases no longer leak their connection string** (2026-10-18)
  - Summary: A string like `Data Source=app.sqlite;Password=...` or `sqlite:///C:\Users\me\app.db` now
    names the block after the file only (`SQLite · app.sqlite`).
  - Why: the whole string, password and local folder included, became the block's id, name and
    description.
- **Connections the agent adds need real evidence** (2026-10-18)
  - Summary: An `add_edges` entry is drawn only when at least one of its citations points at a real file
    and line; otherwise it is left out with `edge/without-evidence` or `edge/unknown-endpoint`. Text and
    locations of `add_nodes`/`add_edges` are checked like tour text.
  - Why: these edges were drawn even when the check failed, and their descriptions and cited paths went
    into the page unchecked, so a secret or a local path written by the agent was published even with
    `--share`.
- **Problem messages no longer copy the agent's raw input** (2026-10-18)
  - Summary: Diagnostics name the entry instead of echoing its contents, and the separate `warnings`
    list is gone (unknown endpoints are diagnostics now). Render counts only the additions and removals
    it really applied.
  - Why: the messages are embedded in the page, so they carried whatever the agent wrote, and the
    counts reported no-op entries as changes.
- **Ignore local `.env` files** (2026-10-16)
  - Summary: `.gitignore` now excludes `.env` and `.env.*` (keeping `.env.example`).
  - Why: contributors who keep keys in a local `.env` while testing should never commit it by accident.

### Changed
- **Agent-neutral wording** (2026-10-16)
  - Summary: The README, docs, banner tagline ("Built for your agents"), skill and brief no longer
    name one agent; enrichment written by an agent is tagged `"source": "agent"`.
  - Why: the skill uses the open `SKILL.md` format and works with any agent that can read files
    and run commands.

## [0.2.0] - 2026-10-16

The first public release.

### Added
- **Trace mode.** Light up everything a block leads to (downstream) or everything that leads to it
  (upstream), at file precision, with hop counts. Pick two places and the worker walks the route
  hop by hop, showing the file and line behind each step.
- **Guided tours and quests** (the Clipboard). Your agent writes them during `/wirehouse`; Wirehouse
  makes a main-floor tour, a follow-a-request route and a few quests when none are written.
  Progress stays in the browser.
- **Checked citations.** Every tour stop, quest and added connection is checked against the scan
  (node ids, files, line ranges, secret-looking text). Problems are reported as
  `error [code] subject: message -> fix`; invalid parts are left out, never guessed.
- **Database rooms.** Columns, keys and a schema diagram for SQL DDL, Prisma, SQLAlchemy,
  SQLModel, Django, Drizzle and TypeORM. Foreign keys become pipes between tables.
- **Links into a view.** The URL restores the room, selection, trace, route, tour stop and floor
  plan. Source links go to GitHub, GitLab, Bitbucket or Azure DevOps at the scanned commit.
- **Export.** Save or copy a picture of the view, or a 1200 x 630 share card.
- `--share` for `build` and `render`: leaves out this machine's folder paths and the list of
  uncommitted files before you publish a page.
- Route tours are checked for a recorded path (`tour/no-recorded-path`); the brief documents node
  ids, table ids and the `kind` override.
- Pipe key doubles as a filter (and traces follow it); Escape backs out one step at a time.
- Optional browser tests (`tests/test_viewer.py`, `pip install -e ".[browser]"`).

### Changed
- The floor plan toggle moved from `Tab` to `P`, so `Tab` moves through the page again.

### Fixed
- Provider URLs in data files no longer put empty blocks on the floor.
- Compose services split across `compose.yml` and `compose.override.yml` are merged; a
  Dockerfile's folder picks the app a service runs; Traefik labels route to services.
- `FRONTEND_HOST`-style settings are no longer drawn as calls; React Email packages are libraries.
- SQLModel tables are detected, with inherited fields and multi-line `Field(foreign_key=...)`.
- Traces and routes no longer follow start-up order (`depends_on`) or provisioning, which are not
  traffic; compose services that only run tests do not describe how an app runs.
- Text the agent writes in descriptions and connection notes is checked for credentials too.
- Room changes during the fade are queued instead of dropped; reduced motion stops particles.
- Space, Enter, arrows and Backspace keep their normal meaning on buttons and links.

## [0.1.0] - 2026-10-10

- First working version: scan, agent enrichment, the 3D warehouse and the floor plan.

[Unreleased]: https://github.com/creyes-git/wirehouse/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/creyes-git/wirehouse/releases/tag/v0.2.0
