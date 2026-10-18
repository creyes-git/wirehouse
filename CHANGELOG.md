# Changelog

All notable changes to Wirehouse are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **IMPROVEMENT_LOG.md** (2026-10-18)
  - Summary: Records each improvement pass: the audit, the menu offered, what was done, deferred and
    rejected.
  - Why: later passes build on earlier ones instead of repeating them.
- **Change review with `--against`** (2026-10-18)
  - Summary: `wirehouse build` and `render` take `--against <earlier archmap.json>`. The page gets a
    **Changes** panel (`V`) listing new, changed and removed blocks, connections and files, and **Show on
    the floor** badges them in every room and lights the new pipes (`#changes=1` in links). `wirehouse
    export` adds a Changes section.
  - Why: "what did this change touch?" is a core review question, and change review was the first
    roadmap item; blocks count as changed only when their code did, so the answer stays evidence-based.
- **Go support** (2026-10-18)
  - Summary: Each `go.mod` becomes a block, classified by its framework (Gin, Echo, chi, Fiber,
    gorilla/mux, gRPC, `net/http`, cobra). Go files get imports (internal packages link to the package's
    files), `os.Getenv` reads, routes (including Go 1.22 `"GET /path"`), symbols and the package comment.
    About thirty drivers and SDKs map to blocks (pgx, go-redis, the AWS SDK, stripe-go, ...); `// indirect`
    requirements do not.
  - Why: Go led the roadmap's "more stacks" list, and Go services did not show up on the map at all.
- **`wirehouse export`: the map as Markdown and Mermaid** (2026-10-18)
  - Summary: Writes `architecture.md` next to the page: a Mermaid flowchart of the top-level blocks by
    zone, a list of blocks, and a table of every connection with its file and line (commit-pinned links
    when the repository has a known code host). `--format mermaid` writes only the diagram.
  - Why: text can go into a README or a pull request and shows up in diffs, which a 1 MB HTML file
    cannot; it follows the same "recorded connections only" rule as the page.
- **Checks in the page and `--strict`** (2026-10-18)
  - Summary: When the checks left something out (an unknown node in a tour, an added connection with no
    evidence, a wrongly shaped entry), a **Checks** button in the top bar lists each problem with its fix.
    `wirehouse render --strict` (and `build --strict`) still writes the page but exits with an error.
  - Why: the diagnostics were computed and embedded but never shown, so a reader could not tell a missing
    part from one that was never written, and CI or an agent had no exit code to stop on.
- **A "nasty repository" test** (2026-10-18)
  - Summary: `tests/test_nasty_repo.py` maps one repository full of past failure cases (secrets in every
    format, BOM files, oddly shaped configs, comment URLs, a 20,000-line file, malformed enrichment) with
    `--share`, and checks that it finishes quickly and that no secret or local path reaches any output.
  - Why: the focused tests guard each bug; this one guards the invariants together, so a new field or
    parser cannot quietly reopen a leak.
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
- **Viewer tests close their pages** (2026-10-18)
  - Summary: An autouse fixture closes every page a viewer test opened.
  - Why: open WebGL pages kept rendering in the background and later tests timed out at random; the
    suite now runs in about 15 seconds instead of over two minutes.
- **Repository links and author filled in** (2026-10-17)
  - Summary: Links now point at `github.com/creyes-git/wirehouse` and its GitHub Pages demo; the
    license and package name Carlos Reyes as the author.
  - Why: the placeholders were kept until the GitHub account was known, so the README, badges,
    install command and issue links work once the repository is published.
- **Agent-neutral wording** (2026-10-16)
  - Summary: The README, docs, banner tagline ("Built for your agents"), skill and brief no longer
    name one agent; enrichment written by an agent is tagged `"source": "agent"`.
  - Why: the skill uses the open `SKILL.md` format and works with any agent that can read files
    and run commands.

### Removed
- **Two leftovers in the detectors** (2026-10-18)
  - Summary: Go files reuse the line index every other language uses instead of building a second one,
    and `schema._balanced` keeps one docstring instead of two.
  - Why: found in the Pass 2 audit; duplicate code makes readers look for a difference that is not there.
- **Unused scanner code** (2026-10-18)
  - Summary: Dropped `Builder.unit_node_id`, a loop that did nothing, the never-read compose `profiles`,
    Dockerfile `copies` and `Unit.implicit` fields, the unused `sln` config category and `.pyi` entry. The
    scan now reports how many files it skipped for size.
  - Why: found in the audit; fields nothing reads make the data model look richer than it is.
