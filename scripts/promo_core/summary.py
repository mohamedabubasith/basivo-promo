"""Plain-language descriptions for the confirmation popup. Standard library only (hook import)."""
import json
from pathlib import Path
from urllib.parse import urlparse

from .brief import SECRET_REF
from .mask_pii import mask

# HyperFrames subcommands that only read or inspect the project: no popup.
HF_READ_ONLY = {"lint", "check", "info", "compositions", "docs", "catalog", "doctor", "snapshot", "keyframes",
                "compare", "--help", "-h", "--version", "-v", "help", "usage"}
# Subcommands that send the project, media or data to HeyGen's servers.
HF_UPLOAD = {"publish", "cloud", "lambda", "cloudrun", "feedback"}


def _brief(path, cwd):
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    if p.is_dir():
        p = p / "promo.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")), p.parent
    except (OSError, ValueError):
        return None, p.parent


def _opt(args, name):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def _host(b):
    url = ((b or {}).get("site") or {}).get("url", "?")
    return urlparse(url).hostname or (f"local file {url}" if url != "?" else "?")


def _secrets(steps):
    names = set()
    for s in steps or []:
        v = (s.get("fill") or s.get("type")) if isinstance(s, dict) else None
        if isinstance(v, list) and len(v) == 2 and isinstance(v[1], str) and SECRET_REF.match(v[1]):
            names.add(SECRET_REF.match(v[1]).group(1))
    return sorted(names)


def describe(args, cwd="."):
    """Words after the promo executable -> (title, lines)."""
    if not args:
        return "basivo-promo", ["Show help."]
    cmd, rest = args[0], args[1:]
    pos = [a for a in rest if not a.startswith("--")]
    b, folder = _brief(pos[0], cwd) if pos else (None, Path(cwd))
    if cmd == "capture":
        shots = (b or {}).get("shots") or {}
        steps = shots.get("steps") or []
        names = [s.get("shot") for s in steps if isinstance(s, dict) and s.get("shot")]
        lines = [f"Open {_host(b)} in a hidden browser and save {len(names)} screenshot(s): {', '.join(names[:8])}",
                 f"Viewports: {', '.join(shots.get('viewports') or ['desktop'])}. {len(steps)} steps, on that site only."]
        return "Capture screenshots", lines + _common(b, steps, folder / "assets" / "captures")
    if cmd == "record-web":
        flows = [f for f in (b or {}).get("flows") or [] if not _opt(rest, "--flow") or f.get("name") == _opt(rest, "--flow")]
        steps = [s for f in flows for s in f.get("steps") or []]
        lines = [f"Record {len(flows)} flow(s) as video on {_host(b)}: {', '.join(f.get('name', '?') for f in flows)}",
                 "A hidden browser clicks, types and scrolls like a person; the mouse path is logged for the edit."]
        return "Record product video", lines + _common(b, steps, folder / "assets" / "recordings")
    if cmd == "render":
        fmts = (_opt(rest, "--formats") or ",".join((b or {}).get("formats") or ["16x9"])).split(",")
        return "Render video", [f"Render {', '.join(fmts)} with HyperFrames ({_opt(rest, '--quality') or 'delivery'} quality) in {folder}.",
                                "Runs locally (headless Chrome + ffmpeg). Then checks the audio track and loudness and",
                                "writes the MP4s and manifest.json next to promo.json. Nothing is uploaded."]
    if cmd == "scaffold":
        return "Create HyperFrames projects", [f"Create one HyperFrames project per format in {folder} and apply the brand colours.",
                                               "Downloads the pinned HyperFrames CLI from npm on first use."]
    if cmd == "screen":
        return "Edit a recording", [f"Turn recording '{_opt(rest, '--name') or (pos[1] if len(pos) > 1 else '?')}' into an edited block: "
                                    "speed ramps, auto-zoom to clicks, smooth cursor. Local only."]
    if cmd == "voice":
        return "Generate voiceover", ["Speak the script lines with the local voice model (nothing leaves this computer)."]
    if cmd == "music":
        return "Generate music", ["Compose a royalty-free track with @simpllyf/ditty in a local headless browser."]
    if cmd == "extract":
        src = pos[1] if len(pos) > 1 else "?"
        if src.startswith("http"):
            return "Adopt brand from website", [f"Open {mask(src)} in a hidden browser and read its colours, font, logo and text.",
                                                "Saves brand.json, content.json, the logo and two screenshots under assets/brand."]
        return "Adopt brand from image", [f"Read the palette from {src} into assets/brand."]
    if cmd == "login":
        host = urlparse(pos[0]).hostname if pos else "?"
        return "Log in (you type the password)", [
            f"Opens a visible browser at {mask(pos[0]) if pos else '?'}. You log in yourself; Claude does not see what you type.",
            f"After you click Done, session cookies are saved to ~/.basivo-promo/sessions/{host}.json (only you can read it)."]
    if cmd == "setup":
        return "Download voice model", ["Downloads Kokoro-82M (Apache-2.0, ~120 MB) from github.com/thewh1teagle/kokoro-onnx",
                                        "into ~/.basivo-promo/models and checks its SHA-256. One time only."]
    if cmd == "import":
        return "Import media", [f"Copy {pos[1] if len(pos) > 1 else '?'} into the project's assets (video converted for editing)."]
    if cmd == "record":
        dev = pos[1] if len(pos) > 1 else "?"
        what = {"ios": "the booted iOS Simulator", "android": "the connected Android device", "mac": "your whole Mac screen"}.get(dev, dev)
        return "Record screen", [f"Record {what} for {_opt(rest, '--seconds') or '15'} seconds.",
                                 "Close anything private first: everything visible is recorded."]
    if cmd == "new":
        return "Create promo folder", [f"Create a promo folder with promo.json for {mask(' '.join(pos)) or '?'}."]
    if cmd in ("validate", "styles", "doctor"):
        return f"basivo-promo {cmd}", ["Read-only check. Changes nothing."]
    return "basivo-promo", [f"Run: promo {mask(' '.join(args))[:200]}"]


