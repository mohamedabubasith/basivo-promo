# Contributing

1. Fork, branch, and keep pull requests focused on one change.
2. Run the unit tests (standard library only): `python3 -m unittest discover -s tests`.
3. For anything visual, render the example and attach a frame or two:
   ```text
   PROMO_SECRET_DEMO_PASSWORD=demo scripts/promo capture examples/acme/storyboard.json
   scripts/promo render examples/acme/storyboard.json --draft
   scripts/promo preview examples/acme/storyboard.json
   ```
4. New scene types go in `templates/runtime.js` (builder), `templates/stage.css` (layout for all
   three formats) and `scripts/promo_core/storyboard.py` (`SCENES` and validation), with a line in
   `skills/promo/references/storyboard.md`. Follow `skills/promo/references/motion.md`.
5. Never add a code path that prints, logs or stores a secret value. Tests in
   `tests/test_core.py` cover the resolver and the hooks; extend them.
