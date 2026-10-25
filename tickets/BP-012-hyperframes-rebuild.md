# BP-012 (parent) Editor-style videos on HyperFrames

Status: done (v0.2.0)

## Why
User review of the first renders (2026-10-25):
1. "No audio": finals had AAC, but silent intermediates (`work/video_*.mp4`) sat next to them.
2. Every video looked the same: one fixed template per scene type.
3. Static and "AI-generated": screenshots plus template motion, not edited real footage.

HyperFrames (heygen-com/hyperframes, Apache-2.0, 0.8.198) gives a real timeline with tracks,
~450 catalog blocks (transitions, kinetic type, camera moves, device stages), checks, Studio
preview and fast deterministic renders (10 s 1080p in ~10 s here). Its launch guide names
"feature list as three cards" and "title over a dimmed screenshot" as tells of weak promos.

## Design
- basivo-promo = intake + security + assets + direction. HyperFrames = composition and render.
- `scripts/hf`: pinned HyperFrames, telemetry off, no silent skill installs.
- Real product footage: `promo record-web` records a flow as 60 fps video plus a cursor/click
  event log; the bundled `promo-screen` block turns it into a Screen Studio-style edit
  (auto-zoom to clicks, smooth oversized cursor, click ripples).
- Creative direction per request: three distinct storylines from the brief and assets; the user picks.
- One HyperFrames project per format (`16x9/`, `9x16/`, `1x1/`) sharing `assets/`.
- `promo finish`: verify audio, loudness, manifest with hashes, remove intermediates.
- Gate: ask for every HyperFrames command that writes, renders or uses the network; strong
  warning for anything that uploads (publish, cloud, lambda, cloudrun, feedback).

## Tasks
- [ ] scripts/hf wrapper
- [ ] record-web with events + promo-screen block
- [ ] promo new (HyperFrames projects + brand tokens) and promo finish
- [ ] gate rules for HyperFrames commands
- [ ] skills rewritten (intake, direction, build with /hyperframes, review, render)
- [ ] remove the old renderer
- [ ] example film made end to end, all three formats, with audio
