<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/readme/readme-banner-dark.svg">
    <img alt="Wirehouse: walk through your codebase like a warehouse." src="docs/brand/readme/readme-banner-light.svg" width="100%">
  </picture>
</p>

<p align="center">
  Wirehouse turns a repository into a 3D warehouse you can walk around: services are shipping
  containers, databases are silos, auth is a security gate, and every pipe is a real connection
  found in the code. Trace where a request goes, take a guided tour, and share it all as
  <b>one offline HTML file</b>. Built for your agents.
</p>

<p align="center">
  <a href="https://github.com/__OWNER__/wirehouse/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/__OWNER__/wirehouse/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-22c55e"></a>
  <img alt="One offline HTML file" src="https://img.shields.io/badge/output-one%20offline%20HTML%20file-F2C230">
  <img alt="Built for your agents" src="https://img.shields.io/badge/built%20for-your%20agents-39C0F5">
</p>

<p align="center">
  <a href="https://__OWNER__.github.io/wirehouse/demo/"><b>Try the live demo</b></a> ·
  <a href="#quick-start"><b>Quick start</b></a> ·
  <a href="#how-to-use"><b>How to use</b></a> ·
  <a href="#how-it-works"><b>How it works</b></a> ·
  <a href="CONTRIBUTING.md"><b>Contributing</b></a>
</p>

<p align="center">
  <img src="docs/assets/demo.webp" alt="Walking through the warehouse of fastapi/full-stack-fastapi-template: tracing what the backend reaches, walking a request from the user to PostgreSQL, entering the backend, the schema diagram, the floor plan and the Clipboard of tours and quests" width="900">
  <br>
  <sub>The warehouse of <a href="https://github.com/fastapi/full-stack-fastapi-template">fastapi/full-stack-fastapi-template</a>, described by a coding agent. <a href="https://__OWNER__.github.io/wirehouse/demo/">Open it yourself</a> (one 1 MB HTML file) · <a href="docs/assets/demo.mp4">MP4 with full-speed walking</a>.</sub>
</p>

<img src="docs/brand/readme/readme-divider-hazard.svg" alt="" width="100%">

## Why

Architecture diagrams go stale the day they are drawn, and reading a new codebase file by file
tells you *what* is there but not *how it fits together*. Wirehouse builds the map from the code
every time, and makes exploring it feel like walking a well-run warehouse instead of reading a
wall of boxes and arrows:

- **New teammate?** Take the guided tour, then go find things on your own with quests.
- **Reviewing a change?** Trace what a service reaches before you touch it.
- **Explaining the system?** Walk the route from the user to the database and share the link.

Everything you see comes from evidence: each pipe lists the file and line it was found in, and
anything your agent adds has to cite real code or it is left out.

## What you can do

<table>
<tr>
<td width="50%"><img src="docs/assets/screenshot-trace.png" alt="Downstream trace from the backend, with rings and hop counts"><br><b>Trace</b> everything a block leads to, or everything that leads to it, with hop counts. File precise.</td>
<td width="50%"><img src="docs/assets/screenshot-route.png" alt="The worker walking the route from Users to PostgreSQL"><br><b>Walk a route</b> from A to B, hop by hop, with the code behind each step.</td>
</tr>
<tr>
<td><img src="docs/assets/screenshot-room.png" alt="Inside the backend: folders as crates, files on shelving racks"><br><b>Walk into any block.</b> Folders are crates, files sit on racks, connections leave through wall ports.</td>
<td><img src="docs/assets/screenshot-tour.png" alt="A guided tour stop"><br><b>Guided tours and quests</b> written by your agent from the real code, with your progress kept in the browser.</td>
</tr>
<tr>
<td><img src="docs/assets/screenshot-schema.png" alt="Schema diagram of the PostgreSQL database"><br><b>Database rooms</b> with columns, keys and a schema diagram.</td>
<td><img src="docs/assets/screenshot-plan.png" alt="2D floor plan"><br><b>Floor plan</b> in 2D for a quick overview, fully keyboard accessible.</td>
</tr>
</table>

Also: night and day shift lighting, search that walks you to anything, links that reopen the exact
view, commit-pinned links to GitHub, GitLab, Bitbucket and Azure DevOps, and pictures or
1200 × 630 share cards of what you are looking at.

## Quick start

