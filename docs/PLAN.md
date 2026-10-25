# Plan: basivo-promo — Claude Code plugin for sales promo videos
> Historical: v0.1 plan. v0.2 moved rendering to HyperFrames (see tickets/BP-012 and CHANGELOG).

## Goal
`/promo <url or app>` → a polished, animated 30–90 s product promo (web, mobile, desktop) with music, a local voiceover, captions and several aspect ratios. Every action is confirmed in a popup. Secrets never reach the model. Token use stays low.

## Core idea (why it is cheap and looks professional)
- **Claude writes only a small `storyboard.json` (~1–2k tokens).** It is a list of scenes: template, text, asset ref, motion preset. Claude never sees frames, video or audio. It sees only one-line results from the scripts.
- **The motion lives in templates, not in model output.** HTML/CSS scene templates whose animations the Web Animations API pauses and seeks (no GSAP: native, no licence issue). A headless browser seeks the timeline frame by frame, takes screenshots and pipes them to ffmpeg. The render is deterministic, which is how editors get smooth easing, kinetic type, device mockups, push-ins, whip transitions and cursor zooms.
- **The voiceover sets the timing.** TTS runs first. Each scene lasts as long as its VO line plus padding, so the cuts land on the speech.

## Location and conventions (copied from existing plugins)
`/Users/abu/Abu/basivo-tool/basivo-promo/` (same layout as basivo-studio and basivo-operator):
```
.claude-plugin/plugin.json, marketplace.json
commands/promo.md            # wizard: brief → capture → storyboard → render
commands/promo-render.md     # re-render an edited storyboard (no capture)
skills/promo/SKILL.md        # storyboard schema, template catalog, rules
skills/promo/references/{templates.md,security.md}
hooks/hooks.json            # PreToolUse + UserPromptSubmit
hooks/gate.py               # popup gate + secret guard (python3 stdlib)
scripts/run                 # POSIX shim (copy of basivo-studio/scripts/run)
scripts/promo.py             # one CLI: capture | tts | music | render | doctor
scripts/mask_pii.py         # copy of basivo-operator/scripts/mask_pii.py
templates/*.html (no animation library)
tests/test_promo.py
```
Runtime: `promo.py` uses PEP 723 inline deps run with `uv run` (playwright, kokoro-onnx, soundfile). No venv setup. ffmpeg is required; `doctor` checks for it and for Chromium.

## Pipeline (`promo.py` subcommands)
1. **capture**
   - **Web:** Playwright drives the flow steps from the storyboard: goto, click, type `${secret:name}`, scroll, wait. It records at 2× DPR in desktop, and in mobile via device emulation (iPhone/Pixel). It produces clean clips plus cursor/click coordinates, which the templates use for zoom-to-click.
   - Playwright `mask:` selectors blur PII in captures, e.g. emails and customer names.
   - **Mobile native / desktop:** the user supplies recordings, or the script runs them after confirmation: `xcrun simctl io booted recordVideo`, `adb shell screenrecord`, macOS `screencapture -v`. They go into the same clip folder.
