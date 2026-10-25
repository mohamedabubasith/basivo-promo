# BP-001 Spike: GSAP seek render to MP4

Status: todo

Prove the core render loop before building on it.

## Tasks
- [ ] HTML page with a paused GSAP timeline and `window.seek(t)`.
- [ ] Playwright (Python, `uv run`) seeks each frame, screenshots JPEG, pipes to `ffmpeg -f image2pipe`.
- [ ] Embedded `<video>` clip stays in sync (`currentTime` + await `seeked`).
- [ ] Measure: 10 s at 1920x1080, 30 fps. Target under 60 s wall time.

## Done when
A smooth 10 s MP4 with an animated headline and a video clip, plus the timing number.
