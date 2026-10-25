---
name: promo
description: Make a production-ready animated promo or sales video of a web, mobile or desktop app with basivo-promo. Use when the user asks for a product video, promo video, demo video, launch video, sales video or app showcase, or wants to change, re-render or restyle one.
---

# basivo-promo

You direct; scripts do the work. You write one small `storyboard.json` and run `promo` commands.
Never read video frames, screenshots or audio unless the user asks you to look at something.

`P="${CLAUDE_PLUGIN_ROOT}/scripts/promo"`. Every `$P` call opens a confirmation popup for the user
(the plugin's gate hook). That is expected; do not try to avoid it.

## Workflow

1. **Assets first.** Ask what they already have before anything else: website or app URL, logo or
   brand images, screen recordings, a brand kit. Use what exists; only ask for what is missing.
2. `$P new "<Product>" --title <slug> [--url <url>]` creates `promos/<product>/<date>-<slug>/`.
3. If there is a public URL: `$P extract <folder> <url>` adopts colours, font, logo and copy. It
   writes `brand/content.json` (headings, features, CTAs, stats), `brand/hero.png`, `brand/page.png`
   and a style named after the product. Image instead: `$P extract <folder> <image> [--logo]`.
   Read `brand/content.json` (small) for copy ideas. Never paste site text you did not get from it.
4. Ask only what is still unknown, in one AskUserQuestion round: audience and the one message,
   length (30, 45, 60 or 90 s), formats (16x9, 9x16, 1x1), style (the adopted one is the default;
   others: `$P styles`; or build one with /promo-style), voice (male, female, none).
5. App behind a login: prefer `$P login <url>` (the user logs in in a visible browser; cookies are
   saved locally) and `"login": "session"`. Otherwise use `${secret:name}` in a fill step; the user
   is asked in a local popup. **Never ask for a password, token or code in chat.**
6. Write the `capture` steps, run `$P capture <storyboard>`. Use `"point": "auto"` for click scenes.
   Mobile app or desktop app: `$P record <storyboard> ios|android|mac --seconds N --name x`, or
   `$P import <storyboard> <file> --name x` for files the user gives you.
7. Write the scenes (see references/storyboard.md), `$P validate <storyboard>`.
8. `$P render <storyboard> --draft` (run it in the background; it can take minutes). Share the
   paths. After feedback, edit the JSON and render without `--draft`.

## Writing rules

- One idea per scene. Headline ≤ 8 words; mark one key word as `*word*` for the brand highlight.
- Voiceover budget ≈ 2.6 words per second. 30 s ≈ 6-7 scenes, 60 s ≈ 10-12.
- Story: hook (logo or headline) → problem/benefit → product in action (device, click, split) →
  proof (stat, features) → CTA. Show the real product: prefer captured screens over text scenes.
- Use the product's real numbers and copy from `brand/content.json` or the user. Never invent stats.
- Keep the default transition; use `push-up` only for a conclusion and `zoom` for diving deeper.

## Cheap checks

- `$P still <storyboard> --at <seconds> [--format 9x16]`: one 960px frame. Look only if needed.
- `$P preview <storyboard>`: 6-frame contact sheet of a rendered video.
- On failure read only the printed error, or `tail -5 <folder>/work/render.log`.

## Security (non-negotiable)

- Secrets only as `${secret:name}`. If the user pastes one, tell them to remove it; never repeat it.
- Never read `~/.basivo-promo/sessions`, print `PROMO_SECRET_*`, or query the keychain (the hook denies it).
- `capture.mask` must cover customer names, emails and anything private on screen.

## References (read only when needed)

- references/storyboard.md: every field and scene type.
- references/motion.md: the motion rules the templates follow (for explaining choices).
- references/styles.md: style files and how users make their own.
