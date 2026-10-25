# Contributing

1. Install the requirements from the README (uv, Node 22+, ffmpeg, Chrome).
2. Run the tests: `python3 -m unittest discover -s tests` (standard library only, no network).
3. Try a change end to end on any public site:
   ```sh
   scripts/promo new Demo --url https://example.com --length 20
   scripts/promo extract promos/demo/<date>-launch https://example.com
   scripts/promo record-web promos/demo/<date>-launch/promo.json
   ```
4. Keep hooks, and the `promo_core` modules they import, free of third-party imports.
5. Security changes (gate, secrets, masking) need a test in `tests/test_core.py`.
6. Open a pull request with what changed and how you checked it. Generated videos stay out of git.
