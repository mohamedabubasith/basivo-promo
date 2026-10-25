# BP-002 Spike: ditty offline WAV in headless Chromium

Status: done

## Tasks
- [x] Vendor `@simpllyf/ditty` browser build to `vendor/ditty.js` (pin version, record sha256).
- [x] In headless Chromium: `renderOffline({ style, seed, loops | seconds })` then `encodeWav(...)`, return bytes to Python.
- [x] Check: same seed gives the same music; length is at least the target.

## Done when
`music.wav` for `peppy` and `cinematic`, 60 s, made with no network.

## Result (2026-10-25)
- Vendored `@simpllyf/ditty@0.6.0` browser build: `vendor/ditty.global.js` (58,529 bytes, sha256 `60f6cdb0b684de8bc44cdb32d7acc0802155580d4761c8ff9b0b93b4b8f23a48`), licence in `vendor/ditty.LICENSE` (MIT).
- `renderOffline` uses `OfflineAudioContext`, so it must run in the browser. Works in headless Chrome with no network.
- 60 s, 44.1 kHz stereo: peppy 8.5 s, cinematic 3.1 s to render.
- Same seed gives the same score (notes identical). Samples differ by at most 3.1e-7 (about -130 dB, float rounding in Chrome's audio engine), so audio is not byte-identical but sounds identical. The manifest stores style + seed; we do not promise byte-identical WAVs.
- Output is loud (about -5 LUFS). The BP-005 mix must bring music down under the VO.
