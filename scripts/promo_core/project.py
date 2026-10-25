"""A promo folder: promo.json, shared assets/, and one HyperFrames project per format."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, ff
from .brief import FORMATS
from .fonts import BUNDLED, font_face_css
from .paths import PLUGIN_ROOT, PromoError

HF = PLUGIN_ROOT / "scripts" / "hf"
ASSET_DIRS = ("brand", "recordings", "captures", "audio", "images", "video")


def hf(args, cwd, what, timeout=1800):
    r = subprocess.run(["sh", str(HF), *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        tail = "\n".join((r.stderr or r.stdout).strip().splitlines()[-6:])
        raise PromoError(f"{what} failed: {tail}")
    return r.stdout


def _tokens(brief, folder):
    """Brand tokens from the adopted brand (brand/brand.json), else the taste profile."""
    b = dict((brief.get("taste") or {}).get("brand") or {})
    bj = folder / "assets" / "brand" / "brand.json"
    if bj.is_file():
        adopted = json.loads(bj.read_text(encoding="utf-8"))
        b.update({k: v for k, v in (adopted.get("colors") or {}).items() if k in ("bg", "fg", "accent", "accent2", "muted")})
        b["font"] = adopted.get("font") or b.get("font")
    return {"--ground": b.get("bg", "#0b0d12"), "--ink": b.get("fg", "#ffffff"), "--accent": b.get("accent", "#6c5cff"),
            "--accent-2": b.get("accent2", "#ff5c8a"), "--muted": b.get("muted", "#9aa3b2"),
            "--font-display": ", ".join(dict.fromkeys([f'"{b.get("font") or "Inter"}"', '"Inter"', "sans-serif"]))}


def _apply_tokens(index, tokens):
    html = index.read_text(encoding="utf-8")
    block = ":root {\n" + "".join(f"        {k}: {v};\n" for k, v in tokens.items()) + "      }"
    html, n = re.subn(r":root\s*\{[^}]*\}", block, html, count=1)
    if n == 0:
        html = html.replace("<style>", "<style>\n      " + block, 1)
    html = html.replace("/* Placeholders: replace all three with the film's own palette and display face. */",
                        "/* Brand tokens from basivo-promo (promo.json + assets/brand). */")
    index.write_text(html, encoding="utf-8")


def _link_assets(project, shared):
    target = project / "assets"
    if target.is_symlink() or target.exists():
        if target.is_symlink() or not any(target.iterdir()):
            target.unlink() if target.is_symlink() else target.rmdir()
        else:
            return
    try:
        os.symlink(os.path.relpath(shared, project), target, target_is_directory=True)
    except OSError:  # Windows without symlink rights: fall back to a copy
        shutil.copytree(shared, target)


def scaffold(brief, folder, formats=None):
    folder = Path(folder).resolve()
    shared = folder / "assets"
    for d in ASSET_DIRS:
        (shared / d).mkdir(parents=True, exist_ok=True)
    made = []
    for fmt in formats or brief["formats"]:
        proj = folder / fmt
        if not (proj / "hyperframes.json").is_file():
            hf(["init", fmt, "--example", "blank", "--resolution", FORMATS[fmt]["resolution"], "--non-interactive"], folder,
               f"creating the {fmt} project")
            tokens = _tokens(brief, folder)
            family = tokens["--font-display"].split(",")[0].strip().strip('"')
            faces = font_face_css(family, shared)
            if not faces and family.lower() not in BUNDLED:
                # Proprietary or unknown brand font: the renderer cannot load it, so say Inter honestly.
                tokens["--font-display"] = '"Inter", sans-serif'
            _apply_tokens(proj / "index.html", tokens)
            if faces:  # a brand font HyperFrames does not bundle: ship the files with the project
                idx = proj / "index.html"
                idx.write_text(idx.read_text(encoding="utf-8").replace("<style>", "<style>\n" + faces, 1), encoding="utf-8")
            made.append(fmt)
        _link_assets(proj, shared)
    return made


def voice(brief, folder, script_path):
    """Voice lines from a script file: [{"id": "hook", "text": "..."}] -> assets/audio/vo-<id>.wav."""
    from .audio import Voice, _trim, VO_RATE
    import soundfile as sf

    folder = Path(folder)
    lines = json.loads(Path(script_path).read_text(encoding="utf-8"))
    if not isinstance(lines, list) or not all(isinstance(l, dict) and re.match(r"^[a-z0-9-]{1,30}$", str(l.get("id", "")))
                                              and isinstance(l.get("text"), str) and 0 < len(l["text"]) <= 400 for l in lines):
        raise PromoError('the script must be a list of {"id": "slug", "text": "line (max 400 chars)"}')
    if brief["voice"]["engine"] == "none":
        raise PromoError("voice engine is 'none' in promo.json")
    v = Voice(brief["voice"])
    out = []
    audio_dir = folder / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for line in lines:
        key = hashlib.sha256(f"{brief['voice']}|{line['text']}".encode()).hexdigest()[:10]
        path = audio_dir / f"vo-{line['id']}.wav"
        stamp = audio_dir / f".vo-{line['id']}.key"
        if not (path.is_file() and stamp.is_file() and stamp.read_text() == key):
            samples = _trim(v.synth(line["text"]))
            if samples.size == 0:
                raise PromoError(f"the voice engine produced silence for '{line['id']}'")
            sf.write(str(path), samples, VO_RATE, subtype="PCM_16")
            stamp.write_text(key)
        info = sf.info(str(path))
        out.append((line["id"], f"assets/audio/{path.name}", round(info.frames / info.samplerate, 2)))
    return out


def music(brief, folder, seconds):
    from playwright.sync_api import sync_playwright
    from .audio import music as ditty
    from .browser import launch

    if not brief["music"]:
        raise PromoError("music is null in promo.json")
    work = Path(folder) / "assets" / "audio"
    with sync_playwright() as p:
        browser, _ = launch(p)
        try:
            path = ditty({"music": brief["music"]}, seconds - 1.5, work, browser)
        finally:
            browser.close()
    final = work / "music.wav"
    shutil.move(str(path), final)
    beat = 60.0 / brief["music"]["bpm"]
    return f"assets/audio/{final.name}", brief["music"]["bpm"], beat


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _loudness(path):
    try:
        m = ff.loudnorm_measure(path)
        return float(m["input_i"]), float(m["input_tp"]), m
    except (PromoError, ValueError, KeyError):
        return None, None, None


def render(brief, folder, formats=None, quality="delivery", log=print):
    folder = Path(folder).resolve()  # HyperFrames runs inside each format folder
    results = {}
    for fmt in formats or brief["formats"]:
        proj = folder / fmt
        if not (proj / "hyperframes.json").is_file():
            raise PromoError(f"no {fmt} project; run promo scaffold first")
        name = FORMATS[fmt]["file"] if quality == "delivery" else FORMATS[fmt]["file"].replace(".mp4", f"_{quality}.mp4")
        out = folder / name
        tmp = folder / f".rendering-{fmt}.mp4"
        log(f"{fmt}: rendering ({quality})")
        hf(["render", "--quality", quality, "--output", str(tmp)], proj, f"rendering {fmt}", timeout=3600)
        info = ff.probe(tmp)
        if info["duration"] <= 0:
            tmp.unlink(missing_ok=True)
            raise PromoError(f"{fmt}: the render is empty")
        notes = []
        if info["audio"]:
            lufs, tp, m = _loudness(tmp)
            if lufs is not None and (abs(lufs + 14) > 1.0 or tp > -1.0):
                # Two-pass loudness to -14 LUFS, -1.5 dBTP; the picture is copied untouched.
                ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                      f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
                fixed = folder / f".rendering-{fmt}-ln.mp4"
                ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(tmp), "-map", "0", "-c:v", "copy", "-af", ln, "-ar", "48000",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(fixed)], "normalising loudness")
                tmp.unlink()
                fixed.rename(tmp)
                notes.append(f"loudness {lufs:.1f} -> -14 LUFS")
            else:
                notes.append(f"loudness {lufs:.1f} LUFS" if lufs is not None else "loudness n/a")
        else:
            notes.append("NO AUDIO TRACK (add <audio> to the composition)")
        tmp.replace(out)
        results[fmt] = {"file": out, "duration": round(info["duration"], 2), "width": info["width"], "height": info["height"],
                        "audio": info["audio"], "notes": notes}
    _manifest(brief, folder, results, quality)
    return results


def _manifest(brief, folder, results, quality):
    path = folder / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    files = old.get("files", {})
    for r in results.values():
        f = r["file"]
        files[f.name] = {"bytes": f.stat().st_size, "sha256": _sha(f), "duration": r["duration"],
                         "size": f"{r['width']}x{r['height']}", "audio": r["audio"], "quality": quality}
    manifest = {"tool": "basivo-promo", "version": __version__, "engine": "HyperFrames (pinned in scripts/hf)",
                "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "product": brief["product"],
                "style": brief["style"], "voice": brief["voice"], "music": brief["music"], "files": files}
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
