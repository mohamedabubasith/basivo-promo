"""ffmpeg / ffprobe helpers. Standard library only."""
import json
import re
import shutil
import subprocess
from pathlib import Path

from .mask_pii import mask
from .paths import PromoError


def need(tool="ffmpeg"):
    if not shutil.which(tool):
        raise PromoError(f"{tool} not found. Install ffmpeg (macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)")


def run(args, what):
    need(args[0])
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-4:])
        raise PromoError(f"{what} failed: {mask(tail)}")
    return r


def probe(path):
    need("ffprobe")
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], f"reading {Path(path).name}")
    info = json.loads(r.stdout)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    rate = v.get("r_frame_rate", "0/1").split("/")
    return {"duration": float(info.get("format", {}).get("duration", 0) or 0), "width": v.get("width"),
            "height": v.get("height"), "codec": v.get("codec_name"), "profile": v.get("profile"),
            "fps": round(int(rate[0]) / max(1, int(rate[1])), 3) if len(rate) == 2 else None,
            "audio": bool(a), "audio_codec": a.get("codec_name") if a else None}


def ingest_video(src, dst, fps=30, max_side=2160):
    """Normalise any clip to silent VP9 WebM with frequent keyframes, so every browser can
    decode it and frame-exact seeking stays fast."""
    vf = (f"fps={fps},scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))',"
          "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-an", "-vf", vf, "-c:v", "libvpx-vp9", "-crf", "24", "-b:v", "0",
         "-g", str(fps // 2), "-deadline", "good", "-cpu-used", "4", "-row-mt", "1", str(dst)], f"importing {Path(src).name}")


def loudnorm_measure(path, target=-14.0, tp=-1.5, lra=11.0):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if r.returncode != 0 or not m:
        raise PromoError("loudness measurement failed")
    return json.loads(m.group(0))
