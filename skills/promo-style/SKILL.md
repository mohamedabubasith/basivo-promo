---
name: promo-style
description: Build, tweak or preview a personal or team video style for basivo-promo (colours, font, pace, transitions, music, voice, design direction). Use when the user wants their own look, a house style, "make it feel like X", or to change how all their promo videos look.
---

# Style builder

A style is a small JSON file of defaults (schema: ../promo/references/styles.md). You write it;
`promo style-sample` renders a 10-second preview so the user judges by eye, not by JSON.

`P="${CLAUDE_PLUGIN_ROOT}/scripts/promo"`

1. **Start from what they have.** Ask in one AskUserQuestion: a website, logo or image to adopt
   from; a built-in style to start from (`$P styles`); or a reference they like ("like Apple
   keynotes", "like Linear"). With a URL or image, run `$P extract <dir> <url|image>`: it writes a
   style from their real colours, font and logo. Use `<dir>` = `~/.basivo-promo/style-work/<name>`.
2. **Ask the taste questions** that the source did not answer, in one round with 2–4 options each:
   - Mood: calm/premium, confident/corporate, friendly/playful, bold/energetic (maps to `brand.personality`).
   - Theme: dark or light canvas. For a fresh look, `$P design "<product>"` gives three directions to pick from.
   - Movement: `push-left` (steady), `push-up` (editorial reveals), `zoom` (high energy).
   - Sound: music style (`cinematic`, `peppy`, `calm`, `playful`, `dreamy`, `lofi`, `ambient`, or none),
     voice (female `af_heart`/`af_bella`, male `am_michael`/`am_adam`, British `bf_emma`/`bm_george`, none),
     sound effects only from licensed sources.
3. **Write the file.** Personal style: `~/.basivo-promo/styles/<name>.json`. Team style: ask, then
   `promo-styles/<name>.json` in their repo so everyone gets it. Name is a lowercase slug.
   A logo path in a style is relative to the style file: copy the logo next to it
   (`~/.basivo-promo/styles/<name>.logo.svg`) and set `"logo": "<name>.logo.svg"`.
   Check contrast yourself: `fg` on `bg` ≥ 7:1, `muted` on `bg` ≥ 4.5:1, white text on `accent` ≥ 3:1.
   Fix colours that fail before saving.
4. **Preview.** `$P style-sample <name>` (style must be findable from the sample folder; personal
   and built-in styles are). Share the MP4 path. Change one thing at a time on feedback and
   re-sample.
5. **Use it.** Tell them to set `"style": "<name>"` in `promo.json`, or that `/promo` will offer it.

Do not invent brand colours the user did not give or extract; offer a built-in palette instead.