- **Unused viewer code** (2026-10-18)
  - Summary: Dropped `UNIT_KINDS`, `fontReady`, the unused port anchor, `makePipe`'s unused room argument
    and `bindPanel`'s ignored options; renamed locals that hid the `where()` helper; foreign keys get their
    own place in the pipe colour order.
  - Why: found in the same audit; dead code hides the real flow.
- **Text that looks like a page placeholder stays text** (2026-10-18)
  - Summary: The page is assembled in one pass over the template, so a description or project name that
    contains `/*__APP__*/` or `__FAVICON__` is shown as written.
  - Why: such text pulled the app or the stylesheet into the data or the title, and the page loaded
    without a viewer. That is likely when Wirehouse maps its own code.
- **`remove_edges` removes both directions** (2026-10-18)
  - Summary: Removing a top-level pair drops the connections and connection notes from A to B and from
    B to A, and render counts the removals that really happened.
  - Why: the brief, the skill and the docs promise "every connection between those blocks", but only one
    direction was removed.
- **Long JavaScript files scan in a blink** (2026-10-18)
  - Summary: The import pattern stops at `=` or `(`, so a file of many `export const` lines no longer
    makes it search to the end of the file each time.
  - Why: a 20,000-line file took about 90 seconds; it now takes well under one.
- **Frontends reach their API through `NEXT_PUBLIC_API_URL`** (2026-10-18)
  - Summary: `PUBLIC_..._URL` variables count as outgoing addresses again, and lines are judged by their
    code, not their strings, so `fetch('http://api:8000', {mode: 'cors'})` keeps its connection.
  - Why: the usual way a Next.js or Vite app points at its backend drew no pipe at all.
- **URLs in comments are not calls** (2026-10-18)
  - Summary: A URL on a commented line (`#`, `//`, `/*`, `*`, `--`) is skipped, and the word `api` inside
    the URL itself no longer makes the line look like a request.
  - Why: `# see https://api.openai.com/...` drew a "found in code" connection, against truth before
    spectacle.
- **Smaller detector mistakes** (2026-10-18)
  - Summary: `domain.py` is not taken for a CLI entry point; `setup.cfg` dependencies are read and
    `setup.py` reads only `install_requires`; `FROM --platform=...` finds the real base image; an
    apostrophe in a SQL or Prisma comment keeps the table's columns; a folder of only SQL or Prisma
    files is a "Database schema", not a Python package; "Deploys to" matches whole words only (no
    "Render" from `test_renderer.py`); Nuxt 4 `app/pages` are found; and `user:pass@` in a URL is skipped
    so the host is right and the password is never kept.
  - Why: each one put a wrong label, a wrong connection or a missing block on the map.
- **`.gitignore` is followed the way git follows it** (2026-10-18)
  - Summary: `!pattern` re-includes files, `.gitignore` files in subfolders apply below them, `**/name`
    also matches at the top, and ignored config files (compose overrides, `appsettings.Development.json`,
    env templates) are no longer read.
  - Why: only source files were checked, so ignored config files still fed the map, and `.env*` with
    `!.env.example` dropped the template the map needs.
- **Odd config files no longer stop the scan** (2026-10-18)
  - Summary: A `package.json`, compose file, workflow, `tsconfig.json`, `appsettings.json` or
    `pyproject.toml` with an unexpected shape (a list where an object belongs, a string for
    `environment`) is read as far as it makes sense instead of raising.
  - Why: one odd fixture file anywhere in a repository crashed the whole scan (11 cases found).
- **Files with a byte-order mark are read** (2026-10-18)
  - Summary: Source and config files, `enrichment.json` and `archmap.raw.json` are decoded as UTF-8 with
    an optional BOM.
  - Why: Visual Studio and Windows PowerShell write one, so a Next.js app was taken for a library and an
    agent's `enrichment.json` was rejected as invalid JSON.
- **Malformed enrichment is reported, not a crash** (2026-10-18)
  - Summary: Entries of the wrong type (a string where an object belongs, `"answer": 5`, a non-text
    `name`, `"line": Infinity`) are left out with `error [enrichment/wrong-shape] ...`, a bare string link
    note is accepted as its description, and an enrichment file that is not an object gets a clear error.
    An unknown `layer` falls back to the kind's zone.
  - Why: the agent got a Python traceback instead of the one-line problem report it is told to fix.
