# BP-007 Popup gate hook, secret prompt guard, audit log

Status: done (v0.2.0)

## Tasks
- [ ] `hooks/gate.py` PreToolUse on Bash: any `promo.py` call returns `ask` with a plain description (URL, pages, output path).
- [ ] Deny Read/Grep/Bash on `~/.basivo-promo/sessions` and `secrets`.
- [ ] UserPromptSubmit: block prompts that contain secrets (regex from `mask_pii.py`).
- [ ] All script stdout through `mask()`.
- [ ] Redacted `~/.basivo-promo/audit.log`.

## Done when
Tests show `ask` for every subcommand, `deny` for session paths, and a blocked prompt for a pasted token.
