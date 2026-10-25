# BP-001 Spike: GSAP seek render to MP4

Status: done

Prove the core render loop before building on it.

## Tasks
- [x] HTML page with a CSS animations (Web Animations API, no GSAP) and `window.seek(t)`.
- [x] Playwright (Python, `uv run`) seeks each frame, screenshots JPEG, pipes to `ffmpeg -f image2pipe`.
- [x] Embedded `<video>` clip stays in sync (`currentTime` + await `seeked`).
- [x] Measure: 10 s at 1920x1080, 30 fps. Target under 60 s wall time.

## Done when
A smooth 10 s MP4 with an animated headline and a video clip, plus the timing number.

## Result (2026-10-25)
- 10 s, 1920x1080, 30 fps: **22.8 s** wall (headless Chrome via Playwright `channel="chrome"`, JPEG q92 to libx264 CRF 18). Output is H.264 High, exactly 10.000 s.
- Seek uses `document.getAnimations()` + `currentTime`; CSS `linear()` easing gives spring/overshoot motion without a library.
- Video clip syncs with `currentTime` + `seeked`.
- Note for BP-004: layout must keep the headline clear of the push-in.
