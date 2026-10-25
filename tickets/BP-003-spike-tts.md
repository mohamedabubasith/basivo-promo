# BP-003 Spike: Kokoro / KittenTTS voiceover

Status: done (KittenTTS deferred)

## Tasks
- [x] `kokoro-onnx` int8 model: one line to WAV, measure load and synth time on CPU.
- [ ] KittenTTS as the `--tiny` option: deferred, see result.
- [x] macOS `say` fallback.
- [x] Confirm both model licences from the model cards.

## Done when
Three WAVs of the same line, timings, licence notes in this ticket.

## Result (2026-10-25)
- Kokoro-82M int8 via `kokoro-onnx`: model 92 MB + voices 28 MB, cached in `~/.basivo-promo/models/`.
  - Load 0.6 s. A 6 s line takes 0.7-1.6 s on CPU (4-8x faster than real time). 24 kHz mono.
  - Licence: Apache-2.0 (hexgrad/Kokoro-82M model card).
- macOS `say`: 2.0 s, zero download. Fallback only.
- KittenTTS: the current release (KittenTTS 2) uses the "Stellon Labs Community License", not Apache. Older ONNX models (`kitten-tts-nano-0.1/0.2`, `kitten-tts-mini-0.8`) are Apache-2.0. Kokoro is fast enough, so `--tiny` is deferred until someone needs a smaller download.
- Samples to listen to: `.spikes/vo_kokoro_af_heart.wav`, `.spikes/vo_kokoro_am_michael.wav`, `.spikes/vo_say.aiff`.
