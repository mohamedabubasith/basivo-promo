# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.47"]
# ///
"""BP-001 spike: seek a CSS-animated page frame by frame and pipe JPEGs to ffmpeg."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / ".spikes"
W, H, FPS, SECONDS = 1920, 1080, 30, 10


def main():
    OUT.mkdir(exist_ok=True)
    clip = OUT / "clip.mp4"
    if not clip.exists():  # stand-in for a captured app recording
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate={FPS}:duration=8",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", str(clip)], check=True)
    shutil.copy(HERE / "render_spike.html", OUT / "index.html")

    out = OUT / "render_spike.mp4"
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                           "-c:v", "libx264", "-profile:v", "high", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required", "--allow-file-access-from-files"])
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto((OUT / "index.html").as_uri())
        page.evaluate("window.ready")
        for n in range(FPS * SECONDS):
            page.evaluate("t => window.seek(t)", n / FPS)
            ff.stdin.write(page.screenshot(type="jpeg", quality=92))
        browser.close()
    ff.stdin.close()
    ff.wait()
    print(f"{out} frames={FPS * SECONDS} wall={time.time() - t0:.1f}s")
    return ff.returncode


if __name__ == "__main__":
    sys.exit(main())
