"""Find a Chromium-family browser for Playwright: Chrome, then Edge, then Playwright's Chromium."""
import os

from .paths import PromoError

ARGS = ["--allow-file-access-from-files", "--autoplay-policy=no-user-gesture-required", "--font-render-hinting=none",
        "--disable-lcd-text", "--force-color-profile=srgb", "--hide-scrollbars", "--mute-audio"]


def launch(p, headless=True):
    """Return (browser, name). PROMO_BROWSER may be a channel (chrome, msedge, chromium) or a path."""
    want = os.environ.get("PROMO_BROWSER", "").strip()
    order = [want] if want else ["chrome", "msedge", "chromium"]
    errors = []
    for name in order:
        try:
            if os.path.sep in name:
                return p.chromium.launch(executable_path=name, headless=headless, args=ARGS), "custom"
            if name == "chromium":
                return p.chromium.launch(headless=headless, args=ARGS), "chromium"
            return p.chromium.launch(channel=name, headless=headless, args=ARGS), name
        except Exception as e:  # playwright raises plain Error for a missing channel
            errors.append(f"{name}: {str(e).splitlines()[0][:120]}")
    raise PromoError("no usable browser. Install Google Chrome, or run: uvx playwright install chromium. Tried: " + "; ".join(errors))
