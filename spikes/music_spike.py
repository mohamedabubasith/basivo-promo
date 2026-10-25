# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.47"]
# ///
"""BP-002 spike: render @simpllyf/ditty offline in headless Chrome and save a WAV."""
import base64
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
OUT = ROOT / ".spikes"

RENDER = """async ({style, seed, seconds}) => {
  const { sampleRate, channels } = await Ditty.renderOffline({ style, seed, seconds });
  const wav = Ditty.encodeWav(channels, sampleRate);
  let s = "";
  for (let i = 0; i < wav.length; i += 0x8000) s += String.fromCharCode.apply(null, wav.subarray(i, i + 0x8000));
  return btoa(s);
}"""


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        page.add_script_tag(path=str(ROOT / "vendor" / "ditty.global.js"))
        for style in ("peppy", "cinematic"):
            t0 = time.time()
            wav = base64.b64decode(page.evaluate(RENDER, {"style": style, "seed": 7, "seconds": 60}))
            path = OUT / f"music_{style}.wav"
            path.write_bytes(wav)
            print(f"{path.name} {len(wav) / 1e6:.1f}MB render={time.time() - t0:.1f}s")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
