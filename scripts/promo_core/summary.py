"""Plain-language description of a `promo` command, shown in the confirmation popup.
Standard library only: the PreToolUse hook imports this."""
import json
from pathlib import Path
from urllib.parse import urlparse

from .mask_pii import mask
from .storyboard import FORMATS, SECRET_REF


def _sb(path, cwd):
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    try:
        return json.loads(p.read_text(encoding="utf-8")), p.parent
    except (OSError, ValueError):
        return None, p.parent


def _opt(args, name):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else None
    for a in args:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def describe(args, cwd="."):
    """args: the words after the promo executable. Returns (title, detail lines)."""
    if not args:
        return "basivo-promo", ["Show help."]
    cmd, rest = args[0], args[1:]
    pos = [a for a in rest if not a.startswith("--")]
    if cmd == "render" and pos:
        sb, folder = _sb(pos[0], cwd)
        fmts = (_opt(rest, "--formats") or ",".join((sb or {}).get("formats") or FORMATS)).split(",")
        lines = [f"Render the promo video in {folder}",
                 f"Formats: {', '.join(fmts)}{' (draft quality)' if '--draft' in rest else ''}"]
        if sb:
            voice = (sb.get("voice") or {}).get("engine", "style default")
            music = sb.get("music")
            lines.append(f"{len(sb.get('scenes') or [])} scenes. Voice: {voice}. Music: {'none' if music is None else (music or {}).get('style', 'style default')}.")
        lines.append("Runs locally: headless browser, local voice model, ffmpeg. Nothing is uploaded.")
        lines.append("Writes MP4s, posters, captions.srt and manifest.json into that folder.")
        return "Render video", lines
    if cmd == "capture" and pos:
        sb, folder = _sb(pos[0], cwd)
        cap = (sb or {}).get("capture") or {}
        url = cap.get("url", "?")
        host = urlparse(url).hostname or ("local file " + url if url != "?" else "?")
        steps = cap.get("steps") or []
        shots = [s.get("shot") for s in steps if isinstance(s, dict) and s.get("shot")]
        secrets = sorted({SECRET_REF.match(s["fill"][1]).group(1) for s in steps
                          if isinstance(s, dict) and isinstance(s.get("fill"), list) and len(s["fill"]) == 2
                          and isinstance(s["fill"][1], str) and SECRET_REF.match(s["fill"][1])})
        lines = [f"Open {host} in a headless browser and take {len(shots)} screenshot(s): {', '.join(shots[:8])}{'…' if len(shots) > 8 else ''}",
                 f"Viewports: {', '.join(cap.get('viewports') or ['desktop'])}. {len(steps)} steps (clicks, typing, scrolling) on that site only.",
                 f"Login: {'reuses your saved session for ' + host if cap.get('login') == 'session' else 'none'}."]
        if secrets:
            lines.append(f"Secrets: {', '.join(secrets)}. You will be asked for them in a local popup (or keychain/env). Claude never sees them.")
        if cap.get("mask"):
            lines.append(f"Hidden in screenshots: {', '.join(cap['mask'][:6])}")
        lines.append(f"Saves PNGs under {folder / 'captures'}")
        return "Capture app screenshots", lines
    if cmd == "login" and pos:
        host = urlparse(pos[0]).hostname or pos[0]
        return "Log in (you type the password)", [
            f"Opens a visible browser at {mask(pos[0])}. You log in yourself; Claude does not see what you type.",
            f"After you click Done, session cookies are saved to ~/.basivo-promo/sessions/{host}.json (only you can read it)."]
    if cmd == "setup":
        return "Download voice model", ["Downloads Kokoro-82M (Apache-2.0, ~120 MB) from github.com/thewh1teagle/kokoro-onnx",
                                        "into ~/.basivo-promo/models and checks its SHA-256. One time only."]
    if cmd == "import" and len(pos) >= 2:
        return "Import media", [f"Copy {pos[1]} into the storyboard's assets folder (videos are converted to WebM).",
                                f"Name: {_opt(rest, '--name') or Path(pos[1]).stem}"]
    if cmd == "record" and len(pos) >= 2:
        what = {"ios": "the booted iOS Simulator (xcrun simctl)", "android": "the connected Android device (adb screenrecord)",
                "mac": "your whole Mac screen (screencapture)"}.get(pos[1], pos[1])
        return "Record screen", [f"Record {what} for {_opt(rest, '--seconds') or '15'} seconds.",
                                 "Close anything private first: everything visible is recorded.",
                                 "The clip is saved into the storyboard's assets folder."]
    if cmd == "new":
        return "Create promo folder", [f"Create a new promo folder and storyboard.json for {mask(' '.join(pos)) or '?'}."]
    if cmd == "style-sample":
        return "Render style sample", [f"Render a short draft sample of style '{pos[0] if pos else '?'}' (no capture, no network)."]
    if cmd == "preview" and pos:
        return "Make preview", ["Make one small contact-sheet image (6 frames) from the rendered video."]
    if cmd in ("validate", "styles", "doctor"):
        return f"basivo-promo {cmd}", ["Read-only check. Changes nothing."]
    return "basivo-promo", [f"Run: promo {mask(' '.join(args))[:200]}"]