def _common(b, steps, dest):
    site = (b or {}).get("site") or {}
    lines = [f"Login: {'reuses your saved session' if site.get('login') == 'session' else 'none'}."]
    names = _secrets(steps)
    if names:
        lines.append(f"Secrets: {', '.join(names)}. Asked in a local popup (or keychain/env); Claude never sees them.")
    if site.get("mask"):
        lines.append(f"Blurred on screen: {', '.join(site['mask'][:6])}")
    lines.append(f"Saves into {dest}")
    return lines


def describe_hf(args):
    """HyperFrames CLI words -> (decision, title, lines). decision: allow | ask."""
    sub = args[0] if args else "--help"
    rest = " ".join(args[1:])
    edits = {"move", "trim", "split", "set", "duplicate", "delete", "apply", "undo", "ids"}
    if sub in HF_READ_ONLY or (sub == "timeline" and ("--plan" in args or not edits & set(args[1:]))):
        return "allow", "", []
    if sub in HF_UPLOAD:
        return "ask", "UPLOAD to HeyGen", [f"`hyperframes {sub}` sends this project, its media or data to HeyGen's servers.",
                                           "Only continue if you asked for this. Rendering locally never needs it."]
    if sub == "media-use":
        return "ask", "Find or make media", ["HyperFrames media-use: may download media, or use paid HeyGen services if you are signed in.",
                                             f"Request: {mask(rest)[:160]}"]
    if sub in ("skills", "upgrade"):
        return "ask", "Change installed tools", [f"`hyperframes {sub}` installs or updates software or Claude Code skills on this machine."]
    if sub == "render":
        return "ask", "Render video", ["Render this HyperFrames project locally with headless Chrome and ffmpeg."]
    if sub == "preview":
        return "ask", "Open preview", ["Start the local HyperFrames Studio preview server for this project."]
    if sub in ("add", "init", "capture", "browser"):
        return "ask", f"HyperFrames {sub}", [f"`hyperframes {sub} {mask(rest)[:120]}`: downloads from the internet and writes files here."]
    return "ask", f"HyperFrames {sub}", [f"`hyperframes {sub} {mask(rest)[:160]}` changes files in this project."]
