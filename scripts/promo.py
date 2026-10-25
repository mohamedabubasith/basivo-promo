# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#   "playwright>=1.47,<2",
#   "kokoro-onnx>=0.4,<1",
#   "soundfile>=0.12",
#   "numpy>=1.24",
# ]
# ///
"""basivo-promo: intake, assets, security and delivery for HyperFrames promo films. Run via scripts/promo."""
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

from promo_core import __version__, ff  # noqa: E402
from promo_core.brief import FORMATS, PLUGIN_STYLES, BriefError, list_styles, load, secret_names  # noqa: E402
from promo_core.mask_pii import mask  # noqa: E402
from promo_core.paths import (ERROR_LOG, HOME, KOKORO_BASE, KOKORO_FILES, MODELS, PromoError, audit,  # noqa: E402
                              private_dir, slug)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}


def say(*parts):
    """Every line Claude sees goes through the masker."""
    print(mask(" ".join(str(p) for p in parts), aggressive=False), flush=True)


def logger(folder):
    path = Path(folder) / ".promo" / "log.txt"
    path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {mask(msg)}\n")
    return log


def _folder(brief_path):
    return Path(brief_path).resolve().parent


# ---------- commands ----------

def cmd_new(a):
    folder = Path(a.root) / slug(a.product) / f"{date.today().isoformat()}-{slug(a.title or 'promo')}"
    if (folder / "promo.json").exists():
        raise PromoError(f"{folder}/promo.json already exists")
    for d in ("brand", "recordings", "captures", "audio", "images", "video"):
        (folder / "assets" / d).mkdir(parents=True, exist_ok=True)
    brief = {"version": 2, "product": a.product, "title": slug(a.title or "promo"), "brief": a.brief or "",
             "length": a.length, "formats": a.formats.split(","), "style": a.style}
    if not brief["brief"]:
        del brief["brief"]
    if a.url:
        brief["site"] = {"url": a.url, "login": "none", "mask": []}
    (folder / "promo.json").write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    (folder / ".gitignore").write_text(".promo/\n*/.hyperframes/\n*/node_modules/\n.rendering-*\n", encoding="utf-8")
    audit("new", folder)
    say(f"created {folder / 'promo.json'}")


def cmd_validate(a):
    b, path = load(a.brief)
    say(f"ok: {b['product']}, {b['length']}s, {', '.join(b['formats'])}, style {b['style']}, voice {b['voice']['engine']}, "
        f"music {(b['music'] or {}).get('style', 'none')}")
    if b.get("site"):
        names = secret_names(b)
        say(f"site: {b['site']['url']}; shots {len((b.get('shots') or {}).get('steps') or [])} steps; "
            f"flows {', '.join(f['name'] for f in b.get('flows') or []) or 'none'}{'; secrets: ' + ', '.join(names) if names else ''}")
    if b["taste"].get("direction"):
        say(f"direction: {b['taste']['direction']}")


def cmd_styles(a):
    base = Path(a.where or ".")
    for name, (path, desc) in list_styles(base.parent if base.is_file() else base).items():
        say(f"{name:12} {desc[:90]} ({'built-in' if path.parent == PLUGIN_STYLES else path.parent})")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def cmd_login(a):
    from promo_core.capture import login
    path = login(a.url)
    audit("login", a.url, "session saved")
    say(f"session saved for {path.stem} (only you can read it). Set \"login\": \"session\" in promo.json site.")


def cmd_extract(a):
    from promo_core import extract
    folder = _folder(a.brief) if a.brief.endswith(".json") else Path(a.brief).resolve()
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
    say(f"brand: {brand['name']} ({c['theme']}) bg {c['bg']} fg {c['fg']} accent {c['accent']} accent2 {c['accent2']} "
        f"font {brand['font']} logo {brand['logo'] or 'none'}")
    if content.get("h1") or content.get("description"):
        say(f"h1: {content.get('h1') or '-'} | {content.get('description', '')[:140]}")
    say(f"found {len(content.get('headings', []))} headings, {len(content.get('features', []))} features, "
        f"{len(content.get('ctas', []))} CTAs, {len(content.get('stats', []))} stats -> assets/brand/content.json")
    if brand["screens"]:
        say(f"screens: {', '.join(brand['screens'])}")
    say(f"taste profile written: promo-styles/{style}.json; scaffold applies these brand colours automatically")


