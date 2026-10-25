# Security policy

basivo-promo drives a browser with your logins and turns what it sees into video, so we take
reports seriously.

## Reporting

Please report vulnerabilities privately through GitHub's "Report a vulnerability" button on
the Security tab of https://github.com/mohamedabubasith/basivo-promo. Do not open a public issue.
Include steps to reproduce and the version (`promo --version`). You will get a reply within 7 days.

## What we protect

| Asset | Protection |
|---|---|
| Passwords, tokens, OTPs | `${secret:name}` only; resolved from env, OS keychain or a native masked popup; never printed, logged, written, or shown in screenshots |
| Session cookies | Saved only by `promo login`, mode 600 in `~/.basivo-promo/sessions/`; tool access denied by the hook |
| Secrets in chat | `UserPromptSubmit` hook blocks messages with credential-shaped text |
| Private data on screen | `site.mask` selectors (kept across in-app navigation), secret fields typed as dots |
| Unexpected actions | Every `promo` command and every writing HyperFrames command raises a permission prompt describing it; raw `npx hyperframes` is denied; recordings cannot leave the named site |
| Uploads | `hf publish`, `cloud`, `lambda`, `cloudrun` and `feedback` prompt with an upload warning; nothing is uploaded otherwise |
| Logs | Script output, errors and `~/.basivo-promo/audit.log` pass through a redactor |
| Downloads | The voice model is fetched over HTTPS and checked against pinned SHA-256 hashes |

## Known limits

- The hooks guard Claude's tools. They cannot stop a user from pasting a secret into a file
  that Claude later reads; keep secrets out of promo.json and project files.
- Masking hides elements that match your selectors. Anything else visible in the app appears
  in the video: use a demo account with demo data.
- `PROMO_SECRET_*` environment variables are visible to other processes run by the same user.
  Prefer the keychain or the popup on shared machines.
