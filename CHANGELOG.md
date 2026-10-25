# Changelog

## 0.1.0 (2026-10-25)

First public release.

- `/promo` wizard: assets first, then only the missing questions; draft and final renders.
- Eight scene templates: logo, headline, device (browser, laptop, phone, none), click (cursor,
  ripple, zoom, callout), features, before/after split, stat counter, CTA.
- Formats 16:9, 9:16 and 1:1 from one storyboard, with platform-safe caption placement.
- Brand adoption: `promo extract` from a website (colours, font, logo, copy, screens) or an image.
- Styles: five built-in, personal, team (`promo-styles/`), `/promo-style` builder, `style-sample`.
- Local voiceover (Kokoro-82M, macOS `say`), generated music (@simpllyf/ditty) with beat-snapped
  cuts, synthesized whoosh and click sounds, ducking, two-pass loudness to -14 LUFS.
- Capture: Playwright flows, desktop/mobile/tablet viewports, PII masking, click points.
- Native recording helpers: iOS Simulator, Android (adb), macOS screen; `import` for any clip.
- Security: confirmation popup for every command, `${secret:name}` popup/keychain resolver,
  login handover, session and secret access denied to tools, pasted-secret guard, redacted logs.
