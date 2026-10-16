# Logo brief for Claude Design

Paste everything below the line into Claude Design. Attach a screenshot of the warehouse
(`docs/assets/screenshot-night.png`) so it can see the product's look.

---

Design a logo system for **Wirehouse**, an open-source developer tool.

## What the product is

Wirehouse scans a codebase and turns its architecture into a 3D warehouse you can walk through
in the browser. Each part of the system is a physical object on a warehouse floor: web apps are
kiosks, services are shipping containers, databases are silos, queues are conveyor belts, auth is
a security gate, third-party APIs wait at the loading dock. Real connections found in the code
are pipes with particles flowing through them. You play as a small warehouse worker in a yellow
hard hat and hi-vis vest, holding a clipboard: you walk into a block to see its folders as crates
and its files on shelving racks, trace where a request goes, and take guided tours. It is a
friendly mini-game on the surface with serious analysis underneath, and it ships as one offline
HTML file. Built for Claude Code. The name is **wire** (connections, wiring) + **warehouse**.

Audience: software engineers, tech leads and new teammates onboarding to a codebase. It will
live on GitHub as a public project, so the mark must work as a GitHub avatar, a favicon and a
README header.

## Personality

Precise, playful, industrial. Think well-run warehouse: safety yellow, steel, painted floor
lines, stencilled labels, everything labelled and in its place. Confident and a little fun, never
childish. The fun comes from the warehouse metaphor, not from cartoon effects.

## Directions to explore (show at least three, side by side)

1. **The W rack.** A bold, geometric "W" built from warehouse shelving uprights and beams (the
   beams in safety orange/yellow), seen straight on or in clean isometric.
2. **Wired crate.** An isometric crate or container whose edges continue into two or three pipes
   or wires that leave the box, one with a small flowing dot. Suggests "a block and its
   connections".
3. **Floor-plan W.** A top-down floor plan: a few rectangles (blocks) joined by routed pipes whose
   path draws a "W". The most "architecture diagram" of the three.
4. **Hazard-stripe badge (optional).** A rounded square with a diagonal safety-stripe band and a
   simple glyph, closest to the small mark already in the app's top bar.

For the best direction, also draw the **worker mascot** as a separate, optional asset: a small,
friendly figure in a yellow hard hat and orange hi-vis vest with reflective strips, holding a
clipboard, simple enough to read at 64 px.

## Visual rules

- Flat vector shapes, a strong silhouette, at most 2 to 3 colours in the symbol. No photoreal 3D,
  no heavy gradients, no glows, no glass, no AI sparkles.
- Must stay recognisable at **16 px** (favicon) and in **one colour** (black on white, white on
  black). Show those tests.
- Works on both **dark** (`#070B16`) and **light** (`#F7F6F2`) backgrounds.
- Corner radius, stroke widths and angles consistent across the system; 45 degree hazard
  stripes if used.
- The symbol contains no text.

## Palette

| Role | Colour |
|------|--------|
| Safety yellow (primary) | `#F2C230` |
| Amber (night variant) | `#FFB23F` |
| Ink | `#1B2330` |
| Night navy | `#070B16` |
| Concrete | `#E3E1DB` |
| Pipe accents, use sparingly | calls `#39C0F5`, data `#FBBF24`, auth `#F472B6` |

## Type

The wordmark "Wirehouse" in **Barlow Condensed** Bold or SemiBold (the typeface used inside the
app), sentence case, slightly tight tracking. Optional stencil treatment if it stays crisp.

## Avoid

- A literal warehouse building with a pitched roof, a house icon, or a generic cube/hexagon
  "tech" logo.
- Anything that reads as Docker (whale, stacked containers on a ship), Kubernetes (helm wheel),
  GitHub, or Anthropic/Claude marks.
- Circuit-board traces and network-graph clichés.

## Deliverables

1. Symbol (SVG), plus a 1-colour version.
2. Horizontal lockup: symbol + wordmark, in a light and a dark version.
3. Square app icon / GitHub avatar (512 x 512).
4. Favicon at 16 and 32 px.
5. GitHub social preview, 1280 x 640: lockup on night navy, the line "Walk through your codebase
   like a warehouse." and a faint isometric warehouse floor with two or three pipes.
6. README banner, 1600 x 400, light and dark, same content as the social preview.

Show the three directions first with the 16 px and one-colour tests, then refine the strongest one
into the full set.