def cmd_capture(a):
    from promo_core.capture import capture
    b, path = load(a.brief)
    if not b.get("shots"):
        raise PromoError("promo.json has no shots section")
    result, shots = capture(b, path, log=logger(path.parent))
    audit("capture", b["site"]["url"], f"{shots} screenshots")
    say(f"captured {shots} screenshot(s): {', '.join('assets/' + k for k in sorted(result))[:700]}")


def cmd_record_web(a):
    from promo_core.record_web import record
    b, path = load(a.brief)
    flows = [f for f in b.get("flows") or [] if not a.flow or f["name"] == a.flow]
    if not flows:
        raise PromoError("no matching flow in promo.json")
    for fl in flows:
        meta = record(b, path, fl, log=logger(path.parent))
        clicks = sum(1 for e in meta["events"] if e["type"] == "click")
        audit("record-web", f"{b['site']['url']} {fl['name']}", f"{meta['duration']:.1f}s")
        say(f"recorded {fl['name']}: {meta['src']} ({meta['duration']:.1f}s, {clicks} clicks, events in "
            f"assets/recordings/{fl['name']}.events.json)")


def cmd_screen(a):
    from promo_core.screen import write_block
    folder = _folder(a.brief)
    meta_path = folder / "assets" / "recordings" / f"{a.recording}.events.json"
    if not meta_path.is_file():
        raise PromoError(f"no recording named {a.recording}; run promo record-web first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for fmt in a.formats.split(","):
        proj = folder / fmt
        out, length, mount = write_block(proj, meta, a.name or f"screen-{a.recording}", chrome=a.chrome,
                                         idle_speed=a.idle_speed, zoom=a.zoom, fit=a.fit, lift=a.lift)
        say(f"{fmt}: {out.relative_to(folder)} ({length:.2f}s; recording {meta['duration']:.1f}s). Mount in index.html:")
        say(f"  {mount}")


def _ingest(src, folder, name):
    src = Path(src)
    if not src.is_file():
        raise PromoError(f"file not found: {src}")
    if slug(name) != name:
        raise PromoError("name must be a slug: lowercase letters, digits and -")
    ext = src.suffix.lower()
    if ext in VIDEO_EXT:
        dst = folder / "assets" / "video" / f"{name}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-an", "-vf", "fps=60,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-movflags", "+faststart", str(dst)], f"importing {src.name}")
    elif ext in IMAGE_EXT:
        dst = folder / "assets" / "images" / f"{name}{ext}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    else:
        raise PromoError(f"unsupported file type {ext}")
    return dst


def cmd_import(a):
    folder = _folder(a.brief)
    dst = _ingest(a.file, folder, a.name or slug(Path(a.file).stem))
    audit("import", dst.name)
    say(f"imported: {dst.relative_to(folder).as_posix()}")


def cmd_record(a):
    folder = _folder(a.brief)
    secs = a.seconds
    tmp = folder / ".promo" / f"record-{a.name}.{'mov' if a.device == 'mac' else 'mp4'}"
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


def cmd_scaffold(a):
    from promo_core.project import scaffold
    b, path = load(a.brief)
    made = scaffold(b, path.parent, a.formats.split(",") if a.formats else None)
    audit("scaffold", path.parent, ",".join(made) or "nothing new")
    for fmt in a.formats.split(",") if a.formats else b["formats"]:
        say(f"{fmt}: {path.parent / fmt} ({FORMATS[fmt]['w']}x{FORMATS[fmt]['h']}){' created' if fmt in made else ' exists'}; assets/ shared")


def cmd_voice(a):
    from promo_core.project import voice
    b, path = load(a.brief)
    lines = voice(b, path.parent, a.script)
    audit("voice", path.parent, f"{len(lines)} lines")
    for lid, src, secs in lines:
        say(f"{lid}: {src} {secs:.2f}s")


def cmd_music(a):
    from promo_core.project import music
    b, path = load(a.brief)
    src, bpm, beat = music(b, path.parent, a.seconds)
    audit("music", path.parent, f"{b['music']['style']} {bpm}bpm")
    say(f"music: {src} ({a.seconds:.0f}s, {b['music']['style']}, {bpm} BPM: a beat every {beat:.3f}s from 0)")


