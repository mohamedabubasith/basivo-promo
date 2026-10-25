---
name: promo
description: Make a production-ready promo, launch, demo or sales video of a web, mobile or desktop app with basivo-promo (HyperFrames + real screen recordings). Use when the user asks for a product video, promo, demo, launch film, sales video or app showcase, or wants one changed, restyled or re-rendered.
---

# basivo-promo

You are the editor. Scripts record, cut, voice, score and render; you write the creative plan and
the HyperFrames compositions. Do not look at frames or audio unless something needs checking.

`P="${CLAUDE_PLUGIN_ROOT}/scripts/promo"` and `HF="${CLAUDE_PLUGIN_ROOT}/scripts/hf"` (pinned
HyperFrames, telemetry off). Never call `npx hyperframes` directly; the gate denies it. Every
`$P` call and every writing `$HF` call opens a confirmation popup. That is expected.

## Progress the user can see

- At the start, create a task list (your todo/task tool) with these 8 steps and keep it current:
  1 Set up · 2 Adopt your brand · 3 Record the product · 4 Edit the footage · 5 Build the project ·
  6 Voice and music · 7 Compose the film · 8 Render.
- Give every Bash call a short plain description of the step ("Record the product flows",
  "Render the draft"), never the raw command. Popups already name the step ("Step 3 of 8").
- Between steps write one short line: what finished, what is next. Each command ends with
  `✓ done. Next: ...`; follow it unless the user said otherwise.
- After a render, open the MP4 for the user (`open <file>` on macOS) and ask what to change.

## 1. Assets first

In one AskUserQuestion, ask what they have: website or app URL, logo, images, screen
recordings, brand kit, a reference video they like. Use what exists before asking anything else.

- `$P new "<Product>" --title <slug> --url <url> --length <s> --formats 16x9,9x16`
  creates `promos/<product>/<date>-<slug>/` with `promo.json` and `assets/`.
- URL: `$P extract <folder> <url>` writes `assets/brand/{brand.json,content.json,hero.png,logo.*}`
  and a taste profile `promo-styles/<product>.json`. Image instead: `$P extract <folder> <image> [--logo]`.
  Read `content.json` (small) for real copy and numbers. Never invent stats or quotes.
- Files from the user: `$P import <folder> <file> --name <slug>`.
- No brand yet, or they want a new look: `$P design "<what the product is>"` prints three
  directions (UI UX Pro Max data). They pick; `$P design "<query>" --write N --name <slug> --brief <promo.json>`.

## 2. Direction

Then ask only what is still unknown, in one round: audience and the one message, length,
formats, voice (female/male/none), and the **format of the film**. Offer 2–3 storylines that fit
this product, not a fixed template, for example:

- Launch film (Apple/Linear): hook, tension, reveal of the real product, proof, claim, end card.
- Screen Studio demo: mostly recorded flow, camera zooms into each action, light captions.
- Fast social ad (9x16): 1–2 s cuts, kinetic type, product in the first 2 s.
- Explainer: problem, how it works in 3 beats, outcome.

Each storyline must differ in structure and pacing. Write a 5–8 line beat sheet and get a yes.

## 3. Real footage

- Web: write `flows` in `promo.json` (steps: `goto, wait, click, hover, type, press, scroll, pause`),
  then `$P record-web <promo.json> [--flow name]`. 60 fps, 2× DPR, cookie banners hidden.
  Use exact selectors: `role=tab[name="Pricing"]`, `text="Sign up"` (quoted = exact), ids.
  Unquoted `text=Foo` matches substrings and can click the wrong element.
- Then `$P screen <promo.json> assets/recordings/<flow>.mp4 --formats 16x9,9x16` turns it into
  an edited block: idle speed ramps, camera zooms to clicks and typing, pull-back on navigation,
  smoothed cursor and ripples. It prints a mount snippet. 9x16 with captions: `--fit 0.7 --lift 18`.
- Mobile/desktop: `$P record <promo.json> ios|android|mac --seconds N --name x`.
- Behind a login: prefer `$P login <url>` (they log in themselves; cookies stay local) and
  `"site": {"login": "session"}`. Otherwise `${secret:name}` in a `type` step; the value is
  asked in a local popup and typed as dots.

## 4. Compose

- `$P scaffold <promo.json>` creates one HyperFrames project per format with brand tokens
  (`--ground --ink --accent --accent-2 --muted --font-display`) and `assets/` linked.
- Write `script/vo.json` (`[{"id": "hook", "text": "..."}]`, ~2.6 words/s), then
  `$P voice <promo.json> script/vo.json` (Kokoro, local) and `$P music <promo.json> --seconds <len>`.
- Author `index.html` per format following the /hyperframes skill (clip contract, `data-start`,
  `data-duration`, `window.__timelines`). Mount the screen blocks. Add VO `<audio>` clips (each needs a unique `id`, or it renders silent) with
  `data-duration`, music with `data-volume="0.16"` and fades. Captions as clips.
- Edit like an editor: matched direction and speed at cuts, no crossfades, stagger under 500 ms,
  something moves in every shot, cursor causes the next action. Avoid three cards in a row and
  titles over dimmed screenshots. 9x16 and 1x1 get their own layout, not a scaled 16x9.
- Sound effects only from sources with a verified license.

## 5. Check and render

- `$HF lint` and `$HF check --json` (read-only, no popup). Fix errors; warnings are optional.
- `$HF snapshot --at 2,9,15` for a few stills only when layout is in doubt.
- `$P render <promo.json> --quality draft` first (run in background), share paths, then
  `--quality delivery`. Render verifies an audio track, normalises to −14 LUFS and writes
  `manifest.json` with SHA-256 hashes. Outputs: `master_16x9.mp4`, `vertical_9x16.mp4`, `square_1x1.mp4`.
- On failure read only the printed error, or `~/.basivo-promo/last-error.log`.

## Security (non-negotiable)

- Never ask for a password, token or code in chat. Secrets only as `${secret:name}`. If the user
  pastes one, tell them to remove it and never repeat it.
- Never read `~/.basivo-promo/sessions`, print `PROMO_SECRET_*` or query the keychain (denied).
- `site.mask` must cover customer names, emails and anything private on screen.
- `$HF publish`, `cloud`, `lambda` upload the project: only when the user explicitly asks.

Style profiles: references/styles.md. Build a personal style: /promo-style.
