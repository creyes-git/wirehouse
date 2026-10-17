---
name: wirehouse
description: Build a walkable 3D warehouse map of a codebase's architecture (services, APIs, databases, auth, queues, third-party providers and how they connect), with a 2D floor plan, as one offline HTML file. Use when the user types /wirehouse, or asks for an architecture map, system diagram, "how is this project wired", "show me the services and databases", or an interactive/visual map of a repo.
---

# Wirehouse

Wirehouse turns a project into a warehouse you can walk through. Blocks on the main
floor are the system's parts (frontends, services, workers, databases, caches, queues,
auth, third-party APIs, CI), arranged in zones from the entrance (clients) to the
loading dock (external providers). Pipes with moving particles are real connections
found in the code. Walking into a block opens a room with its folders and files on racks.

The static scanner finds *what* exists and what talks to what. You add *why*: plain
descriptions grounded in the code. The output is `wirehouse-out/wirehouse.html`.

Usage: `/wirehouse [path] [--quick]`. Path defaults to the current folder. `--quick` skips
the description step.

## Steps

### 1. Make sure the CLI is available

```bash
wirehouse --version || python -m wirehouse --version
```

If neither works, install it: `pip install "git+https://github.com/creyes-git/wirehouse"` (or, from a
source checkout, `pip install -e "{{WIREHOUSE_HOME}}"`).
Use `python -m wirehouse` in later steps if the `wirehouse` command is not on PATH.

### 2. Scan

```bash
wirehouse scan "<path>"
```

(Add `-o <folder>` to every command to write somewhere else.) This writes
`<path>/wirehouse-out/archmap.raw.json` and `enrich-brief.md`, and prints how
many blocks, folders and connections still need descriptions. Previously written
descriptions are cached by content hash, so a re-run only asks about what changed.

If the output says enrichment is up to date, or the user passed `--quick`, go to step 4.

### 3. Describe what the scanner found

Read `wirehouse-out/enrich-brief.md`. It lists every top-level block and folder that needs
text, with its id, hash, contents, how it was detected and where to look, plus the
top-level connections. Then write `wirehouse-out/enrichment.json` in the format the brief
shows.

How to do it well:
- **Read before you write.** For each top-level block, open its manifest and entry point
  (for example `main.py`, `app/layout.tsx`, `Program.cs`, the router files). For folders,
  the file list plus one or two key files is usually enough. Never describe from the name alone.
- **description**: 1 to 2 sentences on what it is, naming concrete things (tables,
  endpoints, providers, jobs). **purpose**: 1 sentence on the role it plays for the rest of
  the system. Plain words a new teammate understands.
- **links**: for each top-level connection in the brief, say what flows over it and when
  (for example "Server components fetch quotes and fundamentals through the FastAPI proxy").
- **Fix the map when the rules got it wrong.** Add a missing block or connection with
  `add_nodes` / `add_edges` only when you can point at a file and line. Remove false
  positives with `remove_nodes` / `remove_edges` and give each removal a `reason` with
  file:line evidence. Removing a top-level pair drops every connection between those two
  blocks and its `links` entry. Typical false positives: a URL that is only an `href` or a
  doc link, and a dependency that is declared but never imported (the brief marks these
  *inferred*).
- **Rename sparingly.** Set `name` only when the folder name hides what the block is
  (`superdb` -> "Market data warehouse"). Never repeat the path as the name.
- If something notable is missing, say so in a description instead of inventing it
  (for example, no authentication layer at all).
- Copy each `hash` exactly, keep entries that are already in the file, and never write
  secret values. Do not open real `.env` files; `.env.example` is fine.
- Large briefs (over about 60 entries): the brief ends its header with a suggested split
  ("web / app (20), ..."). If you can run subagents or parallel tasks, give each group to one that
  returns its JSON fragment; otherwise work through the groups one at a time. Write the top-level
  blocks and links yourself, then merge the fragments into one file.

Then write the guided layer, in the same file:
- **tours** (2 to 4): each one tells a story a new teammate needs, in the order things really happen
  ("How an order gets paid", "What happens at sign-in", "How a nightly job runs"). 3 to 8 stops, each
  `{"node", "text", "evidence"}`, where the text is 1 to 3 plain sentences about what the reader is looking at.
  When the story is simply "from A to B", use `{"id", "title", "route": [from_id, to_id]}` and Wirehouse walks
  the recorded path itself.
- **quests** (3 to 6): questions worth being able to answer about this codebase ("Where are passwords checked?",
  "Which job sends the invoice email?"). `answer` lists every node id that counts, `hint` points the way without
  giving it away, `explain` says what they found and why it matters.
- Every stop and quest cites `evidence` (file path from the project root plus line) that you opened and read.
  Never cite from memory.

Validate the JSON before moving on:

```bash
python -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8')); print('ok')" "<path>/wirehouse-out/enrichment.json"
```

### 4. Render

```bash
wirehouse render "<path>"
```

Add `--open` if the user wants it opened in their browser. Render prints how many
descriptions, connection notes, additions and removals it applied, how many tours and quests
there are, and one line per problem: `error [code] subject: message -> fix` (for example
`error [evidence/line-out-of-range] tours[checkout].stops[2]: ...`). Invalid parts are left out
of the page, never guessed. Fix exactly the entry named in each line, then render again. Two
rounds are enough; if something still fails, say so in your report rather than looping.

### 5. Report

Tell the user, briefly:
- where the file is (`<path>/wirehouse-out/wirehouse.html`, a single offline file they can share)
- what is on the main floor: the main blocks and the most important connections
- anything notable you found while describing (missing auth, a service talking straight
  to another service's database, an unused dependency)
- the tours and quests you wrote, in one line each
- the controls in one line: WASD to walk, click to inspect, E to walk into a block, Q to step
  out, / to search, P for the floor plan, R to trace a route, C for the clipboard of tours and quests

Suggest adding `wirehouse-out/` to `.gitignore` if it is not already there, but do not edit
the file without asking.

## Files in wirehouse-out/

| File | What it is |
|------|------------|
| `archmap.raw.json` | What the static rules found (regenerated on every scan) |
| `enrich-brief.md` | The worklist for step 3 |
| `enrichment.json` | Your descriptions and corrections (kept between runs) |
| `archmap.json` | Raw map merged with enrichment: the data behind the page |
| `wirehouse.html` | The warehouse itself |
