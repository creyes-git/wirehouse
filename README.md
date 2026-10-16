# Wirehouse

Walk through your project's architecture as a 3D warehouse.

Wirehouse scans a codebase and builds one offline HTML file where the system is a
building you can walk around. Each part of the system is a block on the warehouse floor:
frontends as kiosks, services as shipping containers, databases as silos, queues as
conveyor belts, auth as a security gate, third-party APIs parked at the loading dock.
Pipes with moving particles are the real connections found in the code. Walk into a
block and you are in a room holding its folders as crates and its files on shelving racks.
Connections that leave the room come in through ports on the walls.

It is a sibling of [graphify](../graphify): graphify maps files and symbols as a knowledge
graph; Wirehouse maps the architecture (what runs, what stores data, who talks to whom)
and lets you drill down to the code.

## Quick start

```bash
pip install -e .            # from this folder (needs Python 3.11+)
wirehouse install           # adds the /wirehouse skill to Claude Code
```

In Claude Code, run `/wirehouse` in any project (or `/wirehouse path/to/project`). Claude
scans the project, reads the code to write plain-language descriptions, and renders
`wirehouse-out/wirehouse.html`.

Without Claude, the CLI produces the same map with rule-based descriptions:

```bash
wirehouse build path/to/project --open
```

## In the warehouse

| Do this | To |
|---------|----|
| `W` `A` `S` `D` / arrows (`Shift` to run) | walk the worker around |
| Drag, scroll | look around, zoom |
| Click a block, rack item or pipe | open its inventory tag (description, code locations, endpoints, connections) |
| Click the floor or the minimap | walk there |
| `E` | walk into the block in front of you |
| `Q`, or walk out the door | go back to the room above |
| `/` | search everything and walk straight to it |
| `Tab` | switch between walking and the 2D floor plan |
| `T` | switch between night shift and day shift lighting |

The floor is laid out in zones from the entrance to the back: **Clients**,
**Gateway and auth** (shown even when empty, because "no auth found" is worth knowing),
**Services**, **Data**, and the **Loading dock** for external providers. **Ops** (CI/CD,
Terraform, Kubernetes, hosting, observability) runs down the left side.

Pipe colors: calls (blue), data reads and writes (amber), auth (pink), messages (red),
code imports (grey), provisioning (green). The pipe key is in the bottom-left corner.

## How it works

```
scan  ->  per-file facts  ->  units  ->  infra  ->  archmap.raw.json  ->  + enrichment.json  ->  wirehouse.html
```

1. **Scan** (`scan.py`): walks the repo, honouring `.gitignore` and skipping build output,
   dependency folders and large files. Real `.env` files are never read; only templates
   such as `.env.example`.
2. **Per-file facts** (`detectors/code.py`): imports, env var reads, URLs, top-level
   symbols, leading doc comments, HTTP endpoints (FastAPI, Flask, Django, Express, NestJS,
   Next.js app and pages routers, ASP.NET controllers and minimal APIs) and table definitions
   (SQLAlchemy, Django, Prisma, Drizzle, TypeORM, Mongoose, EF Core, SQL DDL).
3. **Units** (`detectors/units.py`): every `package.json`, Python manifest and `.csproj`
   becomes a unit, classified by framework (Next.js, FastAPI, ASP.NET Core, Celery and so on).
4. **Infra** (`detectors/infra.py`): docker-compose, Dockerfiles, env templates,
   `appsettings.json` connection strings, Terraform, Kubernetes manifests, CI workflows,
   gateway configs and hosting files.
5. **Build** (`build.py`): about 115 technology signatures (`signatures.py`) turn imports,
   dependencies, URLs, env values and docker images into blocks. Env vars wire things
   together: `API_URL=http://api:8000` links the file that reads it to the `api` service,
   and `DATABASE_URL=postgresql://...@db/...` links it to the Postgres container. Edges are
   kept at file level and rolled up to whatever level you are looking at.
6. **Enrichment** (`enrich.py`): `enrich-brief.md` lists the blocks, folders and
   connections that need human text. Claude writes `enrichment.json` (descriptions,
   purposes, connection notes, and corrections with evidence). Entries carry a content hash,
   so later runs only ask about code that changed.
7. **Render** (`render/`): Three.js r149, the Barlow fonts, the data and the app are
   inlined into one HTML file of about 1.2 MB. No network access needed.

### Output files

| File | What it is |
|------|------------|
| `wirehouse-out/archmap.raw.json` | What the rules found |
| `wirehouse-out/enrich-brief.md` | Claude's worklist |
| `wirehouse-out/enrichment.json` | Descriptions and corrections, kept between runs |
| `wirehouse-out/archmap.json` | The merged data behind the page |
| `wirehouse-out/wirehouse.html` | The warehouse |

## Supported stacks (v1)

- **JavaScript / TypeScript**: Next.js, React, Vue, Svelte, Nuxt, Remix, Astro, Angular,
  Express, Fastify, NestJS, Hono, Electron, React Native; tsconfig path aliases resolved.
- **Python**: FastAPI, Flask, Django, Starlette, Litestar, Celery, RQ, Streamlit and more;
  relative and absolute imports resolved.
- **.NET**: ASP.NET Core, Worker services, Azure Functions, Blazor, WPF and MAUI;
  ProjectReferences, EF Core DbSets and connection strings.
- **Infra**: docker-compose, Dockerfile, Terraform (AWS, Azure, GCP resource types),
  Kubernetes, GitHub Actions and other CI, Nginx, Caddy and Traefik, Vercel, Netlify, Fly
  and similar hosting files.

## Limits

- Detection is regex based. It favours precision over recall, and Claude's enrichment step
  can add what it misses (with evidence) or remove false positives.
- Dynamic wiring (service discovery, URLs built at runtime, DI containers) is only found
  when it shows up in env vars, config or literals.
- Very large rooms (hundreds of files in one folder) render fine but get dense; search is
  the fastest way around.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

The tests build a small Next.js + FastAPI + Postgres + Redis fixture repo and check the
detected blocks, connections, endpoints and tables, the enrichment round trip, that no
secret values leak into the output, and that the HTML is self-contained.

Third-party assets: Three.js (MIT, `render/vendor/THREE_LICENSE`) and the Barlow typeface
(SIL Open Font License, `render/vendor/BARLOW_OFL.txt`).
