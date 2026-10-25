# BP-002 Spike: ditty offline WAV in headless Chromium

Status: todo

## Tasks
- [ ] Vendor `@simpllyf/ditty` browser build to `vendor/ditty.js` (pin version, record sha256).
- [ ] In headless Chromium: `renderOffline({ style, seed, loops | seconds })` then `encodeWav(...)`, return bytes to Python.
- [ ] Check: same seed gives identical bytes; length is at least the target.

## Done when
`music.wav` for `peppy` and `cinematic`, 60 s, made with no network.
