# storyboard.json reference

```json
{
  "version": 1,
  "product": "Acme Deploy",
  "title": "launch",
  "style": "midnight",
  "formats": ["16x9", "9x16", "1x1"],
  "fps": 30,
  "brand": {"bg": "#0b0d12", "fg": "#ffffff", "accent": "#6c5cff", "accent2": "#ff5c8a", "muted": "#9aa3b2",
            "font": "Inter", "personality": "corporate", "logo": "brand/logo.svg"},
  "voice": {"engine": "kokoro", "voice": "am_michael", "speed": 1.0},
  "music": {"style": "cinematic", "seed": 7, "volume": 0.5, "bpm": 96},
  "captions": {"burn": true},
  "transition": "push-left",
  "look": {"backdrop": "aurora", "cursor": "light"},
  "sfx": true,
  "capture": { ... },
  "scenes": [ ... ]
}
```

Only `version`, `product` and `scenes` are required. Everything else comes from the `style`
(default `midnight`); fields set here override the style.

| Field | Values |
|---|---|
| `formats` | `16x9` (1920×1080), `9x16` (1080×1920), `1x1` (1080×1080) |
| `fps` | 24, 25, 30, 60 |
| `brand.personality` | `premium` (slower), `corporate`, `playful`, `energetic` (faster) |
| `brand.font` | any installed font family; Inter is bundled and used as the fallback |
| `voice.engine` | `kokoro` (local, needs `promo setup` once), `say` (macOS), `none` |
| `voice.voice` | Kokoro: `af_heart`, `af_bella`, `af_nicole`, `am_michael`, `am_adam`, `am_eric`, `bf_emma`, `bm_george`, … |
| `music` | `null` for no music. `style`: `peppy`, `calm`, `playful`, `dreamy`, `lofi`, `cinematic`, `ambient`. Same `seed` gives the same tune. |
| `transition` | `push-left` (default), `push-up`, `zoom`, `cut`; can also be set per scene |
| `look.backdrop` | `aurora`, `grid`, `plain` |
| `look.cursor` | `dark`, `light` |

Media paths are relative to the storyboard folder and must stay inside it (`captures/…`,
`assets/…`, `brand/…`).

## Scenes

Every scene may have `vo` (voiceover line, ≤ 400 chars), `duration` (minimum seconds) and
`transition`. Scene length follows the voiceover automatically; cuts snap to the music beat.

| type | required | optional |
|---|---|---|
| `logo` | – | `text` (defaults to product), `sub` |
| `headline` | `text` | `eyebrow`, `sub` |
| `device` | `media` | `frame` (`browser`, `laptop`, `phone`, `none`), `pan` (`push`, `down`, `none`), `title`, `caption` |
| `click` | `media`, `point` (`[x, y]` 0–1 or `"auto"`) | `label`, `frame`, `title` |
| `features` | `items` (2–6 of `{icon?, title, text?}`) | `title` |
| `split` | `before`, `after` | `labels` (two strings), `title` |
| `stat` | `value`, `label` | `prefix`, `suffix`, `decimals` (0–3), `from` |
| `cta` | `text` | `button`, `url`, `sub` |

Text limits: `text` 60, `title` 60, `sub` 120, `caption` 90, `label` 40, `button` 24. Wrap one
word in `*asterisks*` to give it the brand gradient.

`pan: "down"` scrolls a tall full-page screenshot (`{"shot": "x", "full": true}`).

## capture

```json
"capture": {
  "url": "https://app.example.com/login",
  "viewports": ["desktop", "mobile"],
  "login": "none",
  "mask": [".customer-name", "[data-private]"],
  "steps": [
    {"fill": ["#email", "demo@example.com"]},
    {"fill": ["#password", "${secret:app_password}"]},
    {"click": "button[type=submit]"},
    {"wait": "networkidle"},
    {"shot": "dashboard"},
    {"click": "text=New project", "shot": "new-project"},
    {"scroll": 800},
    {"shot": "pricing", "full": true}
  ]
}
```

- `url`: http(s), `file://`, or a path relative to the storyboard. `goto` may not leave that site.
- `viewports`: `desktop` (1440×900 @2x), `mobile` (iPhone 15 Pro @3x), `tablet` (iPad Pro 11).
- `login`: `session` reuses the cookies saved by `promo login <url>`.
- Steps: `goto`, `wait` (ms, `networkidle`, or a selector), `click` (+ optional `shot` taken just
  before the click, which records the click point), `hover`, `fill` (`[selector, value]`), `press`
  (`Enter`, `Control+A`), `scroll` (pixels), `shot` (+ optional `full`).
- Screenshots go to `captures/<viewport>/<name>.png`; click points to `captures.json`.
- A literal value into a password field is refused. Fields that received a secret are masked
  in every later screenshot.
