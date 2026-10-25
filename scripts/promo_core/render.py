"""Render a storyboard to finished MP4s: voice, music, frames, mix, mux, captions, manifest."""
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, audio, ff
from .browser import launch
from .paths import TEMPLATES, VENDOR, PromoError
from .storyboard import FORMATS, caption_cues, srt, timeline


def _file_url(base, rel):
    return (base / rel).resolve().as_uri()


def _host(sb):
    url = (sb.get("capture") or {}).get("url") or ""
    return urlparse(url).hostname or ""


def _page_data(sb, base, tl, fmt, cues):
    scenes = []
    for sc in sb["scenes"]:
        s = dict(sc)
        for k in ("media", "before", "after"):
            if k in s:
                s[k] = _file_url(base, s[k])
        s.pop("vo", None)
        scenes.append(s)
    brand = dict(sb["brand"])
    if brand.get("logo"):
        brand["logo"] = _file_url(base, brand["logo"])
    f = FORMATS[fmt]
    return {"format": fmt, "layout": f["layout"], "w": f["w"], "h": f["h"], "fps": sb["fps"], "total": tl["total"],
            "speed": tl["speed"], "product": sb["product"], "host": _host(sb), "brand": brand, "look": sb["look"], "scenes": scenes,
            "timeline": tl["scenes"], "captions": cues if sb["captions"]["burn"] else []}


def _css_vars(data):
    b = data["brand"]
    font = '"PromoInter"' if b["font"] == "Inter" else f'"{b["font"]}", "PromoInter"'
    return (f":root{{--W:{data['w']}px;--H:{data['h']}px;--bg:{b['bg']};--fg:{b['fg']};--accent:{b['accent']};"
            f"--accent2:{b['accent2']};--muted:{b['muted']};--font:{font}, system-ui, sans-serif;}}")


def _frames(browser, data, out, poster_at, draft, log):
    w, h, fps, total = data["w"], data["h"], data["fps"], data["total"]
    scale = 0.5 if draft else 1
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(script="window.__PROMO__ = " + json.dumps(data) + ";")
    page.goto((TEMPLATES / "stage.html").as_uri())
    page.add_style_tag(content=_css_vars(data))
    try:
        page.evaluate("window.__ready")
    except Exception as e:
        raise PromoError(f"stage failed to load: {str(e).splitlines()[0][:200]}")
    if errors:
        raise PromoError(f"stage script error: {errors[0][:200]}")
    n = int(round(total * fps))
    vf = "scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=full:out_range=tv,format=yuv420p"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg",
           "-i", "-", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast" if draft else "slow", "-crf", "26" if draft else "17",
           "-profile:v", "high", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv", "-r", str(fps), "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    poster_n = min(n - 1, int(poster_at * fps))
    poster = None
    t0 = time.time()
    try:
        for i in range(n):
            page.evaluate("t => window.__seek(t)", i / fps)
            frame = page.screenshot(type="jpeg", quality=80 if draft else 95)
            proc.stdin.write(frame)
            if i == poster_n:
                poster = page.screenshot(type="png")
            if i % (fps * 5) == 0:
                log(f"{data['format']}: frame {i}/{n} ({time.time() - t0:.0f}s)")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    finally:
        rc = proc.wait()
        ctx.close()
    if rc != 0:
        raise PromoError(f"video encode failed: {proc.stderr.read().decode(errors='replace').strip()[-300:]}")
    if errors:
        raise PromoError(f"stage script error during render: {errors[0][:200]}")
    return poster


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render(sb, sb_path, formats=None, draft=False, log=print):
    from playwright.sync_api import sync_playwright  # heavy import, only when rendering

    base = Path(sb_path).resolve().parent
    work = base / "work"
    work.mkdir(exist_ok=True)
    formats = formats or sb["formats"]
    started = time.time()

    log("voiceover")
    vo = audio.voiceover(sb, work)
    tl = timeline(sb, [s for _, s in vo])
    cues = caption_cues(sb, tl)
    total = tl["total"]
    vo_path = audio.vo_track(vo, tl, work)

    outputs = {}
    with sync_playwright() as p:
        browser, browser_name = launch(p)
        try:
            music_path = None
            if sb["music"]:
                log("music")
                music_path = audio.music(sb, total, work, browser)
            sfx_path = audio.sfx_track(tl, work) if sb["sfx"] else None
            mix = audio.mix(vo_path, music_path, total, (sb["music"] or {}).get("volume", 0.5), work, sfx_path)
            poster_at = tl["scenes"][-1]["start"] + min(2.2, tl["scenes"][-1]["dur"] * 0.6)
            for fmt in formats:
                data = _page_data(sb, base, tl, fmt, cues)
                silent = work / f"video_{fmt}.mp4"
                poster = _frames(browser, data, silent, poster_at, draft, log)
                name = FORMATS[fmt]["file"]
                if draft:
                    name = name.replace(".mp4", "_draft.mp4")
                final = base / name
                if mix:
                    ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(silent), "-i", str(mix), "-map", "0:v", "-map", "1:a",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
                            "-movflags", "+faststart", str(final)], "muxing audio")
                else:
                    shutil.copyfile(silent, final)
                if poster:
                    (base / f"poster_{fmt}.png").write_bytes(poster)
                outputs[fmt] = final
        finally:
            browser.close()

    (base / "captions.srt").write_text(srt(cues), encoding="utf-8")
    manifest = {
        "tool": "basivo-promo", "version": __version__, "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "render_seconds": round(time.time() - started, 1), "draft": draft, "duration": total, "fps": sb["fps"],
        "browser": browser_name, "platform": f"{platform.system()} {platform.machine()}", "python": sys.version.split()[0],
        "voice": {k: sb["voice"][k] for k in ("engine", "voice", "speed")},
        "music": ({"engine": "@simpllyf/ditty 0.6.0", **sb["music"]} if sb["music"] else None),
        "loudness": "-14 LUFS integrated, -1.5 dBTP" if mix else None,
        "scenes": [{"type": s["type"], "start": s["start"], "duration": s["dur"], "transition": s["transition"]} for s in tl["scenes"]],
        "files": {},
    }
    for p_ in sorted(base.glob("*")):
        if p_.is_file() and p_.suffix in (".mp4", ".png", ".srt"):
            manifest["files"][p_.name] = {"bytes": p_.stat().st_size, "sha256": _sha(p_)}
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"outputs": outputs, "duration": total, "seconds": time.time() - started, "dir": base}


