# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#   "playwright>=1.47,<2",
#   "kokoro-onnx>=0.4,<1",
#   "soundfile>=0.12",
#   "numpy>=1.24",
# ]
# ///
"""basivo-promo: production-ready promo videos of your apps. Run through scripts/promo (uv)."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from promo_core import __version__  # noqa: E402
from promo_core import ff  # noqa: E402
from promo_core.mask_pii import mask  # noqa: E402
from promo_core.paths import ERROR_LOG, HOME, KOKORO_BASE, KOKORO_FILES, MODELS, PromoError, audit, private_dir, slug  # noqa: E402
from promo_core.storyboard import (FORMATS, IMAGE_EXT, PLUGIN_STYLES, VIDEO_EXT, StoryboardError,  # noqa: E402
                                   estimate_seconds, list_styles, load, secret_names)


def say(*parts):
    """Every line Claude sees goes through the masker."""
    print(mask(" ".join(str(p) for p in parts)), flush=True)


def progress_logger(folder):
    """Long renders log progress to work/render.log instead of flooding the transcript."""
    path = Path(folder) / "work" / "render.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a", encoding="utf-8")

    def log(msg):
        f.write(f"{time.strftime('%H:%M:%S')} {mask(msg)}\n")
        f.flush()
    return log


# ---------- commands ----------

def cmd_new(a):
    folder = Path(a.root) / slug(a.product) / f"{date.today().isoformat()}-{slug(a.title or 'promo')}"
    if (folder / "storyboard.json").exists():
        raise PromoError(f"{folder}/storyboard.json already exists")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "assets").mkdir(exist_ok=True)
    sb = {"version": 1, "product": a.product, "title": slug(a.title or "promo"), "style": a.style,
          "formats": ["16x9", "9x16", "1x1"], "scenes": [
              {"type": "logo", "vo": f"Meet {a.product}."},
              {"type": "headline", "text": "Your *headline* here", "vo": "One sentence about the main benefit."},
              {"type": "cta", "text": "Try it today", "button": "Get started", "vo": "Try it today."}]}
    if a.url:
        sb["capture"] = {"url": a.url, "viewports": ["desktop"], "login": "none", "mask": [], "steps": [{"shot": "home"}]}
    (folder / "storyboard.json").write_text(json.dumps(sb, indent=2) + "\n", encoding="utf-8")
    (folder / ".gitignore").write_text("work/\n", encoding="utf-8")
    audit("new", folder)
    say(f"created {folder / 'storyboard.json'}")


def cmd_validate(a):
    sb = load(a.storyboard)
    say(f"ok: {len(sb['scenes'])} scenes, style {sb['style']}, about {estimate_seconds(sb):.0f}s, formats {', '.join(sb['formats'])}")
    if "capture" in sb:
        names = secret_names(sb)
        say(f"capture: {sb['capture']['url']} ({len(sb['capture']['steps'])} steps){'; secrets: ' + ', '.join(names) if names else ''}")


def cmd_styles(a):
    base = Path(a.where or ".")
    if base.is_file():
        base = base.parent
    for name, (path, desc) in list_styles(base).items():
        where = "built-in" if path.parent == PLUGIN_STYLES else str(path.parent)
        say(f"{name:12} {desc[:90]} ({where})")


def cmd_setup(a):
    private_dir(MODELS)
    for name, (sha, size) in KOKORO_FILES.items():
        dest = MODELS / name
        if dest.is_file() and _sha(dest) == sha:
            say(f"{name}: already installed")
            continue
        part = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(KOKORO_BASE + name, timeout=60) as r, open(part, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except OSError as e:
            part.unlink(missing_ok=True)
            raise PromoError(f"download of {name} failed: {e}")
        if _sha(part) != sha:
            part.unlink(missing_ok=True)
            raise PromoError(f"{name}: checksum mismatch, download discarded")
        part.rename(dest)
        say(f"{name}: installed ({size / 1e6:.0f} MB, sha256 verified)")
    audit("setup", "kokoro models")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_login(a):
    from promo_core.capture import login
    path = login(a.url)
    audit("login", a.url, "session saved")
    say(f"session saved for {path.stem} (readable only by you). Use \"login\": \"session\" in the capture section.")


def cmd_capture(a):
    from promo_core.capture import capture
    sb = load(a.storyboard, check_media=False)
    if "capture" not in sb:
        raise PromoError("this storyboard has no capture section")
    result, shots = capture(sb, a.storyboard, log=progress_logger(Path(a.storyboard).parent))
    audit("capture", sb["capture"]["url"], f"{shots} screenshots")
    clicks = [k for k, v in result.items() if "point" in v]
    say(f"captured {shots} screenshot(s) into captures/: {', '.join(sorted(result))[:600]}")
    if clicks:
        say(f"click points recorded for: {', '.join(clicks)} (use \"point\": \"auto\")")


def _ingest(src, folder, name):
    src = Path(src)
    if not src.is_file():
        raise PromoError(f"file not found: {src}")
    if not slug(name) == name:
        raise PromoError("name must be a slug: lowercase letters, digits and -")
    assets = folder / "assets"
    assets.mkdir(exist_ok=True)
    ext = src.suffix.lower()
    if ext in VIDEO_EXT:
        dst = assets / f"{name}.webm"
        ff.ingest_video(src, dst)
    elif ext in IMAGE_EXT:
        dst = assets / f"{name}{ext}"
        shutil.copyfile(src, dst)
    else:
        raise PromoError(f"unsupported file type {ext}")
    return dst


def cmd_import(a):
    folder = Path(a.storyboard).resolve().parent
    dst = _ingest(a.file, folder, a.name or slug(Path(a.file).stem))
    audit("import", dst.name)
    say(f"imported: {dst.relative_to(folder).as_posix()}")


def cmd_record(a):
    folder = Path(a.storyboard).resolve().parent
    secs = a.seconds
    tmp = folder / "work" / f"record-{a.name}.{'mov' if a.device == 'mac' else 'mp4'}"
    tmp.parent.mkdir(exist_ok=True)
    if a.device == "ios":
        if not shutil.which("xcrun"):
            raise PromoError("xcrun not found (needs Xcode on macOS)")
        p = subprocess.Popen(["xcrun", "simctl", "io", "booted", "recordVideo", "--codec=h264", "--force", str(tmp)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(secs)
        p.send_signal(signal.SIGINT)
        p.wait(timeout=30)
    elif a.device == "android":
        if not shutil.which("adb"):
            raise PromoError("adb not found (install Android platform-tools)")
        remote = "/sdcard/basivo-promo-record.mp4"
        r = subprocess.run(["adb", "shell", "screenrecord", "--time-limit", str(secs), remote], capture_output=True, text=True)
        if r.returncode != 0:
            raise PromoError(f"adb screenrecord failed: {r.stderr.strip()[:200]}")
        subprocess.run(["adb", "pull", remote, str(tmp)], capture_output=True, check=False)
        subprocess.run(["adb", "shell", "rm", "-f", remote], capture_output=True, check=False)
    elif a.device == "mac":
        if platform.system() != "Darwin":
            raise PromoError("mac recording needs macOS")
        r = subprocess.run(["screencapture", "-v", "-V", str(secs), "-x", str(tmp)], capture_output=True, text=True)
        if r.returncode != 0:
            raise PromoError("screencapture failed; allow Screen Recording for your terminal in System Settings > Privacy & Security")
    if not tmp.is_file() or tmp.stat().st_size == 0:
        raise PromoError("no recording was produced")
    dst = _ingest(tmp, folder, a.name)
    tmp.unlink(missing_ok=True)
    audit("record", f"{a.device} {secs}s", dst.name)
    say(f"recorded {secs}s from {a.device}: {dst.relative_to(folder).as_posix()}")


def cmd_render(a):
    from promo_core.render import render
    sb = load(a.storyboard)
    fmts = a.formats.split(",") if a.formats else sb["formats"]
    bad = [f for f in fmts if f not in FORMATS]
    if bad:
        raise PromoError(f"unknown format(s) {bad}; use {list(FORMATS)}")
    folder = Path(a.storyboard).resolve().parent
    res = render(sb, a.storyboard, fmts, a.draft, log=progress_logger(folder))
    audit("render", folder, f"{', '.join(fmts)} {res['duration']:.1f}s")
    say(f"rendered {res['duration']:.1f}s video in {res['seconds']:.0f}s:")
    for fmt, path in res["outputs"].items():
        say(f"  {fmt}: {path}")
    say(f"  captions.srt, poster_*.png, manifest.json in {folder}")


def cmd_preview(a):
    from promo_core.render import contact_sheet
    folder = Path(a.storyboard).resolve().parent
    name = FORMATS[a.format]["file"]
    video = folder / name
    if not video.is_file():
        video = folder / name.replace(".mp4", "_draft.mp4")
    if not video.is_file():
        raise PromoError(f"no rendered {a.format} video in {folder}; render first")
    out = contact_sheet(video, folder / "work" / f"preview_{a.format}.jpg")
    say(f"preview: {out}")


def cmd_extract(a):
    from promo_core import extract
    folder = Path(a.storyboard).resolve().parent if a.storyboard.endswith(".json") else Path(a.storyboard).resolve()
    if not folder.is_dir():
        raise PromoError(f"folder not found: {folder}")
    if a.source.startswith(("http://", "https://")):
        session = None
        if a.session:
            from promo_core.capture import session_file
            session = session_file(a.source)
            if not session or not session.is_file():
                raise PromoError(f"no saved login for that site. Run: promo login {a.source}")
        brand, content, style = extract.from_url(a.source, folder, session)
    else:
        brand, content, style = extract.from_image(a.source, folder, is_logo=a.logo)
    audit("extract", a.source, f"style {style}")
    c = brand["colors"]
    say(f"brand: {brand['name']} ({c['theme']}) bg {c['bg']} fg {c['fg']} accent {c['accent']} accent2 {c['accent2']} font {brand['font']}"
        f" logo {brand['logo'] or 'none'}")
    if content.get("h1") or content.get("description"):
        say(f"h1: {content.get('h1') or '-'} | {content.get('description', '')[:140]}")
    say(f"found {len(content.get('headings', []))} headings, {len(content.get('features', []))} features, "
        f"{len(content.get('ctas', []))} CTAs, {len(content.get('stats', []))} stats -> brand/content.json")
    if brand["screens"]:
        say(f"screens: {', '.join(brand['screens'])}")
    say(f"style created: \"style\": \"{style}\" (promo-styles/{style}.json)")


def cmd_still(a):
    from promo_core.render import still
    sb = load(a.storyboard)
    folder = Path(a.storyboard).resolve().parent
    out = folder / "work" / f"still_{a.format}_{a.at:.2f}.jpg"
    path, scene, total = still(sb, a.storyboard, a.format, a.at, out)
    say(f"still at {a.at:.2f}s of {total:.1f}s (scene {scene['index']} {scene['type']}): {path}")


SAMPLE_SCENES = [
    {"type": "logo"},
    {"type": "headline", "eyebrow": "Style preview", "text": "Your story, *beautifully* told", "sub": "This is how motion, colour and type feel in this style."},
    {"type": "features", "title": "Everything in one place", "items": [
        {"icon": "⚡", "title": "Fast", "text": "Answers in seconds"}, {"icon": "🔒", "title": "Secure", "text": "Private by default"},
        {"icon": "✨", "title": "Delightful", "text": "Feels effortless"}]},
    {"type": "stat", "value": 3.4, "decimals": 1, "suffix": "x", "label": "faster than before"},
    {"type": "cta", "text": "Make it *yours*", "button": "Get started", "url": "example.com"},
]


def cmd_style_sample(a):
    from promo_core.render import render
    style = a.style
    if style.endswith(".json"):  # a style file anywhere: sample next to it so the lookup finds it
        sp = Path(style).resolve()
        if not sp.is_file() or sp.parent.name != "promo-styles":
            raise PromoError("a style file must live in a promo-styles/ folder")
        style, default_out = sp.stem, sp.parent.parent / "style-sample"
    else:
        default_out = HOME / "style-samples" / style
    out = Path(a.out) if a.out else default_out
    out.mkdir(parents=True, exist_ok=True)
    sb = {"version": 1, "product": a.product, "title": "sample", "style": style, "formats": ["16x9"], "scenes": SAMPLE_SCENES}
    if not all((MODELS / n).is_file() for n in KOKORO_FILES):
        sb["voice"] = {"engine": "none"}
    else:
        lines = ["Meet your new style.", "Every scene follows the same motion rules.", "Three ideas, one clear story.",
                 "Numbers count up on the beat.", "Make it yours."]
        for sc, line in zip(sb["scenes"], lines):
            sc["vo"] = line
    path = out / "storyboard.json"
    path.write_text(json.dumps(sb, indent=2) + "\n", encoding="utf-8")
    full = load(path)
    res = render(full, path, ["16x9"], draft=not a.full, log=progress_logger(out))
    audit("style-sample", style)
    say(f"sample of '{style}' ({res['duration']:.1f}s): {res['outputs']['16x9']}")


def cmd_doctor(a):
    checks = []
    checks.append(("python", sys.version.split()[0], True))
    for tool in ("ffmpeg", "ffprobe"):
        checks.append((tool, shutil.which(tool) or "missing (brew install ffmpeg / apt install ffmpeg)", bool(shutil.which(tool))))
    try:
        from playwright.sync_api import sync_playwright
        from promo_core.browser import launch
        with sync_playwright() as p:
            b, name = launch(p)
            checks.append(("browser", f"{name} {b.version}", True))
            b.close()
    except Exception as e:
        checks.append(("browser", str(e)[:160], False))
    models = all((MODELS / n).is_file() for n in KOKORO_FILES)
    checks.append(("kokoro voice", "installed" if models else "not installed (run: promo setup), or use voice engine 'say'/'none'", models))
    checks.append(("macOS say", "available" if shutil.which("say") else "not available", True))
    checks.append(("secret popup", "osascript" if shutil.which("osascript") else "tkinter/env/keychain", True))
    ok = True
    for name, detail, good in checks:
        ok &= good
        say(f"{'ok ' if good else 'ERR'} {name}: {detail}")
    say(f"basivo-promo {__version__}: {'ready' if ok else 'fix the ERR lines above'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="promo", description="basivo-promo: animated promo videos of your apps")
    ap.add_argument("--version", action="version", version=f"basivo-promo {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="create a promo folder with a starter storyboard")
    s.add_argument("product"); s.add_argument("--title"); s.add_argument("--style", default="midnight")
    s.add_argument("--url"); s.add_argument("--root", default="promos")
    s = sub.add_parser("validate", help="check a storyboard"); s.add_argument("storyboard")
    s = sub.add_parser("styles", help="list available styles"); s.add_argument("where", nargs="?")
    sub.add_parser("setup", help="download the Kokoro voice model (~120 MB, once)")
    s = sub.add_parser("login", help="log in yourself in a visible browser and save the session"); s.add_argument("url")
    s = sub.add_parser("capture", help="take screenshots by following the capture steps"); s.add_argument("storyboard")
    s = sub.add_parser("import", help="add an image or video to assets/"); s.add_argument("storyboard"); s.add_argument("file"); s.add_argument("--name")
    s = sub.add_parser("record", help="record iOS Simulator, Android device or Mac screen")
    s.add_argument("storyboard"); s.add_argument("device", choices=["ios", "android", "mac"])
    s.add_argument("--seconds", type=int, default=15); s.add_argument("--name", required=True)
    s = sub.add_parser("render", help="render the video"); s.add_argument("storyboard")
    s.add_argument("--formats", help="comma list of 16x9,9x16,1x1"); s.add_argument("--draft", action="store_true", help="half resolution, fast")
    s = sub.add_parser("preview", help="contact sheet of a rendered video"); s.add_argument("storyboard")
    s.add_argument("--format", default="16x9", choices=list(FORMATS))
    s = sub.add_parser("extract", help="adopt colours, font, logo and copy from a website or image")
    s.add_argument("storyboard", help="storyboard.json or its folder"); s.add_argument("source", help="https URL or image file")
    s.add_argument("--session", action="store_true", help="use the saved login for that site")
    s.add_argument("--logo", action="store_true", help="the image is the logo")
    s = sub.add_parser("still", help="render one frame (960px) at a time in seconds, for a quick check")
    s.add_argument("storyboard"); s.add_argument("--at", type=float, required=True)
    s.add_argument("--format", default="16x9", choices=list(FORMATS))
    s = sub.add_parser("style-sample", help="render a short sample of a style"); s.add_argument("style")
    s.add_argument("--out"); s.add_argument("--product", default="Acme"); s.add_argument("--full", action="store_true")
    sub.add_parser("doctor", help="check dependencies")
    a = ap.parse_args(argv)
    if getattr(a, "seconds", None) is not None and not 1 <= a.seconds <= 300:
        ap.error("--seconds must be 1 to 300")
    fn = globals()["cmd_" + a.cmd.replace("-", "_")]
    try:
        fn(a)
        return 0
    except StoryboardError as e:
        say("storyboard problems:")
        for line in e.errors:
            say(f"  - {line}")
        return 2
    except PromoError as e:
        audit(a.cmd, "", f"error: {e}")
        say(f"error: {e}")
        return 1
    except KeyboardInterrupt:
        say("cancelled")
        return 130
    except Exception as e:
        try:
            private_dir(HOME)
            ERROR_LOG.write_text(mask(traceback.format_exc()), encoding="utf-8")
            os.chmod(ERROR_LOG, 0o600)
        except OSError:
            pass
        audit(a.cmd, "", f"crash: {type(e).__name__}")
        say(f"unexpected error: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''} (details: {ERROR_LOG})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
