---
description: Re-render a promo video after editing its storyboard (draft or final quality).
argument-hint: "<path to storyboard.json> [--draft] [--formats 16x9,9x16,1x1]"
---

Use the **promo** skill. `P="${CLAUDE_PLUGIN_ROOT}/scripts/promo"`.

1. If no storyboard path is given, list `promos/*/*/storyboard.json` (newest first) and ask which.
2. Apply any changes the user asked for to the JSON, then run `$P validate <storyboard>`.
3. Run `$P render <storyboard> $ARGUMENTS` in the background and report the printed paths.