def cmd_render(a):
    from promo_core.project import render
    b, path = load(a.brief)
    res = render(b, path.parent, a.formats.split(",") if a.formats else None, a.quality, log=logger(path.parent))
    audit("render", path.parent, ", ".join(f"{k} {v['duration']}s" for k, v in res.items()))
    for fmt, r in res.items():
        say(f"{fmt}: {r['file']} ({r['width']}x{r['height']}, {r['duration']}s, {'; '.join(r['notes'])})")
    say(f"manifest: {path.parent / 'manifest.json'}")


def cmd_design(a):
    from promo_core.design import directions, write_profile
    best, dirs, candidates = directions(a.query, product_type=a.type)
    if a.write:
        if not 1 <= a.write <= len(dirs):
            raise PromoError(f"--write must be 1 to {len(dirs)}")
        where = (_folder(a.brief) / "promo-styles") if a.brief else (HOME / "styles")
        path = write_profile(dirs[a.write - 1], a.name or slug(dirs[a.write - 1]["style"]), where)
        audit("design", a.query, path.name)
        say(f"taste profile written: {path} (use \"style\": \"{path.stem}\")")
        return
    say(f"product type: {best['Product Type']} (UI UX Pro Max data)" + ("" if a.type else
        f"; other matches: {' | '.join(c['Product Type'] for c in candidates[1:5])}. Wrong? rerun with --type \"<one of them>\""))
    for i, d in enumerate(dirs, 1):
        p = d["palette"]
        say(f"{i}. {d['style']} | {d['font']['heading']} + {d['font']['body']} | bg {p['bg']} fg {p['fg']} accent {p['accent']} "
            f"accent2 {p['accent2']} | {d['personality']}, {d['transition']}, music {d['music']}")
        say(f"   motion: {d['motion'][:150]}")


def cmd_style_sample(a):
    from promo_core.project import render, scaffold
    from promo_core.brief import validate
    out = Path(a.out) if a.out else HOME / "style-samples" / a.style
    out.mkdir(parents=True, exist_ok=True)
    raw = {"version": 2, "product": a.product, "title": "sample", "style": a.style, "length": 10, "formats": ["16x9"]}
    (out / "promo.json").write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    b = validate(raw, out)
    scaffold(b, out)
    tpl = (Path(__file__).resolve().parents[1] / "templates" / "hyperframes" / "style-sample.html").read_text(encoding="utf-8")
    index = out / "16x9" / "index.html"
    from promo_core.project import _tokens
    tokens = "".join(f"{k}:{v};" for k, v in _tokens(b, out).items())
    pace = {"premium": 1.15, "corporate": 1.0, "playful": 0.9, "energetic": 0.8}.get(((b["taste"].get("brand") or {}).get("personality")), 1.0)
    index.write_text(tpl.replace("__TOKENS__", tokens).replace("__PRODUCT__", a.product).replace("__PACE__", str(pace)), encoding="utf-8")
    res = render(b, out, ["16x9"], "draft", log=logger(out))
    audit("style-sample", a.style)
    say(f"sample of '{a.style}': {res['16x9']['file']}")


