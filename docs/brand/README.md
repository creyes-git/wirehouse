# Wirehouse brand kit: Hazard badge

A yellow safety badge with a hard hat and a 45° hazard-stripe band. Precise, playful, industrial.
All SVGs are self-contained: text is converted to outlines, so they render the same everywhere (GitHub included).

## Folders

| Folder | What's inside |
| --- | --- |
| `logo/` | Symbol (colour, night, ink, white, 16 px master), wordmark, horizontal + stacked lockups. SVG masters, PNGs in `logo/png/`. |
| `favicon/` | `favicon.ico` (16/32/48), `favicon.svg`, PNG favicons, `apple-touch-icon.png`, Android + maskable icons, `site.webmanifest`. |
| `social/` | GitHub social preview (1280×640), OG images (1200×630, dark + light), GitHub avatar (512). |
| `readme/` | README banner (light + dark), "How Wirehouse maps your code" strip (light + dark), hazard divider. |
| `landing/` | Hero banner (1920×1080, dark + light), standalone hero scene, six spot illustrations (dark + light), worker mascot, patterns. |
| `snippets/` | Copy-paste HTML `<head>`, README markup and CSS tokens. |

## Which file where

- **GitHub avatar** → `social/github-avatar-512.png`
- **Repo social preview** (Settings → General → Social preview) → `social/github-social-preview-1280x640.png`
- **README header** → `readme/readme-banner-light.svg` + `readme-banner-dark.svg` via `<picture>` (see `snippets/README-snippet.md`)
- **Website favicon** → everything in `favicon/` at your site root + `snippets/head.html`
- **Link previews** → `social/og-image-1200x630.png`
- **Landing hero** → `landing/hero-banner-*` as a full image, or `landing/hero-scene-*.svg` next to your own headline
- **Feature section** → `landing/spots/{dark|light}/spot-*.svg` (kiosk, container, silo, conveyor, gate, dock)

## Colour

| Token | Hex | Use |
| --- | --- | --- |
| Safety yellow | `#F2C230` | Primary. Badge on light backgrounds. |
| Amber | `#FFB23F` | Night variant of the badge on dark backgrounds. |
| Ink | `#1B2330` | Hard hat, stripes, wordmark on light. |
| Night navy | `#070B16` | Dark backgrounds. |
| Concrete | `#E3E1DB` | Neutral surfaces, text on dark. |
| Paper | `#F7F6F2` | Light backgrounds. |
| Pipe blue / amber / pink | `#39C0F5` / `#FBBF24` / `#F472B6` | Illustrations only: connections and particles. Never in the logo. |

## Type

Barlow Condensed (Google Fonts). Wordmark: Bold 700, sentence case, tracking −0.02em. Headlines: Bold 700. Body/taglines: Medium 500. Small labels: SemiBold 600, uppercase, tracking +0.08em.

## Rules

- **Clear space:** keep at least ¼ of the badge width empty on every side.
- **Minimum size:** use `wirehouse-symbol-small-16.svg` / `favicon.svg` below 24 px; the full symbol from 24 px up. Lockup minimum height: 24 px.
- **Light vs dark:** yellow badge with ink glyph on light; amber badge with knocked-out glyph on dark.
- **One colour:** use the `-ink` or `-white` files, where the hat and stripes are true cut-outs.
- **Don't:** rotate the badge, recolour the stripes, add gradients, glows or shadows, put text inside the symbol, or change the stripe angle from 45°.
