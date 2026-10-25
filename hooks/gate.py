#!/usr/bin/env python3
"""PreToolUse gate for basivo-promo.

1. Every `promo` command asks for confirmation in Claude Code's own popup, with a plain
   description of what it will do (site, screenshots, secrets by name, output folder).
2. Tools may not read saved sessions or pull secrets out of the keychain or environment.

Fail-safe: if this script breaks while looking at a promo command it still asks; for
anything else it stays silent so normal permission rules apply.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

PROMO = re.compile(r"(?:^|[\s;&|(\"'/])(?:scripts/promo(?:\.py)?|promo\.py)(?=$|[\s\"'])")
HF_WRAPPER = re.compile(r"(?:^|[\s;&|(\"'/])scripts/hf(?=$|[\s\"'])")
# Unpinned HyperFrames runs telemetry and may install skills; basivo-promo always goes through scripts/hf.
HF_RAW = re.compile(r"(?:^|[\s;&|(])(?:npx|bunx|pnpm\s+dlx|yarn\s+dlx)\s+(?:-y\s+|--yes\s+)?hyperframes\b|(?:^|[\s;&|(])hyperframes\s+\w")
PRIVATE_PATH = re.compile(r"\.basivo-promo/sessions")
SECRET_READ = re.compile(r"find-generic-password[^|;&]*basivo-promo|secret-tool\s+lookup[^|;&]*basivo-promo|PROMO_SECRET_", re.I)
# Dumping the whole environment is only blocked when promo secrets are actually set in it.
ENV_DUMP = re.compile(r"(?:^|[\s;&|(])(?:printenv|env|export\s+-p|declare\s+-x|set)\s*(?:$|[|;&>)])")
PATH_FIELDS = ("file_path", "path", "pattern", "glob", "notebook_path")


def out(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def _after(command, exe_pattern):
    """Words after the first word matching exe_pattern, up to the next shell operator."""
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    for i, w in enumerate(words):
        if re.search(exe_pattern, w):
            rest = words[i + 1:]
            for j, r in enumerate(rest):
                if r in ("&&", "||", ";", "|", "&"):
                    return rest[:j]
            return rest
    return []


def promo_args(command):
    """Words after the promo executable, or None if this is not a promo call."""
    if not PROMO.search(command):
        return None
    return _after(command, r"(?:^|/)(?:scripts/promo|promo\.py)$")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or "."

    # Never let a tool touch saved login sessions. Only paths and commands are checked, so
    # documents that merely mention the folder can still be edited.
    targets = [str(ti.get(k) or "") for k in PATH_FIELDS] + [str(ti.get("command") or "")]
    if any(PRIVATE_PATH.search(t) for t in targets):
        out("deny", "basivo-promo: saved login sessions are private. They are used only by the promo scripts and never "
                    "shown to Claude.")

    if tool != "Bash":
        return
    command = ti.get("command") or ""
    has_secret_env = any(k.startswith("PROMO_SECRET_") for k in os.environ)
    if SECRET_READ.search(command) or (has_secret_env and ENV_DUMP.search(command)):
        out("deny", "basivo-promo: this command could print a secret (keychain entry, PROMO_SECRET_* variable or the "
                    "whole environment). Secrets stay out of the conversation; promo reads them itself when it needs them.")
    if HF_RAW.search(command) or (re.search(r"\bnpm\s+run\s+(render|dev|check|publish)\b", command)
                                  and (Path(cwd) / "hyperframes.json").is_file()):
        out("deny", "basivo-promo: run HyperFrames through \"${CLAUDE_PLUGIN_ROOT}/scripts/hf\" (pinned version, telemetry "
                    "off, no silent skill installs), not npx or npm run.")
    if HF_WRAPPER.search(command):
        words = _after(command, r"(?:^|/)scripts/hf$")
        try:
            from promo_core.summary import describe_hf
            decision, title, lines = describe_hf(words or [])
        except Exception:
            decision, title, lines = "ask", "HyperFrames", ["Run a HyperFrames command. (Could not summarise it.)"]
        if decision == "allow":
            return
        out("ask", _text(f"basivo-promo · {title}", lines, cwd))
    args = promo_args(command)
    if args is None:
        return
    try:
        from promo_core.summary import describe
        title, lines = describe(args, cwd)
    except Exception:
        title, lines = "basivo-promo", ["Run a basivo-promo command. (Could not summarise it; check the command below.)"]
    try:
        from promo_core.summary import header
        title = header(args[0] if args else "", title)
    except Exception:
        pass
    out("ask", _text(title, lines, cwd))


def _text(title, lines, cwd):
    """Popup text: title, then one bullet per line, with paths shown relative to the project."""
    body = "\n".join(f"• {l}" for l in lines)
    if cwd and len(cwd) > 1:
        body = body.replace(cwd.rstrip("/") + "/", "")
    return f"{title}\n{body}"


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass  # never block unrelated tools because this hook failed
