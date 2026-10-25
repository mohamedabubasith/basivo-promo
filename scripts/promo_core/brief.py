"""promo.json: what the video is for and which assets feed it. Standard library only.

The film itself (scenes, motion, timing) is a HyperFrames project composed per request; this
file only holds intent, taste, sound and the capture/recording instructions, so it can be
validated, summarised in the confirmation popup and checked for secrets.
"""
import json
import re
from pathlib import Path

from .mask_pii import mask

FORMATS = {
    "16x9": {"w": 1920, "h": 1080, "resolution": "landscape", "file": "master_16x9.mp4"},
    "9x16": {"w": 1080, "h": 1920, "resolution": "portrait", "file": "vertical_9x16.mp4"},
    "1x1": {"w": 1080, "h": 1080, "resolution": "square", "file": "square_1x1.mp4"},
}
MUSIC_STYLES = ("peppy", "calm", "playful", "dreamy", "lofi", "cinematic", "ambient")
MUSIC_BPM = {"peppy": 120, "playful": 116, "cinematic": 96, "calm": 84, "lofi": 84, "dreamy": 80, "ambient": 72}
VOICE_ENGINES = ("kokoro", "say", "none")
SHOT_VIEWPORTS = ("desktop", "mobile", "tablet")
FLOW_VIEWPORTS = ("desktop", "laptop", "mobile")
STYLE_KEYS = ("name", "description", "brand", "voice", "music", "captions", "transition", "look", "sfx", "direction")

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
SECRET_REF = re.compile(r"^\$\{secret:([a-z0-9_]{1,40})\}$")
# Tags from mask_pii that mean "this looks like a credential". REDACTED is left out on purpose:
# mask()'s loose key/value rule fires on copy like "auth flows".
SECRET_TAGS = re.compile(r"\[(JWT|AWS_KEY|GITHUB_TOKEN|ANTHROPIC_KEY|SLACK_TOKEN|GOOGLE_API_KEY|"
                         r"API_KEY|TOKEN|SECRET|CARD|SSN)\]")
SECRET_KV = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token|"
                       r"refresh[_-]?token|client[_-]?secret|otp|cvv)\s*[:=]\s*[\"']?[^\s\"',;]{3,}")


class BriefError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("\n".join(errors))


def looks_secret(text):
    """True when text contains something shaped like a credential."""
    s = str(text)
    if SECRET_KV.search(s):
        return True
    return bool(SECRET_TAGS.search(mask(s))) and not SECRET_TAGS.search(s)


# ---------- taste profiles (styles) ----------

PLUGIN_STYLES = Path(__file__).resolve().parents[2] / "styles"


def style_dirs(base_dir):
    """promo-styles/ in the project folder or any of its 4 parents, then personal, then built-in."""
    from .paths import HOME
    dirs, p = [], Path(base_dir).resolve()
    for _ in range(5):
        dirs.append(p / "promo-styles")
        if p.parent == p:
            break
        p = p.parent
    return dirs + [HOME / "styles", PLUGIN_STYLES]


def list_styles(base_dir):
    seen = {}
    for d in style_dirs(base_dir):
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            if f.stem not in seen:
                try:
                    seen[f.stem] = (f, json.loads(f.read_text(encoding="utf-8")).get("description", ""))
                except (OSError, ValueError):
                    seen[f.stem] = (f, "(unreadable)")
    return seen


def load_style(name, base_dir):
    if not (isinstance(name, str) and NAME.match(name)):
        raise BriefError([f"style: '{name}' is not a valid style name"])
    for d in style_dirs(base_dir):
        f = d / f"{name}.json"
        if f.is_file():
            try:
                style = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                raise BriefError([f"style '{name}' ({f}): invalid JSON: {e}"])
            bad = [k for k in style if k not in STYLE_KEYS] if isinstance(style, dict) else ["(not an object)"]
            if bad:
                raise BriefError([f"style '{name}' ({f}): unknown fields {bad}; allowed {list(STYLE_KEYS)}"])
            logo = (style.get("brand") or {}).get("logo")
            if logo:  # relative to the style file, so personal styles can carry a logo
                style["brand"]["logo"] = str((f.parent / logo).resolve())
            return style, f
    raise BriefError([f"style '{name}' not found. Available: {', '.join(list_styles(base_dir)) or 'none'}"])


# ---------- validation ----------

STEP_ACTIONS = {"goto", "wait", "click", "hover", "fill", "type", "press", "scroll", "shot", "pause"}