Requires Python 3.11+.

```bash
pip install "git+https://github.com/__OWNER__/wirehouse"
wirehouse install          # adds the wirehouse skill to the coding agents on this machine
```

Then, in your coding agent, inside any project:

```text
/wirehouse
```

(Or just ask: *"map this project with wirehouse"*.) The agent scans the project, reads the code to
describe every block and connection, writes tours and quests, and opens
`wirehouse-out/wirehouse.html`.

### Works with your agent

Wirehouse ships as a skill in the open `SKILL.md` format. `wirehouse install` writes it to the
shared `~/.agents/skills` folder and to the skills folder of every agent it finds in your home
folder:

| Agent | Skill folder |
|-------|--------------|
| Codex and other agents that read the shared folder | `~/.agents/skills` (always written) |
| Claude Code | `~/.claude/skills` |
| Cursor | `~/.cursor/skills` |
| OpenCode | `~/.config/opencode/skills` |
| Gemini CLI | `~/.gemini/skills` |
| Antigravity | `~/.gemini/antigravity/skills` |
| GitHub Copilot | `~/.copilot/skills` |

Pick agents with `wirehouse install --agent cursor --agent opencode`, add any other skills folder
with `--dir <folder>`, or run `wirehouse install --print` and paste the instructions into an agent
that has no skills support. Restart the agent if it was already open.

**No agent?** The CLI draws the same map with rule-based descriptions and a starter tour:

```bash
wirehouse build path/to/project --open
```

## How to use

### 1. Make a map

| Command | What it does |
|---------|--------------|
| `/wirehouse [path]` | In your agent: scan, describe, render and open. Add `--quick` to skip the descriptions. |
| `wirehouse build <path> [--open]` | Scan and render in one go, reusing any descriptions from earlier runs. |
| `wirehouse scan <path>` | Detect structure only: writes `archmap.raw.json` and the agent's worklist `enrich-brief.md`. |
| `wirehouse render <path> [--open]` | Merge `enrichment.json` and write `wirehouse.html`. |
| `--share` | (build, render) Leave out local paths before you publish the page. |
| `-o <folder>` | Write somewhere other than `<path>/wirehouse-out/`. |
| `wirehouse install` | Add the skill to your agents (`--agent`, `--dir`, `--print`; see above). |

Descriptions are cached by a hash of the code they describe, so re-running `/wirehouse` after a
change only asks the agent about what changed. Add `wirehouse-out/` to your `.gitignore`.

### 2. Walk around

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/readme/readme-how-it-maps-dark.svg">
  <img alt="Web apps are kiosks, services are shipping containers, databases are silos, queues are conveyor belts, auth is a security gate, third-party APIs are the loading dock." src="docs/brand/readme/readme-how-it-maps-light.svg" width="100%">
</picture>

The floor is laid out from the entrance to the back: **Clients**, **Gateway and auth** (shown even
when empty, because "no auth found" is worth knowing), **Services**, **Data**, and the
**Loading dock** for third-party providers. **Ops** (CI/CD, Terraform, Kubernetes, hosting,
observability) runs down the left side.

| Do this | To |
|---------|----|
| `W` `A` `S` `D` / arrows (`Shift` to run, `Space` to jump) | walk the worker around |
| Drag, scroll | look around, zoom |
| Click a block, rack item or pipe | open its inventory tag: description, code locations, endpoints, connections |
| Click it again, or the floor, or the minimap | walk there |
| `E` / `Q` | walk into the block in front of you / step back out |
| `/` | search everything and walk straight to it |
| `P` | switch between walking and the 2D floor plan |
| `T` | switch between night shift and day shift |
| `R` | route from the inspected block: pick an end point and walk it |
| `C` | the Clipboard: tours and quests |
| `X` | export a picture or a share card |
| `Space` `,` `.` | during a tour or route: play or pause, back, next |
| `Esc` | back out one step: close, pause, stop, clear |
| `?` | show the controls |

Pipe colors: calls (blue), reads and writes (amber), sign-in (pink), messages (red), code imports
(grey), provisioning (green), foreign keys (tan). The **pipe key** in the bottom-left corner is
also a filter: switch a kind off to hide it everywhere, traces included. Switching off imports
gives you runtime-only reach.

### 3. Trace and route

