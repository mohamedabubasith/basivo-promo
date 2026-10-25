# basivo-promo

A Claude Code plugin that makes production-ready, animated promo videos of your web, mobile
and desktop apps, for sales and marketing teams.

You give it what you have (a website, a logo, screen recordings). It adopts your colours,
font, logo and copy, captures crisp screenshots of the real product, and renders a motion-
designed video with a local voiceover, generated music and captions in 16:9, 9:16 and 1:1.
Claude writes one small storyboard; everything heavy runs locally in scripts.

- **Looks edited, not generated.** Scene templates follow motion-design rules: matched-vector
  cuts on the music beat, springs, an oversized cursor that clicks and the camera zooms, word-by-
  word type, device frames (browser, laptop, phone), before/after wipes, counters.
- **Your brand, automatically.** `promo extract https://your.site` reads colours, font, logo,
  headings, features and stats, and turns them into a style.
- **Everyone has their own taste.** Five built-in styles, personal styles, team styles committed
  to your repo, and a style builder (`/promo-style`) that previews each change.
- **Private by design.** Every command asks for confirmation in a popup. Passwords go from a
  local popup (or your keychain) straight into the browser and never reach the model.
- **Cheap to run.** Claude writes about 1–2k tokens of JSON per video and never looks at frames
  unless you ask.
- **Fully local.** Voice: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) on your CPU.
  Music: [@simpllyf/ditty](https://github.com/simpllyf/ditty) in a headless browser. Video: ffmpeg.

## Install

Requirements: [Claude Code](https://claude.com/claude-code), [uv](https://docs.astral.sh/uv/),
ffmpeg, and Google Chrome (or Edge, or `uvx playwright install chromium`). Python dependencies
are installed by uv on first use.

```text
/plugin marketplace add mohamedabubasith/basivo-promo
/plugin install basivo-promo@basivo-promo
```

Then, once: ask Claude to "run promo doctor" and "run promo setup" (downloads the 120 MB voice
model and checks its SHA-256). Without it, use the macOS `say` voice or no voice.

## Use

```text
/promo https://acme.dev, a 45 second video for sales calls
```

Claude asks which assets you have, adopts your brand, asks the few things it still needs
(audience, length, formats, style, voice), captures the screens, writes the storyboard and
renders a draft. You give feedback; it renders the final.

Other commands:

| Command | What it does |
|---|---|
| `/promo-render <storyboard>` | Re-render after edits (`--draft` for a fast half-resolution pass) |
| `/promo-style` | Build your own style from a site, an image or your taste, with previews |

### Output

```text
promos/acme-deploy/2026-10-25-launch/
  master_16x9.mp4      1920×1080, H.264 High, CRF 17, BT.709, AAC 192k, -14 LUFS
  vertical_9x16.mp4    1080×1920, captions placed clear of Reels/TikTok/Shorts UI
  square_1x1.mp4       1080×1080
  poster_*.png         a frame from the end card of each format
  captions.srt
  manifest.json        durations, settings, SHA-256 of every file
  storyboard.json      the source of truth: edit and re-render
  captures/ brand/ assets/ work/   (work/ is cache, git-ignored)
```

### The CLI

The plugin's skill drives `scripts/promo`; you can run it yourself too:

```text
promo new "Acme" --title launch [--url https://app.acme.dev]
promo extract <folder> https://acme.dev        # or an image: promo extract <folder> logo.png --logo
promo login https://app.acme.dev               # you log in in a visible browser; cookies saved locally
promo capture <storyboard.json>
promo record <storyboard.json> ios|android|mac --seconds 20 --name onboarding
promo import <storyboard.json> clip.mov --name onboarding
promo validate <storyboard.json>
promo render <storyboard.json> [--draft] [--formats 16x9,9x16]
promo still <storyboard.json> --at 12.5        # one frame, for a quick look
promo preview <storyboard.json>                # 6-frame contact sheet
promo styles | style-sample <name> | setup | doctor
```

Storyboard reference: [skills/promo/references/storyboard.md](skills/promo/references/storyboard.md).
A complete example with a demo app: [examples/](examples/).

## Security model

- **Confirmation popup for every action.** A `PreToolUse` hook turns every `promo` command into
  a Claude Code permission prompt that says in plain words what will happen: which site, how
  many screenshots, which secrets by name, where files go.
- **Secrets never reach the model.** Storyboards may only reference `${secret:name}`. The value
  comes from `PROMO_SECRET_<NAME>`, your OS keychain (service `basivo-promo`), or a native
  masked popup, and goes straight into the browser. It is not printed, logged or saved; fields
  that received one are masked in every later screenshot. Literal values typed into password
  fields are refused.
- **Login handover.** `promo login` lets you log in yourself; only session cookies are saved,
  in `~/.basivo-promo/sessions/` with mode 600. The hook denies any tool access to that folder,
  keychain reads for `basivo-promo`, and `PROMO_SECRET_*` lookups.
- **Pasted secrets are stopped.** A `UserPromptSubmit` hook blocks messages containing API keys,
  tokens, private keys or `password:` assignments before they are sent
  (`BASIVO_PROMO_PROMPT_GUARD=0` turns it off).
- **Private data on screen.** `capture.mask` hides selectors (emails, customer names) in every
  screenshot. All script output and the audit log (`~/.basivo-promo/audit.log`) are redacted.
- **Scoped browsing.** Capture steps cannot navigate away from the site you named.

Report vulnerabilities privately: see [SECURITY.md](SECURITY.md).

## How it works

`storyboard.json` → Kokoro voiceover (scene timing follows the speech) → beat grid from the
music tempo → `templates/runtime.js` builds every scene on one master timeline with the Web
Animations API → headless Chrome seeks it frame by frame → ffmpeg encodes. Audio: voice, music
ducked under it, synthesized whooshes and clicks, two-pass loudness normalisation to −14 LUFS.

Render speed on an M-series Mac: about 2× real time per 1080p format.

## Credits

Motion rules adapted from the [LottieFiles motion-design skill](https://github.com/LottieFiles/motion-design-skill)
(MIT), [HeyGen HyperFrames](https://github.com/heygen-com/hyperframes) skills (Apache-2.0) and
[product-launch-motion](https://github.com/AbubakrChan/product-launch-motion) (MIT). Bundled
third-party files are listed in [NOTICE](NOTICE).

## License

MIT