def _steps(steps, where, errs, kind):
    def err(w, msg):
        errs.append(f"{where}{w}: {msg}")

    if not isinstance(steps, list) or not steps or len(steps) > 150:
        err("", "needs a list of 1 to 150 steps")
        return
    names = set()
    allowed = STEP_ACTIONS - ({"pause"} if kind == "shots" else {"shot"})
    for i, st in enumerate(steps):
        w = f"[{i}]"
        if not isinstance(st, dict):
            err(w, "must be an object")
            continue
        acts = [k for k in st if k in STEP_ACTIONS and not (k == "shot" and "click" in st and kind == "shots")]
        extra = set(st) - STEP_ACTIONS - {"full"}
        if len(acts) != 1 or extra or acts[0] not in allowed:
            err(w, f"needs exactly one action of {sorted(allowed)}")
            continue
        a, v = acts[0], st[acts[0]]
        if a == "goto" and (not isinstance(v, str) or not v or looks_secret(v)):
            err(w, "goto needs a URL or path without credentials")
        elif a in ("click", "hover") and not (isinstance(v, str) and v):
            err(w, f"{a} needs a CSS selector")
        elif a == "press" and not (isinstance(v, str) and re.match(r"^[A-Za-z0-9+]{1,30}$", v)):
            err(w, "press needs a key such as Enter or Control+A")
        elif a == "scroll" and not (isinstance(v, int) and not isinstance(v, bool) and -20000 <= v <= 20000):
            err(w, "scroll needs pixels (integer)")
        elif a == "wait" and not ((isinstance(v, int) and 0 <= v <= 30000) or (isinstance(v, str) and v)):
            err(w, "wait needs milliseconds (<= 30000), 'networkidle' or a selector")
        elif a == "pause" and not (isinstance(v, int) and 0 < v <= 15000):
            err(w, "pause needs milliseconds (1 to 15000)")
        elif a in ("fill", "type"):
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v) and v[0]):
                err(w, f"{a} needs [selector, value]")
            elif "${secret:" in v[1] and not SECRET_REF.match(v[1]):
                err(w, "a secret reference must be exactly ${secret:name} (lowercase letters, digits, _)")
            elif not SECRET_REF.match(v[1]) and looks_secret(v[1]):
                err(w, "this value looks like a credential; use ${secret:name} so it is asked for in a local popup")
        name = st.get("shot") if kind == "shots" and a in ("shot", "click") else None
        if name is not None:
            if not (isinstance(name, str) and NAME.match(name)):
                err(w, "shot name must be a slug (lowercase, digits, - or _)")
            elif name in names:
                err(w, f"shot name '{name}' is used twice")
            names.add(name)
        if "full" in st and not (a == "shot" and isinstance(st["full"], bool)):
            err(w, "'full' only applies to a shot step")