def cmd_doctor(a):
    checks = [("python", sys.version.split()[0], True)]
    for tool in ("ffmpeg", "ffprobe", "node"):
        checks.append((tool, shutil.which(tool) or "missing", bool(shutil.which(tool))))
    try:
        v = subprocess.run(["node", "-p", "process.versions.node"], capture_output=True, text=True).stdout.strip()
        checks.append(("node 22+", v, int(v.split(".")[0]) >= 22))
    except (OSError, ValueError):
        checks.append(("node 22+", "not found", False))
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
    checks.append(("kokoro voice", "installed" if models else "not installed (promo setup), or use 'say'/'none'", True))
    hf_skill = any(Path(p).exists() for p in (Path.home() / ".claude/skills/hyperframes",)) or \
        any((Path.home() / ".claude/plugins/cache").glob("*/hyperframes/*/skills/hyperframes/SKILL.md"))
    checks.append(("hyperframes skills", "found" if hf_skill else "missing: /plugin marketplace add heygen-com/hyperframes, then "
                   "/plugin install hyperframes@hyperframes", hf_skill))
    ok = True
    for name, detail, good in checks:
        ok &= good
        say(f"{'ok ' if good else 'ERR'} {name}: {detail}")
    say(f"basivo-promo {__version__}: {'ready' if ok else 'fix the ERR lines above'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="promo", description="basivo-promo: promo films of your apps, built on HyperFrames")
    ap.add_argument("--version", action="version", version=f"basivo-promo {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="create a promo folder and promo.json")
    s.add_argument("product"); s.add_argument("--title"); s.add_argument("--brief"); s.add_argument("--url")
    s.add_argument("--length", type=int, default=45); s.add_argument("--formats", default="16x9")
    s.add_argument("--style", default="midnight"); s.add_argument("--root", default="promos")
    s = sub.add_parser("validate", help="check promo.json"); s.add_argument("brief")
    s = sub.add_parser("styles", help="list taste profiles"); s.add_argument("where", nargs="?")
    sub.add_parser("setup", help="download the Kokoro voice model (~120 MB, once)")
    s = sub.add_parser("login", help="log in yourself in a visible browser; saves session cookies"); s.add_argument("url")
    s = sub.add_parser("extract", help="adopt colours, font, logo and copy from a website or image")
    s.add_argument("brief", help="promo.json or its folder"); s.add_argument("source")
    s.add_argument("--session", action="store_true"); s.add_argument("--logo", action="store_true")
    s = sub.add_parser("capture", help="screenshots from the shots steps"); s.add_argument("brief")
    s = sub.add_parser("record-web", help="record flows as 60 fps video with cursor events"); s.add_argument("brief"); s.add_argument("--flow")
    s = sub.add_parser("screen", help="turn a recording into an edited HyperFrames block")
    s.add_argument("brief"); s.add_argument("recording"); s.add_argument("--name"); s.add_argument("--formats", default="16x9")
    s.add_argument("--chrome", default="auto", choices=["auto", "browser", "phone", "none"])
    s.add_argument("--idle-speed", type=float, default=3.0); s.add_argument("--zoom", type=float)
    s.add_argument("--fit", type=float, default=0.8, help="window height as a share of the frame (0.4-0.95)")
    s.add_argument("--lift", type=float, default=5, help="percent of the frame kept free at the bottom (captions)")
    s = sub.add_parser("import", help="add an image or video to assets/"); s.add_argument("brief"); s.add_argument("file"); s.add_argument("--name")
    s = sub.add_parser("record", help="record iOS Simulator, Android device or Mac screen")
    s.add_argument("brief"); s.add_argument("device", choices=["ios", "android", "mac"])
    s.add_argument("--seconds", type=int, default=15); s.add_argument("--name", required=True)
    s = sub.add_parser("scaffold", help="create one HyperFrames project per format"); s.add_argument("brief"); s.add_argument("--formats")
    s = sub.add_parser("voice", help="voiceover lines from a script JSON"); s.add_argument("brief"); s.add_argument("script")
    s = sub.add_parser("music", help="generate the music bed"); s.add_argument("brief"); s.add_argument("--seconds", type=float, required=True)
    s = sub.add_parser("render", help="render, verify audio and loudness, write manifest"); s.add_argument("brief")
    s.add_argument("--formats"); s.add_argument("--quality", default="delivery", choices=["draft", "looks", "delivery"])
    s = sub.add_parser("design", help="three style directions for a product (UI UX Pro Max data)"); s.add_argument("query")
    s.add_argument("--write", type=int, help="save direction N as a taste profile"); s.add_argument("--name")
    s.add_argument("--type", help="exact product type (from the matches it prints)")
    s.add_argument("--brief", help="promo.json: save into its promo-styles/ instead of ~/.basivo-promo/styles")
    s = sub.add_parser("style-sample", help="render a 10 s sample of a taste profile"); s.add_argument("style")
    s.add_argument("--out"); s.add_argument("--product", default="Acme")
    sub.add_parser("doctor", help="check dependencies")
    a = ap.parse_args(argv)
    if getattr(a, "seconds", None) is not None and not 1 <= a.seconds <= 300:
        ap.error("--seconds must be 1 to 300")
    fn = globals()["cmd_" + a.cmd.replace("-", "_")]
    try:
        fn(a)
        return 0
    except BriefError as e:
        say("promo.json problems:")
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
