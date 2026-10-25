# Styles

A style is a JSON file of defaults: colours, pace, transition, music, voice, backdrop and
cursor. A storyboard picks one with `"style": "<name>"` and can still override any field.

Lookup order (first match wins):
1. `promo-styles/<name>.json` in the storyboard folder or any of its 4 parent folders
   (a team can commit `promo-styles/` to share a house style).
2. `~/.basivo-promo/styles/<name>.json` (personal styles).
3. Built-in: `midnight` (default), `daylight`, `neon`, `editorial`, `playful`.

`promo extract` writes `promo-styles/<product>.json` from the product's site or image.

```json
{
  "name": "my-style",
  "description": "One line shown by `promo styles`.",
  "brand": {"bg": "#0b0d12", "fg": "#ffffff", "accent": "#6c5cff", "accent2": "#ff5c8a", "muted": "#9aa3b2",
            "font": "Inter", "personality": "corporate"},
  "voice": {"engine": "kokoro", "voice": "am_michael", "speed": 1.0},
  "music": {"style": "cinematic", "seed": 7, "volume": 0.5},
  "captions": {"burn": true},
  "transition": "push-left",
  "look": {"backdrop": "aurora", "cursor": "light"},
  "sfx": true
}
```

Allowed keys: `name`, `description`, `brand`, `voice`, `music`, `captions`, `transition`,
`look`, `sfx`. `brand.logo` in a style is a path relative to the style file. Keep text readable: `fg` on `bg` needs a contrast of at least 7:1, and `muted`
on `bg` at least 4.5:1.

Preview any style without a product: `promo style-sample <name>` (about 18 s, draft quality).
