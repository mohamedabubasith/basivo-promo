"""Capture crisp screenshots of a web app by following the shots steps in promo.json."""
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .browser import CONSENT_JS, launch
from .paths import SESSIONS, PromoError, private_dir
from .secrets import Secrets
from .brief import SECRET_REF

HIDE_SCROLLBARS = "*::-webkit-scrollbar{display:none!important}*{scrollbar-width:none!important}"


def resolve_url(cap, base_dir):
    url = cap["url"]
    if url.startswith(("http://", "https://", "file://")):
        return url
    p = (Path(base_dir) / url).resolve()
    if not p.exists():
        raise PromoError(f"capture.url path not found: {url}")
    return p.as_uri()


def session_file(url):
    host = urlparse(url).hostname
    return SESSIONS / f"{host}.json" if host else None


def _viewport(p, name):
    if name == "mobile":
        return dict(p.devices["iPhone 15 Pro"])
    if name == "tablet":
        return dict(p.devices["iPad Pro 11"])
    return {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 2}


def _same_site(a, b):
    pa, pb = urlparse(a), urlparse(b)
    return pa.scheme == pb.scheme and pa.hostname == pb.hostname


def capture(brief, brief_path, log=print):
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    cap = {**brief["site"], **brief["shots"]}
    base = Path(brief_path).resolve().parent
    start = resolve_url(cap, base)
    secrets = Secrets(purpose=f"capturing {urlparse(start).hostname or 'the local app'}")
    state = None
    if cap["login"] == "session":
        state = session_file(start)
        if not state or not state.is_file():
            raise PromoError(f"no saved login for {urlparse(start).hostname}. Run: promo login {start}")
    result, shots = {}, 0
    with sync_playwright() as p:
        browser, _ = launch(p)
        try:
            for vp in cap["viewports"]:
                ctx = browser.new_context(**_viewport(p, vp), storage_state=str(state) if state else None,
                                          reduced_motion="no-preference", color_scheme="light")
                ctx.add_init_script(CONSENT_JS)
                ctx.set_default_timeout(15000)
                page = ctx.new_page()
                masked = list(cap["mask"])
                outdir = base / "assets" / "captures" / vp
                outdir.mkdir(parents=True, exist_ok=True)

                def shoot(name, full=False, point=None):
                    nonlocal shots
                    page.add_style_tag(content=HIDE_SCROLLBARS)
                    path = outdir / f"{name}.png"
                    page.screenshot(path=str(path), full_page=full, animations="disabled", caret="hide",
                                    mask=[page.locator(s) for s in masked], mask_color="#2b2f3a")
                    rel = path.relative_to(base).as_posix()
                    result[rel] = {"viewport": vp, "full_page": full}
                    if point:
                        result[rel]["point"] = point
                    shots += 1

                page.goto(start, wait_until="load")
                for i, st in enumerate(cap["steps"]):
                    where = f"capture step {i + 1}"
                    try:
                        if "goto" in st:
                            url = urljoin(page.url if page.url != "about:blank" else start, st["goto"]) if not st["goto"].startswith(("http://", "https://", "file://")) else st["goto"]
                            if not _same_site(url, start):
                                raise PromoError(f"{where}: goto leaves {urlparse(start).hostname or 'the app'}; only the capture.url site is allowed")
                            page.goto(url, wait_until="load")
                        elif "wait" in st:
                            w = st["wait"]
                            if isinstance(w, int):
                                page.wait_for_timeout(w)
                            elif w == "networkidle":
                                page.wait_for_load_state("networkidle")
                            else:
                                page.locator(w).first.wait_for(state="visible")
                        elif "click" in st:
                            loc = page.locator(st["click"]).first
                            loc.scroll_into_view_if_needed()
                            point = None
                            if st.get("shot"):
                                box = loc.bounding_box()
                                vs = page.viewport_size
                                if box and vs:
                                    point = [round((box["x"] + box["width"] / 2) / vs["width"], 4),
                                             round((box["y"] + box["height"] / 2) / vs["height"], 4)]
                                shoot(st["shot"], point=point)
                            loc.click()
                        elif "hover" in st:
                            page.locator(st["hover"]).first.hover()
                        elif "fill" in st or "type" in st:
                            sel, value = st.get("fill") or st.get("type")
                            loc = page.locator(sel).first
                            m = SECRET_REF.match(value)
                            if m:
                                try:
                                    loc.fill(secrets.get(m.group(1)))
                                except PromoError:
                                    raise
                                except Exception:
                                    # Never surface the underlying message: keep the value out of every log.
                                    raise PromoError(f"{where}: could not type secret '{m.group(1)}' into {sel}") from None
                                masked.append(sel)  # never show a typed secret in any later screenshot
                            else:
                                if (loc.get_attribute("type") or "").lower() == "password":
                                    raise PromoError(f"{where}: {sel} is a password field; use ${{secret:name}} instead of a literal value")
                                loc.fill(value)
                        elif "press" in st:
                            page.keyboard.press(st["press"])
                        elif "scroll" in st:
                            page.mouse.wheel(0, st["scroll"])
                            page.wait_for_timeout(400)
                        elif "shot" in st:
                            shoot(st["shot"], full=bool(st.get("full")))
                    except PromoError:
                        raise
                    except PWTimeout:
                        raise PromoError(f"{where}: timed out ({next(iter(st))}: {_describe(st)})") from None
                    except Exception as e:
                        raise PromoError(f"{where}: {type(e).__name__}: {str(e).splitlines()[0][:160]}") from None
                ctx.close()
                log(f"{vp}: done")
        finally:
            browser.close()
    caps_path = base / "assets" / "captures" / "captures.json"
    old = json.loads(caps_path.read_text(encoding="utf-8")) if caps_path.is_file() else {}
    old.update(result)
    caps_path.write_text(json.dumps(old, indent=2), encoding="utf-8")
    return result, shots


def _describe(st):
    k = next(iter(st))
    v = st[k]
    if k in ("fill", "type"):
        return f"{v[0]} <- {'secret' if SECRET_REF.match(v[1]) else 'text'}"
    return str(v)[:80]


def _confirm_dialog(message):
    """Blocking native OK dialog; returns True when the user confirms."""
    if platform.system() == "Darwin" and shutil.which("osascript"):
        r = subprocess.run(["osascript", "-e", "on run argv", "-e",
                            'display dialog (item 1 of argv) with title "basivo-promo" buttons {"Cancel", "Done"} default button "Done"',
                            "-e", "end run", message], capture_output=True, text=True)
        return r.returncode == 0
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return bool(messagebox.askokcancel("basivo-promo", message, parent=root))
        finally:
            root.destroy()
    except Exception:
        raise PromoError("cannot open a confirmation dialog on this machine")


def login(url, log=print):
    """Open a visible browser, let the user log in themselves, then save the session cookies."""
    from playwright.sync_api import sync_playwright

    target = session_file(url)
    if not target:
        raise PromoError("login needs an http(s) URL")
    with sync_playwright() as p:
        browser, _ = launch(p, headless=False)
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.goto(url)
            ok = _confirm_dialog(f"Log in to {urlparse(url).hostname} in the browser window that just opened.\n\n"
                                 "Then click Done here. Your password goes only to the website; basivo-promo saves the "
                                 "session cookies on this computer so captures can reuse them.")
            if not ok:
                raise PromoError("login cancelled; nothing was saved")
            private_dir(SESSIONS)
            state = ctx.storage_state()
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f)
            os.chmod(target, 0o600)
        finally:
            browser.close()
    return target
