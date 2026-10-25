"""Record a real flow in the product as smooth 60 fps video plus a cursor/click event log.

The browser is driven like a person: the mouse travels on eased paths, typing is visible
character by character, scrolling is gradual. Frames come from the CDP screencast at device
pixel ratio 2 (crisp when the edit zooms in). The headless page has no visible pointer; the
event log lets the promo-screen block draw an oversized, smoothed cursor and zoom to clicks.
"""
import base64
import json
import math
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .browser import CONSENT_JS, launch
from .capture import resolve_url, session_file, _same_site
from .paths import PromoError
from .secrets import Secrets
from .brief import SECRET_REF

VIEWPORTS = {"desktop": {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 2},
             "laptop": {"viewport": {"width": 1280, "height": 800}, "device_scale_factor": 2},
             # iPhone 15 Pro: 393x852 CSS px. Recorded at 2x (786x1704) to keep files sane.
             "mobile": {"viewport": {"width": 393, "height": 852}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True,
                        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                                      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}}
FPS = 60


def _ease(t):  # easeInOutCubic: how a hand moves a mouse
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Recorder:
    def __init__(self, page, cdp, vp, masks, secrets):
        self.page, self.cdp, self.vp, self.masks, self.secrets = page, cdp, vp, list(masks), secrets
        self.frames, self.events = [], []
        self.mouse = (vp["width"] * 0.5, vp["height"] * 0.62)
        self.t0 = None
        cdp.on("Page.screencastFrame", self._frame)

    def _frame(self, params):
        self.frames.append((params["metadata"]["timestamp"], params["data"]))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass

    def now(self):
        return time.time() - self.t0

    def log(self, kind, **kw):
        self.events.append({"t": round(self.now(), 3), "type": kind, **kw})

    def norm(self, x, y):
        return round(x / self.vp["width"], 4), round(y / self.vp["height"], 4)

    def start(self):
        self.page.wait_for_timeout(300)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1,
                                               "maxWidth": self.vp["width"] * 2, "maxHeight": self.vp["height"] * 2})
        self.t0 = time.time()
        self.page.wait_for_timeout(250)
        self.log("move", x=self.norm(*self.mouse)[0], y=self.norm(*self.mouse)[1])

    def stop(self):
        self.page.wait_for_timeout(400)
        self.cdp.send("Page.stopScreencast")
        return self.now()

    def persist_css(self, css):
        """Inject CSS into the current page and every page loaded after it (navigations included)."""
        js = ("(() => { const add = () => { const s = document.createElement('style'); s.textContent = %s; "
              "(document.head || document.documentElement).appendChild(s); }; "
              "document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', add) : add(); })()") % json.dumps(css)
        self.page.context.add_init_script(script=js)
        self.page.add_style_tag(content=css)

    def apply_masks(self):
        css = "".join(f"{s}{{filter:blur(12px)!important}}" for s in self.masks)
        if css:
            self.persist_css(css)

    def move_to(self, x, y, seconds=None):
        x0, y0 = self.mouse
        dist = math.hypot(x - x0, y - y0)
        seconds = seconds or min(1.1, 0.35 + dist / 1800)
        steps = max(8, int(seconds * 60))
        for i in range(1, steps + 1):
            k = _ease(i / steps)
            # A slight arc, like a wrist, instead of a ruler-straight line.
            arc = math.sin(math.pi * i / steps) * min(40, dist * 0.06)
            px, py = x0 + (x - x0) * k, y0 + (y - y0) * k - arc
            self.page.mouse.move(px, py)
            if i % 3 == 0 or i == steps:
                nx, ny = self.norm(px, py)
                self.log("move", x=nx, y=ny)
            self.page.wait_for_timeout(int(1000 * seconds / steps))
        self.mouse = (x, y)

    def target(self, sel):
        # Skip hidden duplicates (mobile menus), unless the author picked one with nth=.
        loc = self.page.locator(sel if "nth=" in sel else f"{sel} >> visible=true").first
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        if not box:
            raise PromoError(f"'{sel}' is not visible")
        return loc, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def click(self, sel):
        loc, x, y = self.target(sel)
        self.move_to(x, y)
        self.page.wait_for_timeout(120)
        nx, ny = self.norm(x, y)
        self.log("click", x=nx, y=ny)
        self.page.mouse.down()
        self.page.wait_for_timeout(70)
        self.page.mouse.up()
        self.page.wait_for_timeout(250)

    def type(self, sel, value, secret_name=None):
        loc, x, y = self.target(sel)
        self.move_to(x, y)
        self.page.mouse.click(x, y)
        nx, ny = self.norm(x, y)
        self.log("click", x=nx, y=ny)
        if secret_name:
            # Show dots, never the value, even if the field is not a password field.
            self.persist_css(f"{sel}{{-webkit-text-security:disc!important}}")
            self.masks.append(sel)
        t0 = self.now()
        try:
            loc.press_sequentially(value, delay=55 if not secret_name else 35)
        except Exception:
            if secret_name:
                raise PromoError(f"could not type secret '{secret_name}' into {sel}") from None
            raise
        self.log("type", x=nx, y=ny, t0=round(t0, 3), t1=round(self.now(), 3))
        self.page.wait_for_timeout(200)

    def scroll(self, pixels):
        t0 = self.now()
        step = 40 if pixels > 0 else -40
        for _ in range(int(abs(pixels) / 40)):
            self.page.mouse.wheel(0, step)
            self.page.wait_for_timeout(14)
        self.log("scroll", t0=round(t0, 3), t1=round(self.now(), 3), dy=pixels)
        self.page.wait_for_timeout(300)