- **Git details are checked more carefully** (2026-10-18)
  - Summary: SHA-256 repositories get code links, the scan turns off `core.fsmonitor` (a command a
    checkout's config can name), and when git cannot list every changed file the page says links may show
    older code. A corrupt `archmap.raw.json` gets a clear error, and citations are checked against the
    project folder even when the raw map has no root.
  - Why: these gaps silently dropped links, marked changed files as clean, or ran repository-configured
    commands during a scan.

### Fixed
- **Kubernetes files with odd `metadata` are read** (2026-10-18)
  - Summary: A manifest whose `metadata` is not a mapping (`metadata: [1, 2]`) is named after its kind
    instead of stopping the scan.
  - Why: one such file anywhere in a repository crashed the whole build with an `AttributeError`.
- **Hostile files no longer stall the scan** (2026-10-18)
  - Summary: The C# and Go doc-comment readers go line by line, and the Go import block, FastAPI and
    Flask router prefix, TypeORM entity and column, SQL `CREATE TABLE` body, `go.mod` require and URL
    scheme patterns are anchored or bounded. Each case now scans a 200 KB file in well under a second.
  - Why: one file could hold the scan for minutes: 200 KB of `///` lines took 174 s, 80 KB of `//` lines
    29 s, 390 KB of `import (` lines 94 s and of `CREATE TABLE ` 106 s.
- **The minimap keeps its size on scaled displays** (2026-10-18)
  - Summary: At 125% or 200% display scaling the minimap grew with every redraw until it covered the view;
    it now has a fixed size, and the 3D view also follows browser zoom and moves to another monitor.
  - Why: most Windows laptops run at 125% or more, so the page became unusable there within seconds.
- **Phones and touch screens can drive the viewer** (2026-10-18)
  - Summary: Dragging on the 3D view turns the camera and a pinch zooms it, instead of the browser taking over
    the gesture; on a phone the tour, route and trace bar sits above the inventory panel, so Back, Next and Done
    can be tapped.
  - Why: a running tour could not be paused or stopped on a phone, and a cancelled touch left the camera
    turning with the mouse.
- **Tours no longer answer quests, and the hover follows the camera** (2026-10-18)
  - Summary: A tour stop counts as seen but no longer ticks off the quest it shows; the hover highlight and
    tooltip update while the camera moves under a still pointer; the walk prompt is only rewritten when its
    text changes.
  - Why: playing a tour could complete quests the reader never found, and the highlight stayed on a block the
    pointer had left.
- **Without WebGL the page opens on the floor plan** (2026-10-18)
  - Summary: When the browser cannot start WebGL, the viewer starts on the floor plan and the Walk view is
    switched off, so tours and routes step through it.
  - Why: tours and routes waited forever for a worker that could not walk.
- **A tour route from a block into its own contents is rejected** (2026-10-18)
  - Summary: `render` reports `tour/nested-route` for a tour whose route goes from a block to something inside
    it, and the viewer never plays the route that was on screen before under that tour's name.
  - Why: the page showed an unrelated route as the tour and counted the tour as walked.
- **Brand kit text uses plain punctuation** (2026-10-18)
  - Summary: The brand kit README, snippets and the titles of the README banners and social images use a
    colon where they had a long dash.
  - Why: the banner title is the tooltip and accessible name on the repository page, and the project avoids
    long dashes in everything it publishes.
- **The installed skill matches how Wirehouse was installed** (2026-10-18)
  - Summary: The "install from a source checkout" line is left out of the installed `SKILL.md` unless
    Wirehouse really runs from one; the skill now mentions `--share` before a page is published, and its
    JSON check accepts a byte-order mark.
  - Why: after a normal `pip install` the skill told agents to `pip install -e` the site-packages folder,
    and nothing reminded them to leave local paths out of shared pages.
- **A floor plan link opens on a fresh page** (2026-10-18)
  - Summary: Opening a link with `plan=1` in a new tab shows the floor plan instead of a blank page.
  - Why: the plan was drawn before the first room existed, which stopped the viewer from starting.
- **Upstream traces and routes claim only what the map records** (2026-10-18)
  - Summary: An upstream trace no longer counts every file inside a block that reaches the target as a
    whole, and a route between a block and something inside it is refused (it needs no connection)
    instead of being shown as "the shortest path through recorded connections". A link to such a route
    clears the old trace. Floor badges on a route are numbered like the bar's stops.
  - Why: upstream reach was larger than downstream reach for the same connections, and badge 2 could
    point at a different block than stop 2, against truth before spectacle.
- **The viewer frees GPU memory as you walk** (2026-10-18)
  - Summary: Day-shift shadow maps, the night grid, selection boxes and the old worker figure are freed
    when a room or theme changes, and label textures are kept for the last three rooms only.
  - Why: walking in and out of rooms kept adding GPU memory (each shadow map is 2048 x 2048), which can
    end in a lost WebGL context on large repositories.
- **Smaller viewer fixes** (2026-10-18)
  - Summary: Room changes asked for during the fade are queued instead of dropped (which could freeze the
    address bar); Tab moves through every button of the welcome card; nothing behind the schema diagram
    reacts to keys; `E` does nothing on the floor plan; exporting without WebGL pictures the floor plan
    and an empty picture is reported instead of failing; the trace bar follows the theme; corrupt saved
    progress starts fresh, and progress is kept per project (name and blocks), not per name.
  - Why: each one left a control dead, acted on something hidden, or threw an error.

### Security
- **Terminal escape codes are stripped from the output** (2026-10-18)
  - Summary: The last redaction pass removes control characters (except tab and newline) from every
    key and value, so the problems render prints and the files it writes carry none.
  - Why: an id written into `enrichment.json` is echoed in a diagnostic, and an escape sequence in it
    could rewrite the terminal title or clear the screen of whoever ran the build.
- **YAML alias bombs no longer hang the scan** (2026-10-18)
  - Summary: Compose, workflow and Kubernetes values are taken only when they are plain scalars (or
    lists of them), with a length cap, so nested `&anchor`/`*alias` lists are never expanded into text.
  - Why: an 11-line compose file with nine levels of aliases turned into hundreds of millions of items
    when `image` or `command` was converted to text, and the build never finished.
- **The scan stays inside the project folder** (2026-10-18)
  - Summary: Symlinks, Windows junctions, pipes and devices are skipped, every file read must resolve to
    a path inside the project, and config files (compose, workflows, `.gitignore`, `package.json`, ...)
    over 400 KB are not read, like source files.
  - Why: a linked folder or a `package.json -> ~/.npmrc` link let the scan read files outside the
    project, a named pipe called `x.py` hung it, and config reads had no size cap.
- **The scan never runs filters named by the repository's own git config** (2026-10-18)
  - Summary: When the checkout's `.git/config` (or a file it includes) defines a `filter.*` clean or
    smudge command, the scan skips `git status` and marks the list of changed files as incomplete. Filters
    from your own global or system config (Git LFS) are unaffected.
  - Why: `git status` runs those commands, so a `.git` folder that came with an archive or a copied
    project could run any program during a scan.
- **Enrichment that came with the repository is never applied silently** (2026-10-18)
  - Summary: When `wirehouse-out/enrichment.json` is tracked by git, render prints a warning and adds
    an `enrichment/from-repository` check. Every `remove_nodes` and `remove_edges` entry that removed
    something adds an `enrichment/removed-node` or `enrichment/removed-edge` check, so the Checks panel
    lists what the scan found and the page leaves out. The file is still applied.
  - Why: a cloned repository can ship its own enrichment, and `"remove_nodes": ["ext:evil-exfil.io"]`
    hid an exfiltration endpoint from the map without a trace.
- **`--share` keeps API routes and finds more home folders** (2026-10-18)
  - Summary: Only real home folders are cut: `C:\Users\<name>` and `C:\Documents and Settings\<name>`
    with a drive letter, and `/Users/<name>`, `/home/<name>`, `/var/home/<name>`, `/export/home/<name>`,
    `/mnt/c/Users/<name>` (WSL), `/c/Users/<name>` (Git Bash) and `/root` where a path starts. Endpoint
    paths are never touched, and a route after an HTTP method (`GET /home/dashboard`) is kept.
  - Why: the old pattern ignored case and matched anywhere, so `--share` turned routes such as
    `GET /users/{id}` and `/home/dashboard` into `~`, while WSL and Git Bash home folders went through.
- **More credential formats are redacted** (2026-10-18)
  - Summary: The last redaction pass now also catches GitHub `gho_`/`ghs_`/`ghu_`/`ghr_` tokens, AWS
    `ASIA` keys and secret access keys, JWTs, OpenAI and Anthropic `sk-` keys, Google `AIza` keys,
    GitLab, npm, SendGrid, Hugging Face and Twilio tokens, Slack and Discord webhook URLs, Azure
    `AccountKey=`, `SharedAccessKey=` and SAS `sig=` values, `Bearer`/`Basic` headers and quoted keys
    such as `"password": "..."`. Setting names match after an underscore too (`DB_PASSWORD=`,
    `client_secret=`).
  - Why: file docstrings, workflow names and endpoint paths reach the page, and these common formats
    went through even with `--share`.
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
