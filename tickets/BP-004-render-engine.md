# BP-004 Render engine + first 3 templates + manifest

Status: replaced by BP-012 (HyperFrames)

## Tasks
- [ ] `scripts/promo.py render <storyboard.json>`; prints at most 5 lines.
- [ ] Storyboard schema (scenes: template, text, asset, motion, duration); rejects literal secrets.
- [ ] Templates: kinetic headline, device mockup with push-in, CTA end card.
- [ ] Brand kit from basivo-studio `brand.json`.
- [ ] Output folder `./promos/<product>/<date>-<slug>/` with `manifest.json` (sha256, durations, versions).
- [ ] H.264 High, CRF 18, 30 fps, `+faststart`.

## Done when
A hand-written storyboard renders a 20 s master MP4 and manifest.
