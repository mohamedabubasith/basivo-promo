"""Find a Chromium-family browser for Playwright: Chrome, then Edge, then Playwright's Chromium."""
import os

from .paths import PromoError

ARGS = ["--allow-file-access-from-files", "--autoplay-policy=no-user-gesture-required", "--font-render-hinting=none",
        "--disable-lcd-text", "--force-color-profile=srgb", "--hide-scrollbars", "--mute-audio"]


# Hide cookie/consent banners without answering them (no consent is given or refused on the
# person's behalf) and unlock scrolling they block. CMPs load late, so it re-checks for 15 s.
CONSENT_JS = r"""(() => {
  const CMP = '#onetrust-banner-sdk,#onetrust-consent-sdk,#CybotCookiebotDialog,#usercentrics-root,.osano-cm-window,' +
    '#truste-consent-track,.fc-consent-root,#didomi-host,.cc-window,#cookie-law-info-bar,[id*=cookie-banner i],[class*=cookie-banner i]';
  const WORDS = /cookie|consent|gdpr|privacy preferences/i;
  let hid = false;
  const hide = (e) => { if (e.style.display !== 'none') { e.style.setProperty('display', 'none', 'important'); hid = true; } };
  const sweep = () => {
    if (!document.body) return;
    document.querySelectorAll(CMP).forEach(hide);
    for (const e of document.body.querySelectorAll('div,section,aside,dialog,form')) {
      const cs = getComputedStyle(e);
      if ((cs.position !== 'fixed' && cs.position !== 'sticky') || e.style.display === 'none') continue;
      const t = e.textContent || '';
      if (/cookie|consent|gdpr/i.test(e.id + ' ' + e.getAttribute('class')) || (WORDS.test(t) && t.length < 3000)) hide(e);
    }
    // Only undo a scroll lock when a banner was hidden; app shells set overflow:hidden on purpose.
    if (hid) for (const e of [document.documentElement, document.body])
      if (getComputedStyle(e).overflow === 'hidden') e.style.setProperty('overflow', 'auto', 'important');
  };
  let n = 0;
  const id = setInterval(() => { sweep(); if (++n > 30) clearInterval(id); }, 500);
  document.addEventListener('DOMContentLoaded', sweep);
})();"""


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