Inspect a block and press **Downstream** (where it leads) or **Upstream** (what leads to it).
Rings and badges mark every place it reaches, with the number of hops, and the trace bar lists
them so you can jump to any of them.

- Traces follow **recorded connections only**: what the scanner found plus what your agent added
  with evidence. That is the map's reach, not a promise about runtime impact. Start-up order
  (`depends_on`) and provisioning are left out, because they are not traffic.
- They are **file precise**: a trace from `web/lib/payments.ts` follows that file's connections,
  not the whole frontend's. A connection that points at a whole block (an env var naming a
  service) reaches everything inside it.
- **Hops count block boundaries**, so a chain of imports inside one service does not make
  something look further away.

Press **R** (or *Route to…*) and pick an end point: Wirehouse finds the shortest recorded path and
the worker walks it stop by stop, showing the file and line behind each hop. If the blocks connect
but the files do not line up, the route says it is **loose**.

### 4. Tours and quests

Open the **Clipboard** (`C`). **Tours** walk the worker through the system in the order things
really happen ("What happens when you log in"). **Quests** send you looking ("Where are passwords
hashed?") and tick off when you inspect the answer. Progress stays in your browser.

Your agent writes them during `/wirehouse`. You can add your own to
`wirehouse-out/enrichment.json`:

```json
{
  "tours": [
    {"id": "login", "title": "What happens when you log in", "stops": [
      {"node": "unit:js:frontend", "text": "The login form posts the email and password.",
       "evidence": [{"file": "frontend/src/routes/login.tsx", "line": 42}]}
    ]},
    {"id": "request", "title": "Follow a request to the database", "route": ["actor:users", "res:postgres"]}
  ],
  "quests": [
    {"question": "Where are passwords hashed?", "answer": ["file:backend/app/core/security.py"],
     "hint": "Look in the backend's core folder.", "explain": "...",
     "evidence": [{"file": "backend/app/core/security.py", "line": 20}]}
  ]
}
```

`wirehouse render` checks every node id, file and line, and prints one line per problem:

```text
error [evidence/line-out-of-range] tours[login].stops[0]: `frontend/src/routes/login.tsx` has 30 lines, cited line 42 -> open the file and cite the line the claim is based on
```

Invalid parts are left out of the page, never guessed. Without enrichment, Wirehouse makes a
main-floor tour, a follow-a-request route and a few quests from what it found.

### 5. Database rooms

Walk into a database to see its tables on racks, with foreign keys as pipes between them. The
inventory tag lists each table's columns and keys, and **Open schema diagram** draws them all.
Columns are read from SQL migrations, Prisma, SQLAlchemy, SQLModel, Django, Drizzle and TypeORM.

### 6. Share it

- The address bar always describes the view (`#room=`, `#focus=`, `#trace=down~<id>`,
  `#route=<from>~<to>&stop=2`, `#tour=<id>&stop=3`, `#plan=1`), and **Copy link** copies it.
- Code links go to your code host **at the exact commit that was scanned**, so they keep working
  when the file is shared. Files with uncommitted changes are marked.
- **Export** (`X`) saves or copies a picture of the view, or a 1200 × 630 share card describing the
  route, trace or tour on screen.
- The page is a single file with everything inlined. Email it, attach it to a pull request, or
  host it anywhere static. Use `--share` so it does not include your local folder paths.

## How it works

```mermaid
flowchart LR
  A[scan<br/>honours .gitignore] --> B[per-file facts<br/>imports · env · URLs · endpoints · tables]
  B --> C[units<br/>apps and packages]
  C --> D[infra<br/>compose · Docker · Terraform · K8s · CI]
  D --> E[archmap.raw.json]
  E --> F{{your agent reads the code<br/>enrichment.json}}
  F --> G[checks<br/>ids · files · lines · secrets]
  G --> H[wirehouse.html<br/>one offline file]
```

1. **Scan** walks the repo, honours `.gitignore`, skips build output and dependency folders, and
   never opens real `.env` files (templates like `.env.example` are fine).
2. **Detectors** find imports, env var reads, URLs, HTTP endpoints (FastAPI, Flask, Django, Express,
   NestJS, Next.js, ASP.NET), tables and columns, apps and packages, and infrastructure.
3. **Build** maps about 115 technology signatures to blocks. Env values wire things together:
   `API_URL=http://api:8000` links the code that reads it to the `api` service, and
   `DATABASE_URL=postgresql://...@db/...` links it to the Postgres container. Connections are kept
   at file level and rolled up to whatever level you are looking at.
4. **Enrichment**: your agent reads the code and writes descriptions, connection notes, corrections
   (each with file:line evidence), tours and quests. Entries carry a content hash, so later runs only
   ask about code that changed.
5. **Checks**: every citation is verified against the scan, and secret-looking text is removed.
6. **Render** inlines Three.js, the fonts, the data and the app into one HTML file of about 1 MB.

| Output in `wirehouse-out/` | What it is |
|------|------------|
| `archmap.raw.json` | What the rules found |
| `enrich-brief.md` | The agent's worklist |
| `enrichment.json` | Descriptions, corrections, tours and quests, kept between runs |
| `archmap.json` | The merged data behind the page |
| `wirehouse.html` | The warehouse |

## What it detects

- **JavaScript / TypeScript**: Next.js, React, Vue, Svelte, Nuxt, Remix, Astro, Angular, Express,
  Fastify, NestJS, Hono, Electron, React Native; tsconfig path aliases.
- **Python**: FastAPI, Flask, Django, Starlette, Litestar, Celery, RQ, Streamlit and more.
- **.NET**: ASP.NET Core, Worker services, Azure Functions, Blazor, WPF, MAUI; EF Core and
  connection strings.
- **Data**: Postgres, MySQL, SQL Server, SQLite, MongoDB, Redis, queues, object storage and search,
  with tables and columns from SQL, Prisma, SQLAlchemy, SQLModel, Django, Drizzle and TypeORM.
- **Infra**: docker-compose (including override files), Dockerfiles, Terraform (AWS, Azure, GCP),
  Kubernetes, GitHub Actions and other CI, Nginx, Caddy, Traefik, Vercel, Netlify, Fly.
- **Third parties**: Stripe, Clerk, Auth0, Supabase, Firebase, OpenAI, Anthropic, Sentry and about
  a hundred more.

Missing your stack? [Tell us where the map is wrong](https://github.com/__OWNER__/wirehouse/issues/new?template=wrong_map.yml).

## Privacy and safety

- Runs locally. No network requests, no telemetry, and the page loads nothing from the network.
- Never reads real `.env` files. Env values, passwords, connection strings, column defaults and
  credentials inside git remotes are never written to the output.
- Text written by the agent is checked for credential-looking strings, which are removed.

See [SECURITY.md](SECURITY.md) to report a problem.

## Limits

- Detection is regex based. It favours precision over recall: it would rather miss a connection
  than draw a wrong one, and the agent's pass adds what it misses (with evidence).
- Wiring that only exists at runtime (service discovery, URLs built on the fly, DI containers) is
  found only when it shows up in env vars, config or literals, so traces cannot see it either.
- Very large rooms (hundreds of files in one folder) render fine but get dense; search is the
  fastest way around.
- The page needs WebGL for the 3D view; the floor plan works without it.

## Roadmap

- **Change review**: compare two scans (or a branch against `main`) and walk the differences.
- **History**: a timeline of how each block changed, from git.
- More stacks: Go, Java/Kotlin (Spring), Ruby on Rails, PHP (Laravel).
- Bigger repos: instanced rendering for rooms with thousands of files.

Ideas welcome in [Discussions](https://github.com/__OWNER__/wirehouse/discussions).

## Contributing

Contributions are welcome, and the most useful one is a project where the map is wrong. See
[CONTRIBUTING.md](CONTRIBUTING.md) for setup, the ground rules and where things live, and please
follow the [Code of Conduct](CODE_OF_CONDUCT.md).

```bash
pip install -e ".[dev]" && python -m pytest
```

## Acknowledgements

- [Three.js](https://threejs.org) (MIT) renders the warehouse, and the
  [Barlow](https://github.com/jpt/barlow) typeface (SIL Open Font License) labels it. Both are
  vendored in `wirehouse/render/vendor/` with their licenses.
- Trace, route, links-into-a-view and evidence-first validation were inspired by
  [Archify](https://github.com/tt-a1i/archify) (MIT) and its "truth before spectacle" principle.
- The demo maps [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) (MIT).

## License

[MIT](LICENSE) © __AUTHOR__
