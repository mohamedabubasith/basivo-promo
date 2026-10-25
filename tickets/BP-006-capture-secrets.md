# BP-006 Web capture, secret resolver, login handover

Status: done (v0.2.0)

## Tasks
- [ ] `promo.py capture`: flow steps (goto, click, type, scroll, wait), desktop and mobile emulation, 2x DPR.
- [ ] Record cursor/click coordinates for zoom-to-click.
- [ ] Playwright `mask:` selectors for PII.
- [ ] `${secret:name}` resolver: OS keychain, else native masked popup (osascript / tkinter). Never printed, never written.
- [ ] Login handover: headed browser, user logs in, `storageState` saved to `~/.basivo-promo/sessions/<host>.json`, chmod 600.

## Done when
Capture of a logged-in demo app works, and a canary secret is absent from all outputs and logs.