def _encode(frames, duration, out, width, height, start):
    """Turn variable-rate screencast frames into constant 60 fps H.264.

    `start` is the event clock's zero (wall time), so video time t shows what the page showed
    when the event log says t. Before the first frame arrives, the first frame is held."""
    if not frames:
        raise PromoError("the browser produced no frames")
    frames.sort(key=lambda f: f[0])
    n = int(math.ceil(duration * FPS))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg",
           "-i", "-", "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
           "-crf", "16", "-profile:v", "high", "-movflags", "+faststart", "-r", str(FPS), str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    j, cur = 0, base64.b64decode(frames[0][1])
    for i in range(n):
        t = start + i / FPS
        while j + 1 < len(frames) and frames[j + 1][0] <= t:
            j += 1
            cur = base64.b64decode(frames[j][1])
        proc.stdin.write(cur)
    proc.stdin.close()
    if proc.wait() != 0:
        raise PromoError(f"encoding the recording failed: {proc.stderr.read().decode(errors='replace')[-200:]}")


def record(brief, brief_path, flow, log=print):
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    site = brief["site"]
    base = Path(brief_path).resolve().parent
    start_url = resolve_url(site, base)
    state = None
    if site.get("login") == "session":
        state = session_file(start_url)
        if not state or not state.is_file():
            raise PromoError(f"no saved login for {urlparse(start_url).hostname}. Run: promo login {start_url}")
    vp = VIEWPORTS[flow.get("viewport", "desktop")]["viewport"]
    out_dir = base / "assets" / "recordings"
    out_dir.mkdir(parents=True, exist_ok=True)
    secrets = Secrets(purpose=f"recording {urlparse(start_url).hostname or 'the local app'}")
    with sync_playwright() as p:
        browser, _ = launch(p)
        try:
            ctx = browser.new_context(**VIEWPORTS[flow.get("viewport", "desktop")], storage_state=str(state) if state else None,
                                      color_scheme="light")
            ctx.add_init_script(CONSENT_JS)
            ctx.set_default_timeout(15000)
            page = ctx.new_page()
            page.goto(urljoin(start_url, flow.get("path", "")) if flow.get("path") else start_url, wait_until="load")
            cdp = ctx.new_cdp_session(page)
            rec = Recorder(page, cdp, vp, site.get("mask", []), secrets)
            rec.persist_css("*::-webkit-scrollbar{display:none!important}*{scrollbar-width:none!important}")
            rec.apply_masks()
            # A click that loads a new page is a reveal: the edit pulls back to show it.
            page.on("framenavigated", lambda fr: rec.log("nav") if fr == page.main_frame and rec.t0 else None)
            rec.start()
            for i, st in enumerate(flow["steps"]):
                where = f"{flow['name']} step {i + 1}"
                try:
                    if "goto" in st:
                        url = urljoin(page.url, st["goto"])
                        if not _same_site(url, start_url):
                            raise PromoError(f"{where}: goto leaves the site")
                        page.goto(url, wait_until="load")
                        rec.log("nav")
                    elif "click" in st:
                        rec.click(st["click"])
                    elif "hover" in st:
                        _, x, y = rec.target(st["hover"])
                        rec.move_to(x, y)
                    elif "type" in st or "fill" in st:
                        sel, value = st.get("type") or st.get("fill")
                        m = SECRET_REF.match(value)
                        if m:
                            rec.type(sel, secrets.get(m.group(1)), secret_name=m.group(1))
                        else:
                            if (page.locator(sel).first.get_attribute("type") or "").lower() == "password":
                                raise PromoError(f"{where}: {sel} is a password field; use ${{secret:name}}")
                            rec.type(sel, value)
                    elif "press" in st:
                        page.keyboard.press(st["press"])
                        rec.log("key", key=st["press"])
                        page.wait_for_timeout(250)
                    elif "scroll" in st:
                        rec.scroll(st["scroll"])
                    elif "wait" in st:
                        w = st["wait"]
                        if isinstance(w, int):
                            page.wait_for_timeout(w)
                        elif w == "networkidle":
                            page.wait_for_load_state("networkidle")
                        else:
                            page.locator(w).first.wait_for(state="visible")
                    elif "pause" in st:
                        page.wait_for_timeout(int(st["pause"]))
                except PromoError:
                    raise
                except PWTimeout:
                    raise PromoError(f"{where}: timed out") from None
                except Exception as e:
                    raise PromoError(f"{where}: {type(e).__name__}: {str(e).splitlines()[0][:160]}") from None
            duration = rec.stop()
            frames, t0 = rec.frames, rec.t0
        finally:
            browser.close()
    video = out_dir / f"{flow['name']}.mp4"
    _encode(frames, duration, video, vp["width"] * 2, vp["height"] * 2, t0)
    meta = {"src": f"assets/recordings/{flow['name']}.mp4", "width": vp["width"], "height": vp["height"], "fps": FPS,
            "duration": round(duration, 3), "viewport": flow.get("viewport", "desktop"),
            "first_frame_offset": round(min(f[0] for f in frames) - t0, 3), "events": rec.events}
    (out_dir / f"{flow['name']}.events.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta
