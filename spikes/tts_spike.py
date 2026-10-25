# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["kokoro-onnx>=0.4", "soundfile"]
# ///
"""BP-003 spike: one voiceover line with Kokoro-82M int8 (ONNX, CPU) and macOS `say`."""
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import soundfile as sf

OUT = Path(__file__).parent.parent / ".spikes"
MODELS = Path.home() / ".basivo-promo" / "models"
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ["kokoro-v1.0.int8.onnx", "voices-v1.0.bin"]
LINE = "Meet Acme. Ship your releases twice as fast, with every check automated and every team in sync."


def fetch():
    MODELS.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = MODELS / name
        if not dest.exists():
            urllib.request.urlretrieve(BASE + name, dest.with_suffix(".part"))
            dest.with_suffix(".part").rename(dest)
        print(f"{name} {dest.stat().st_size / 1e6:.0f}MB")


def main():
    OUT.mkdir(exist_ok=True)
    fetch()
    from kokoro_onnx import Kokoro

    t0 = time.time()
    kokoro = Kokoro(str(MODELS / FILES[0]), str(MODELS / FILES[1]))
    load = time.time() - t0
    for voice in ("af_heart", "am_michael"):
        t0 = time.time()
        samples, rate = kokoro.create(LINE, voice=voice, speed=1.0, lang="en-us")
        synth = time.time() - t0
        sf.write(OUT / f"vo_kokoro_{voice}.wav", samples, rate)
        print(f"kokoro {voice}: load={load:.1f}s synth={synth:.1f}s audio={len(samples) / rate:.1f}s rate={rate}")

    if shutil.which("say"):
        t0 = time.time()
        subprocess.run(["say", "-o", str(OUT / "vo_say.aiff"), LINE], check=True)
        print(f"say: synth={time.time() - t0:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