def validate(data, base_dir):
    """Normalised copy of promo.json, or BriefError listing every problem."""
    base = Path(base_dir)
    errs = []
    if not isinstance(data, dict):
        raise BriefError(["promo.json must be a JSON object"])
    b = json.loads(json.dumps(data))

    def err(where, msg):
        errs.append(f"{where}: {msg}")

    known = {"version", "product", "title", "brief", "length", "formats", "style", "voice", "music", "captions",
             "site", "shots", "flows"}
    for k in b:
        if k not in known:
            err(k, f"unknown field; allowed: {sorted(known)}")
    if b.get("version") != 2:
        err("version", "must be 2")
    for k, limit, required in (("product", 60, True), ("brief", 800, False)):
        v = b.get(k)
        if v is None and not required:
            continue
        if not isinstance(v, str) or not v.strip() or len(v) > limit:
            err(k, f"must be text of at most {limit} characters")
        elif looks_secret(v):
            err(k, "looks like it contains a credential")
    b.setdefault("title", "promo")
    if not (isinstance(b["title"], str) and NAME.match(b["title"])):
        err("title", "must be a slug")
    b.setdefault("length", 45)
    if not isinstance(b["length"], (int, float)) or isinstance(b["length"], bool) or not 6 <= b["length"] <= 180:
        err("length", "must be 6 to 180 seconds")
    b.setdefault("formats", ["16x9"])
    if not isinstance(b["formats"], list) or not b["formats"] or any(f not in FORMATS for f in b["formats"]) \
            or len(set(b["formats"])) != len(b["formats"]):
        err("formats", f"must be a list of distinct {list(FORMATS)}")

    b.setdefault("style", "midnight")
    try:
        style, _ = load_style(b["style"], base)
    except BriefError as e:
        errs.extend(e.errors)
        style = {}
    b["taste"] = style  # resolved profile, for the skill and the scaffold

    voice = {**(style.get("voice") or {}), **(b.get("voice") or {})}
    voice.setdefault("engine", "kokoro")
    voice.setdefault("voice", "am_michael" if voice["engine"] == "kokoro" else "")
    voice.setdefault("speed", 1.0)
    b["voice"] = voice
    if voice["engine"] not in VOICE_ENGINES:
        err("voice.engine", f"must be one of {VOICE_ENGINES}")
    if not isinstance(voice["voice"], str) or not re.match(r"^[A-Za-z0-9_ ()-]{0,40}$", voice["voice"]):
        err("voice.voice", "must be a voice name")
    if not isinstance(voice["speed"], (int, float)) or not 0.7 <= voice["speed"] <= 1.4:
        err("voice.speed", "must be 0.7 to 1.4")

    if "music" in b and b["music"] is None:
        music = None
    else:
        music = {**(style.get("music") or {}), **(b.get("music") or {})}
        music.setdefault("style", "cinematic")
        music.setdefault("seed", 7)
        music.setdefault("volume", 0.5)
        if music["style"] not in MUSIC_STYLES:
            err("music.style", f"must be one of {MUSIC_STYLES}")
        else:
            music.setdefault("bpm", MUSIC_BPM[music["style"]])
        if not isinstance(music["seed"], int) or isinstance(music["seed"], bool) or not 0 <= music["seed"] < 2**31:
            err("music.seed", "must be a non-negative integer")
        if not isinstance(music.get("bpm"), (int, float)) or not 60 <= music["bpm"] <= 160:
            err("music.bpm", "must be 60 to 160")
    b["music"] = music
    b.setdefault("captions", (style.get("captions") or {}).get("burn", True))
    if not isinstance(b["captions"], bool):
        err("captions", "must be true or false")

    site = b.get("site")
    if site is not None:
        if not isinstance(site, dict) or set(site) - {"url", "login", "mask"}:
            err("site", "must be {url, login?, mask?}")
        else:
            url = site.get("url")
            if not isinstance(url, str) or not re.match(r"^(https?://[^\s/]+|file://|\.{0,2}/|[A-Za-z0-9_.-]+/)", url):
                err("site.url", "must be an http(s) URL, a file:// URL or a path relative to promo.json")
            elif looks_secret(url):
                err("site.url", "contains something that looks like a credential")
            if site.setdefault("login", "none") not in ("none", "session"):
                err("site.login", "must be 'none' or 'session'")
            m = site.setdefault("mask", [])
            if not isinstance(m, list) or any(not isinstance(s, str) or not s for s in m):
                err("site.mask", "must be a list of CSS selectors")
    if ("shots" in b or "flows" in b) and site is None:
        err("site", "is required when shots or flows are given")

    shots = b.get("shots")
    if shots is not None:
        if not isinstance(shots, dict) or set(shots) - {"viewports", "steps"}:
            err("shots", "must be {viewports?, steps}")
        else:
            vps = shots.setdefault("viewports", ["desktop"])
            if not isinstance(vps, list) or not vps or any(v not in SHOT_VIEWPORTS for v in vps):
                err("shots.viewports", f"must be a list of {SHOT_VIEWPORTS}")
            _steps(shots.get("steps"), "shots.steps", errs, "shots")

    flows = b.get("flows")
    if flows is not None:
        if not isinstance(flows, list) or not 1 <= len(flows) <= 12:
            err("flows", "must be a list of 1 to 12 flows")
        else:
            seen = set()
            for i, fl in enumerate(flows):
                w = f"flows[{i}]"
                if not isinstance(fl, dict) or set(fl) - {"name", "viewport", "path", "steps"}:
                    err(w, "must be {name, viewport?, path?, steps}")
                    continue
                if not (isinstance(fl.get("name"), str) and NAME.match(fl["name"])) or fl["name"] in seen:
                    err(w, "needs a unique slug 'name'")
                seen.add(fl.get("name"))
                if fl.setdefault("viewport", "desktop") not in FLOW_VIEWPORTS:
                    err(w, f"viewport must be one of {FLOW_VIEWPORTS}")
                if "path" in fl and (not isinstance(fl["path"], str) or looks_secret(fl["path"])):
                    err(w, "path must be a URL path without credentials")
                _steps(fl.get("steps"), f"{w}.steps", errs, "flows")
    if errs:
        raise BriefError(errs)
    return b


def load(path):
    path = Path(path)
    if path.is_dir():
        path = path / "promo.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BriefError([f"promo.json not found: {path}"])
    except json.JSONDecodeError as e:
        raise BriefError([f"promo.json is not valid JSON: line {e.lineno} col {e.colno}: {e.msg}"])
    return validate(data, path.parent), path


def secret_names(b):
    """Every ${secret:name} referenced by shots and flows (names only, never values)."""
    names = []
    steps = list((b.get("shots") or {}).get("steps") or [])
    for fl in b.get("flows") or []:
        steps += fl.get("steps") or []
    for st in steps:
        v = (st.get("fill") or st.get("type")) if isinstance(st, dict) else None
        if isinstance(v, list) and len(v) == 2 and isinstance(v[1], str):
            m = SECRET_REF.match(v[1])
            if m and m.group(1) not in names:
                names.append(m.group(1))
    return names
