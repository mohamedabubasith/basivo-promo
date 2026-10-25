---
description: Re-render a promo after edits (draft, looks or delivery quality).
argument-hint: "<path to promo.json> [--quality draft|looks|delivery] [--formats 16x9,9x16,1x1]"
---

Use the **promo** skill. `P="${CLAUDE_PLUGIN_ROOT}/scripts/promo"`, `HF="${CLAUDE_PLUGIN_ROOT}/scripts/hf"`.

1. If no path is given, list `promos/*/*/promo.json` (newest first) and ask which.
2. Apply the requested changes to the compositions, then run `$HF check --json` in each format folder.
3. Run `$P render <promo.json> $ARGUMENTS` in the background and report the printed paths.