2. **tts** — Default **Kokoro-82M int8 ONNX** (`kokoro-onnx`, ~88 MB, CPU, 28 voices). `--tiny` (deferred) would use an Apache-2.0 KittenTTS ONNX model; KittenTTS 2 itself is not Apache. Zero-download fallback: macOS `say`. Models are cached in `~/.basivo-promo/models/`. The script outputs per-line WAVs and their durations. Kokoro licence confirmed Apache-2.0 on its model card.
3. **music** — **[@simpllyf/ditty](https://github.com/simpllyf/ditty)**: MIT, zero dependencies, ~17.5 KB, deterministic (same seed gives the same track).
   - Render: `renderOffline({ style, seed, seconds })` then `encodeWav(channels, sampleRate)`, which writes `audio/music.wav`.
   - Run it inside the same headless Chromium page used for rendering, so `OfflineAudioContext` is guaranteed. The file is vendored at `vendor/ditty.js`: no CDN, no network at render time.
   - The storyboard picks `style` from `peppy | calm | playful | dreamy | lofi | cinematic | ambient` (sales default: `peppy`/`cinematic`). It stores `seed` in `manifest.json`, so a re-render gives the same music.
   - Prefer `loops: n` (gapless form boundaries) sized to be at least the video length. ffmpeg trims it and adds a 1.5 s `afade` out at the end card.
   - Fallback: the user drops a track in `~/.basivo-promo/music/`.
4. **render**
   - Load each template with the scene data. Seek frame `n` with `window.seek(n/fps)`; every CSS animation gets `currentTime`; embedded `<video>.currentTime`, then awaits `seeked`. Take a JPEG screenshot and pipe it to `ffmpeg -f image2pipe`.
   - Audio: VO plus music, with `sidechaincompress` ducking and `loudnorm` to −14 LUFS.
   - Captions come from VO text and durations, as `.srt` plus an optional burned-in style.
   - Outputs: 16:9 master, 9:16 and 1:1 re-layouts (templates are responsive; not a crop).

Templates v1 (8): logo sting, kinetic headline, device mockup (browser/phone/laptop) with push-in, zoom-to-click with cursor ripple, feature grid stagger, before/after split, stat counter, CTA end card. The brand kit is reused from basivo-studio `brand.json` (colours, fonts, logo).

## Security: popups and secrets
- **Popup for every action.** `hooks/gate.py` runs on PreToolUse Bash when the command calls `promo.py`. It returns `permissionDecision: "ask"` with a plain reason, for example: *"Capture https://app.acme.com (3 pages, mobile + desktop), mask .email, save to ./promos/acme/2026-10-25-launch/"*. The pattern is the same as basivo-operator `hooks/check-domain.py:89` and claude-guard `hook.go:137`. Unknown subcommands, and any network access (model download, URL capture), always ask.
- **Credentials never pass through the model.**
  - The storyboard holds only `${secret:login_password}` placeholders.
  - At capture time `promo.py` resolves each placeholder itself: first the OS keychain (`security find-generic-password` on macOS, `secret-tool` on Linux), else a native masked popup (tkinter `show='*'`, or `osascript ... with hidden answer` on macOS). The value goes straight into Playwright, and the script never prints it.
  - Preferred alternative: **login handover**, as in basivo-operator. A headed browser opens, the user logs in, and `storageState` is saved to `~/.basivo-promo/sessions/<host>.json` with chmod 600.
- **Guards.**
  - gate.py **denies** Read/Grep/Bash access to `~/.basivo-promo/sessions|secrets`.
  - A UserPromptSubmit hook blocks prompts that contain secrets, using the regex from `mask_pii.py` / claude-guard `detectors.go:38`, and tells the user to use the popup instead.
  - All script stdout passes through `mask()` before Claude sees it.
- Audit log: `~/.basivo-promo/audit.log`, redacted (same as basivo-operator `redact-log.py`).

## Token budget
- The wizard asks only 4 questions: product, audience, length, platforms. Claude writes the storyboard once.
- Each script call prints ≤5 lines (paths, durations).
- Review uses one 800 px contact sheet (6 frames). It is optional and needs confirmation, using basivo-studio's `check_copy` trick.
- Edits are JSON patches to the storyboard plus `/promo-render`. No re-capture and no re-planning.

## Storage (production output)
`./promos/<product>/<YYYY-MM-DD>-<slug>/`
- `master_16x9.mp4` (1920×1080, H.264 High, CRF 18, 30 fps, AAC 192k, `+faststart`), `vertical_9x16.mp4`, `square_1x1.mp4`
- `poster.png`, `captions.srt`, `storyboard.json`, `clips/`, `audio/{vo,music,mix}.wav`
- `manifest.json`: sha256 of each file, durations, model/template versions, and the source URL (with no secrets)
- `.gitignore` covers `clips/` and `audio/` by default. Masters are kept.

## Build order
1. Spikes (half a day each): (a) seek → ffmpeg at 1080p30 render speed, (b) ditty `renderOffline` in headless Chromium → WAV, (c) Kokoro int8 quality and speed.
2. `promo.py render` + 3 templates on a handwritten storyboard.
3. `tts` + VO-driven timing + audio mix + captions.
4. `capture` (web) + secret resolver + login handover.
5. `hooks/gate.py` + UserPromptSubmit guard + audit log.
6. Commands and skill, the remaining 5 templates, 9:16 and 1:1 layouts, `music`.
7. Mobile/desktop recording helpers, `doctor`, marketplace.json.

## Verification
- `tests/test_promo.py`:
  - The secret resolver never writes a value to stdout or files: a canary secret is grepped across the output dir and logs.
  - gate.py returns `ask` for each subcommand and `deny` for session paths.
  - The storyboard schema rejects literal passwords.
  - `mask_pii --selftest`.
- E2E: `/promo http://localhost:<demo app>` produces 3 MP4s. `ffprobe` checks resolution, duration ±0.1 s and audio present. `ffmpeg -af ebur128` shows ≈ −14 LUFS. The canary secret is absent from the transcript (`~/.claude/projects/...jsonl`).
- Manual: watch the master; confirm every popup appeared before each capture, download and render.

## Open questions for the user
- Is the plugin repo private or public under `mohamedabubasith`?
