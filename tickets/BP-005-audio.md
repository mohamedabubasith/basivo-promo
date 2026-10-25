# BP-005 Voiceover timing, music, mix, captions

Status: done (v0.2.0)

## Tasks
- [ ] `promo.py tts`: one WAV per scene line, durations into the storyboard.
- [ ] Scene length = VO length + padding.
- [ ] `promo.py music`: ditty style + seed, trim + 1.5 s fade on end card.
- [ ] Mix: `sidechaincompress` ducking, `loudnorm` to -14 LUFS.
- [ ] `captions.srt` from VO text and durations; optional burned-in style.

## Done when
Master has VO, ducked music, at -14 LUFS (+-1), and matching captions.