def still(sb, sb_path, fmt, at, out, width=960):
    """One frame at time `at`, scaled to `width`, without rendering the whole video."""
    from playwright.sync_api import sync_playwright

    base = Path(sb_path).resolve().parent
    work = base / "work"
    work.mkdir(exist_ok=True)
    vo = audio.voiceover(sb, work)
    tl = timeline(sb, [s for _, s in vo])
    data = _page_data(sb, base, tl, fmt, caption_cues(sb, tl))
    at = max(0.0, min(at, tl["total"] - 1 / sb["fps"]))
    with sync_playwright() as p:
        browser, _ = launch(p)
        try:
            ctx = browser.new_context(viewport={"width": data["w"], "height": data["h"]}, device_scale_factor=width / data["w"])
            page = ctx.new_page()
            page.add_init_script(script="window.__PROMO__ = " + json.dumps(data) + ";")
            page.goto((TEMPLATES / "stage.html").as_uri())
            page.add_style_tag(content=_css_vars(data))
            page.evaluate("window.__ready")
            page.evaluate("t => window.__seek(t)", at)
            page.screenshot(path=str(out), type="jpeg", quality=85)
        finally:
            browser.close()
    scene = next((s for s in reversed(tl["scenes"]) if s["start"] <= at), tl["scenes"][0])
    return out, scene, tl["total"]


def contact_sheet(video, out, frames=6, width=800):
    """Small preview grid of evenly spaced frames, for a cheap visual check."""
    info = ff.probe(video)
    d = info["duration"] or 1
    times = [d * (i + 0.5) / frames for i in range(frames)]
    sel = "+".join(f"lt(prev_pts*TB\\,{t:.2f})*gte(pts*TB\\,{t:.2f})" for t in times)
    cols = 3
    tile_w = width // cols
    ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(video), "-vf", f"select='{sel}',scale={tile_w}:-2,tile={cols}x{(frames + cols - 1) // cols}",
            "-frames:v", "1", "-q:v", "4", str(out)], "making contact sheet")
    return out
