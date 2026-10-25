# BP-010 (parent) Adopt the user's own brand and content

Status: doing

Whatever the user gives (website URL, logged-in app, image, logo, video, brand kit), use it
first and ask only for what is missing.

## Tasks
- [x] `promo extract <folder> <url>`: colours (usage census + brand tokens), font, logo (header home link, SVG with baked paint), headings, features, CTAs, stats, hero and full-page screens.
- [x] `promo extract <folder> <image> [--logo]`: palette from an image.
- [x] Masked text; scoped to the given site; optional saved session for logged-in apps.
- [x] Tested on linear.app, stripe.com, vercel.com, notion.com.
- [ ] Feed the result into the HyperFrames project as brand tokens (BP-012).
- [ ] Video input: pull key frames and palette from a user's clip.

## Done when
`/promo <url>` produces a video in the product's own colours, font and logo with no colour questions asked.
