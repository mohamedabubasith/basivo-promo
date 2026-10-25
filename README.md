# basivo-promo

A Claude Code plugin that makes production-ready, animated promo videos of your web, mobile and desktop apps, for sales teams.

**Status: in development.** See [docs/PLAN.md](docs/PLAN.md) for the design and [tickets/](tickets/) for the work.

## What it does

- Captures your app (web via Playwright; mobile and desktop from screen recordings).
- Animates it with motion templates: device mockups, push-ins, zoom-to-click, kinetic type, transitions.
- Adds a local voiceover (Kokoro-82M / KittenTTS, on your CPU) and generated music ([@simpllyf/ditty](https://github.com/simpllyf/ditty)).
- Exports 16:9, 9:16 and 1:1 MP4s, captions, a poster and a manifest.

## Security

- Every capture, download and render asks for confirmation in a popup first.
- Credentials are entered in a native masked popup or by logging in yourself. They go straight to the browser and never reach the model.
- Logs and script output are redacted.

## Requirements

ffmpeg, Python 3.10+, [uv](https://docs.astral.sh/uv/), Chrome or Chromium.

## License

MIT
