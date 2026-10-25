"""Voiceover lines (Kokoro-82M or macOS say) and music (@simpllyf/ditty). HyperFrames mixes them."""
import base64
import math
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from . import ff
from .paths import KOKORO_FILES, MODELS, VENDOR, PromoError

VO_RATE = 24000


def _trim(samples, threshold=0.004, pad=0.04):
    """Cut leading/trailing silence so scene timing follows the actual speech."""
    idx = np.flatnonzero(np.abs(samples) > threshold)
    if idx.size == 0:
        return samples[:0]
    p = int(pad * VO_RATE)
    return samples[max(0, idx[0] - p): idx[-1] + p]


class Voice:
    def __init__(self, cfg):
        self.engine, self.voice, self.speed = cfg["engine"], cfg.get("voice") or "", float(cfg.get("speed", 1.0))
        self._kokoro = None

    def _load_kokoro(self):
        if self._kokoro is None:
            missing = [n for n in KOKORO_FILES if not (MODELS / n).is_file()]
            if missing:
                raise PromoError("the Kokoro voice model is not installed. Run: promo setup (downloads ~120 MB once)")
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(str(MODELS / "kokoro-v1.0.int8.onnx"), str(MODELS / "voices-v1.0.bin"))
            voices = self._kokoro.get_voices()
            if self.voice not in voices:
                sample = ", ".join(v for v in voices if v[:2] in ("af", "am", "bf", "bm"))
                raise PromoError(f"unknown Kokoro voice '{self.voice}'. English voices: {sample}")
        return self._kokoro

    def synth(self, text):
        if self.engine == "kokoro":
            k = self._load_kokoro()
            lang = "en-gb" if self.voice.startswith("b") else "en-us"
            samples, rate = k.create(text, voice=self.voice, speed=self.speed, lang=lang)
            samples = np.asarray(samples, dtype=np.float32)
            if rate != VO_RATE:
                raise PromoError(f"unexpected Kokoro sample rate {rate}")
            return samples
        if self.engine == "say":
            if platform.system() != "Darwin" or not shutil.which("say"):
                raise PromoError("voice engine 'say' needs macOS; use 'kokoro' or 'none'")
            with tempfile.TemporaryDirectory() as td:
                txt, aiff, wav = Path(td, "line.txt"), Path(td, "line.aiff"), Path(td, "line.wav")
                txt.write_text(text, encoding="utf-8")  # -f avoids passing copy as argv
                cmd = ["say", "-f", str(txt), "-o", str(aiff)]
                if self.voice:
                    cmd += ["-v", self.voice]
                if self.speed != 1.0:
                    cmd += ["-r", str(int(175 * self.speed))]
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    raise PromoError(f"say failed: {r.stderr.strip()[:200]}")
                ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(aiff), "-ac", "1", "-ar", str(VO_RATE), "-c:a", "pcm_f32le", str(wav)], "converting say output")
                samples, _ = sf.read(str(wav), dtype="float32")
                return samples
        raise PromoError(f"unknown voice engine {self.engine}")


DITTY_JS = """async ({style, seed, seconds, bpm}) => {
  const { sampleRate, channels } = await Ditty.renderOffline({ style, seed, seconds, bpm });
  const wav = Ditty.encodeWav(channels, sampleRate);
  let s = "";
  for (let i = 0; i < wav.length; i += 0x8000) s += String.fromCharCode.apply(null, wav.subarray(i, i + 0x8000));
  return btoa(s);
}"""


def music(sb, total, work, browser):
    """Render the ditty track for this video (cached by style, seed and length)."""
    m = sb["music"]
    seconds = int(math.ceil(total + 1.5))
    path = work / f"music_{m['style']}_{m['seed']}_{m['bpm']}_{seconds}.wav"
    if path.is_file():
        return path
    page = browser.new_page()
    try:
        page.add_script_tag(path=str(VENDOR / "ditty.global.js"))
        data = page.evaluate(DITTY_JS, {"style": m["style"], "seed": m["seed"], "seconds": seconds, "bpm": m["bpm"]})
    finally:
        page.close()
    path.write_bytes(base64.b64decode(data))
    return path
