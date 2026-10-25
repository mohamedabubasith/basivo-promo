#!/usr/bin/env python3
"""UserPromptSubmit guard: stop a message that contains a credential before it reaches the model.

Only high-confidence shapes are blocked (provider API keys, tokens, private keys, explicit
password=/token: assignments, card numbers), so normal prose and code pass. Turn it off with
BASIVO_PROMO_PROMPT_GUARD=0.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

PEM = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")


def found(prompt):
    from promo_core.storyboard import SECRET_KV, SECRET_TAGS
    from promo_core.mask_pii import mask

    kinds = set()
    if PEM.search(prompt):
        kinds.add("PRIVATE_KEY")
    if SECRET_KV.search(prompt):
        kinds.add("PASSWORD/TOKEN")
    # Typed provider tokens only; the generic long-blob rule ([SECRET]) is skipped so hashes and IDs pass.
    for tag in SECRET_TAGS.findall(mask(prompt, aggressive=False)):
        if tag not in ("SECRET",) and f"[{tag}]" not in prompt:
            kinds.add(tag)
    return sorted(kinds)


def main():
    if os.environ.get("BASIVO_PROMO_PROMPT_GUARD", "1") == "0":
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    prompt = data.get("prompt") or ""
    kinds = found(prompt)
    if kinds:
        print(json.dumps({"decision": "block", "reason":
            f"basivo-promo stopped this message because it looks like it contains a secret ({', '.join(kinds)}). "
            "It was NOT sent to Claude. Remove the secret and resend. For logins, use ${secret:name} in the "
            "storyboard: promo asks for the value in a local popup (or reads PROMO_SECRET_NAME / your keychain). "
            "To turn this check off, set BASIVO_PROMO_PROMPT_GUARD=0."}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
