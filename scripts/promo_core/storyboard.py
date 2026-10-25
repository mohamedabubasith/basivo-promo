"""Storyboard: load, validate, and turn into a timed timeline. Standard library only."""
import json
import math
import re
from pathlib import Path

from .mask_pii import mask

FORMATS = {
    "16x9": {"w": 1920, "h": 1080, "file": "master_16x9.mp4", "layout": "landscape"},
    "9x16": {"w": 1080, "h": 1920, "file": "vertical_9x16.mp4", "layout": "portrait"},
    "1x1": {"w": 1080, "h": 1080, "file": "square_1x1.mp4", "layout": "square"},
}
FPS = (24, 25, 30, 60)
TRANSITIONS = ("push-left", "push-up", "zoom", "cut")
TRANSITION_SECONDS = 0.6
# Motion speed per brand personality (multiplies every animation duration).
PERSONALITIES = {"premium": 1.15, "corporate": 1.0, "playful": 0.9, "energetic": 0.8}
MUSIC_STYLES = ("peppy", "calm", "playful", "dreamy", "lofi", "cinematic", "ambient")
# Tempo per music style; scene cuts snap to this beat grid.
MUSIC_BPM = {"peppy": 120, "playful": 116, "cinematic": 96, "calm": 84, "lofi": 84, "dreamy": 80, "ambient": 72}
BACKDROPS = ("aurora", "grid", "plain")
CURSORS = ("dark", "light")
STYLE_KEYS = ("name", "description", "brand", "voice", "music", "captions", "transition", "look", "sfx")
VOICE_ENGINES = ("kokoro", "say", "none")
VIEWPORTS = ("desktop", "mobile", "tablet")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
SECRET_REF = re.compile(r"^\$\{secret:([a-z0-9_]{1,40})\}$")

# Seconds a scene needs without voiceover, and its allowed fields beyond the common ones.
SCENES = {
    "logo": (2.6, [], ["text", "sub"]),
    "headline": (2.8, ["text"], ["sub", "eyebrow"]),
    "device": (4.0, ["media"], ["frame", "pan", "title", "caption"]),
    "click": (4.6, ["media", "point"], ["label", "frame", "title"]),
    "features": (4.2, ["items"], ["title"]),
    "split": (4.2, ["before", "after"], ["labels", "title"]),
    "stat": (3.2, ["value", "label"], ["prefix", "suffix", "decimals", "from"]),
    "cta": (3.8, ["text"], ["button", "url", "sub"]),
}
COMMON = ("type", "vo", "duration", "transition")
FRAMES = ("browser", "phone", "laptop", "none")
PANS = ("push", "down", "none")
TEXT_LIMITS = {"text": 60, "sub": 120, "eyebrow": 32, "title": 60, "caption": 90, "label": 40,
               "button": 24, "url": 48, "vo": 400, "prefix": 4, "suffix": 8}
# Tags from mask_pii that mean "this looks like a credential", never allowed in a storyboard.
# REDACTED is left out on purpose: mask()'s loose key/value rule fires on copy like "auth flows".
SECRET_TAGS = re.compile(r"\[(JWT|AWS_KEY|GITHUB_TOKEN|ANTHROPIC_KEY|SLACK_TOKEN|GOOGLE_API_KEY|"
                         r"API_KEY|TOKEN|SECRET|CARD|SSN)\]")
# Explicit "key: value" / "key=value" credential assignments.
SECRET_KV = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token|"
                       r"refresh[_-]?token|client[_-]?secret|otp|cvv)\s*[:=]\s*[\"']?[^\s\"',;]{3,}")

VO_LEAD = 0.35   # seconds from scene start (or end of its transition) to the first word
VO_TAIL = 0.7    # seconds of breathing room after the last word
END_HOLD = 1.2   # extra hold on the last scene for the music fade


class StoryboardError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("\n".join(errors))


def looks_secret(text):
    """True when text contains something shaped like a credential."""
    s = str(text)
    if SECRET_KV.search(s):
        return True
    return bool(SECRET_TAGS.search(mask(s))) and not SECRET_TAGS.search(s)


def load(path, check_media=True):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StoryboardError([f"storyboard not found: {path}"])
    except json.JSONDecodeError as e:
        raise StoryboardError([f"storyboard is not valid JSON: line {e.lineno} col {e.colno}: {e.msg}"])
    return validate(data, path.parent, check_media)


def _inside(base, rel):
    """Resolve rel against base; None if it escapes base or is absolute."""
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        return None
    p = (base / rel).resolve()
    try:
        p.relative_to(base.resolve())
    except ValueError:
        return None
    return p


PLUGIN_STYLES = Path(__file__).resolve().parents[2] / "styles"


def style_dirs(base_dir):
    """Where styles are looked up, most specific first: promo-styles/ in the storyboard folder or
    any of its 4 parents, then ~/.basivo-promo/styles, then the built-in styles."""
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
        raise StoryboardError([f"style: '{name}' is not a valid style name"])
    for d in style_dirs(base_dir):
        f = d / f"{name}.json"
        if f.is_file():
            try:
                style = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                raise StoryboardError([f"style '{name}' ({f}): invalid JSON: {e}"])
            bad = [k for k in style if k not in STYLE_KEYS]
            if not isinstance(style, dict) or bad:
                raise StoryboardError([f"style '{name}' ({f}): unknown fields {bad}; allowed {list(STYLE_KEYS)}"])
            logo = (style.get("brand") or {}).get("logo")
            if logo:
                # A style's logo is relative to the style file, so personal styles can carry one.
                style["brand"]["logo"] = str((f.parent / logo).resolve())
                style["brand"]["_style_logo"] = True
            return style
    raise StoryboardError([f"style '{name}' not found. Available: {', '.join(list_styles(base_dir)) or 'none'}"])


def apply_style(sb, style):
    """Style values are defaults; anything the storyboard sets wins."""
    for k in ("brand", "voice", "captions", "look"):
        if isinstance(style.get(k), dict):
            sb[k] = {**style[k], **(sb.get(k) or {})}
    if "music" in style and "music" not in sb:
        sb["music"] = style["music"]
    elif isinstance(style.get("music"), dict) and isinstance(sb.get("music"), dict):
        sb["music"] = {**style["music"], **sb["music"]}
    for k in ("transition", "sfx"):
        if k in style and k not in sb:
            sb[k] = style[k]
    return sb


def validate(data, base_dir, check_media=True):
    """Return a normalised copy of the storyboard or raise StoryboardError listing every problem.
    check_media=False skips "file exists" checks (used before capture creates the files)."""
    base = Path(base_dir)
    errs = []
    if not isinstance(data, dict):
        raise StoryboardError(["storyboard must be a JSON object"])
    sb = json.loads(json.dumps(data))  # deep copy
    sb.setdefault("style", "midnight")
    sb = apply_style(sb, load_style(sb["style"], base))

    def err(where, msg):
        errs.append(f"{where}: {msg}")

    def text(obj, key, where, required=False):
        v = obj.get(key)
        if v is None:
            if required:
                err(where, f"'{key}' is required")
            return
        if not isinstance(v, str) or not v.strip():
            err(where, f"'{key}' must be a non-empty string")
            return
        limit = TEXT_LIMITS.get(key)
        if limit and len(v) > limit:
            err(where, f"'{key}' is {len(v)} characters, max {limit}")
        if looks_secret(v):
            err(where, f"'{key}' looks like it contains a credential; remove it")

    def media(obj, key, where):
        v = obj.get(key)
        p = _inside(base, v)
        if p is None:
            err(where, f"'{key}' must be a relative path inside the storyboard folder")
        elif p.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
            err(where, f"'{key}' must be an image ({', '.join(sorted(IMAGE_EXT))}) or video ({', '.join(sorted(VIDEO_EXT))})")
        elif check_media and not p.is_file():
            err(where, f"'{key}' not found: {v} (run capture or import first)")

    if sb.get("version") != 1:
        err("version", "must be 1")
    text(sb, "product", "product", required=True)
    if "title" in sb and not (isinstance(sb["title"], str) and NAME.match(sb["title"])):
        err("title", "must be a short slug: lowercase letters, digits, - or _")

    sb.setdefault("formats", ["16x9", "9x16", "1x1"])
    if not isinstance(sb["formats"], list) or not sb["formats"] or any(f not in FORMATS for f in sb["formats"]):
        err("formats", f"must be a non-empty list of {list(FORMATS)}")
    sb.setdefault("fps", 30)
    if sb["fps"] not in FPS:
        err("fps", f"must be one of {FPS}")

    brand = sb.setdefault("brand", {})
    if not isinstance(brand, dict):
        err("brand", "must be an object")
        brand = sb["brand"] = {}
    for k, default in (("bg", "#0b0d12"), ("fg", "#ffffff"), ("accent", "#6c5cff"), ("accent2", "#ff5c8a"), ("muted", "#9aa3b2")):
        brand.setdefault(k, default)
        if not (isinstance(brand[k], str) and HEX.match(brand[k])):
            err(f"brand.{k}", "must be a hex colour like #1a2b3c")
    brand.setdefault("font", "Inter")
    if not (isinstance(brand["font"], str) and re.match(r"^[A-Za-z0-9 \-]{1,40}$", brand["font"])):
        err("brand.font", "must be a font family name")
    brand.setdefault("personality", "corporate")
    if brand["personality"] not in PERSONALITIES:
        err("brand.personality", f"must be one of {list(PERSONALITIES)}")
    from_style = brand.pop("_style_logo", False) and Path(str(brand.get("logo"))).is_absolute()
    if brand.get("logo") is not None:
        p = Path(brand["logo"]) if from_style else _inside(base, brand["logo"])
        if p is None or not p.is_file() or p.suffix.lower() not in IMAGE_EXT:
            err("brand.logo", "must be an image file inside the storyboard folder (or next to the style file)")

    voice = sb.setdefault("voice", {})
    voice.setdefault("engine", "kokoro")
    voice.setdefault("voice", "am_michael" if voice["engine"] == "kokoro" else "")
    voice.setdefault("speed", 1.0)
    if voice["engine"] not in VOICE_ENGINES:
        err("voice.engine", f"must be one of {VOICE_ENGINES}")
    if not isinstance(voice["voice"], str) or not re.match(r"^[A-Za-z0-9_ ()-]{0,40}$", voice["voice"]):
        err("voice.voice", "must be a voice name")
    if not isinstance(voice["speed"], (int, float)) or not 0.7 <= voice["speed"] <= 1.4:
        err("voice.speed", "must be between 0.7 and 1.4")

    music = sb.setdefault("music", {"style": "cinematic", "seed": 7, "volume": 0.5})
    if music is not None:
        if not isinstance(music, dict):
            err("music", "must be an object or null")
        else:
            music.setdefault("style", "cinematic")
            music.setdefault("seed", 7)
            music.setdefault("volume", 0.5)
            if music["style"] not in MUSIC_STYLES:
                err("music.style", f"must be one of {MUSIC_STYLES}")
            else:
                music.setdefault("bpm", MUSIC_BPM[music["style"]])
            if not isinstance(music.get("bpm"), (int, float)) or not 60 <= music.get("bpm", 0) <= 160:
                err("music.bpm", "must be 60 to 160")
            if not isinstance(music["seed"], int) or isinstance(music["seed"], bool) or not 0 <= music["seed"] < 2**31:
                err("music.seed", "must be a non-negative integer")
            if not isinstance(music["volume"], (int, float)) or not 0.05 <= music["volume"] <= 1:
                err("music.volume", "must be between 0.05 and 1")

    captions = sb.setdefault("captions", {"burn": True})
    if not isinstance(captions, dict) or not isinstance(captions.setdefault("burn", True), bool):
        err("captions", "must be {\"burn\": true|false}")
    sb.setdefault("transition", "push-left")
    if sb["transition"] not in TRANSITIONS:
        err("transition", f"must be one of {TRANSITIONS}")
    sb.setdefault("sfx", True)
    if not isinstance(sb["sfx"], bool):
        err("sfx", "must be true or false")
    look = sb.setdefault("look", {})
    if not isinstance(look, dict) or set(look) - {"backdrop", "cursor"}:
        err("look", "must be {backdrop?, cursor?}")
    else:
        look.setdefault("backdrop", "aurora")
        look.setdefault("cursor", "dark")
        if look["backdrop"] not in BACKDROPS:
            err("look.backdrop", f"must be one of {BACKDROPS}")
        if look["cursor"] not in CURSORS:
            err("look.cursor", f"must be one of {CURSORS}")

    scenes = sb.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 30:
        err("scenes", "must be a list of 1 to 30 scenes")
        scenes = []
    for i, sc in enumerate(scenes):
        where = f"scenes[{i}]"
        if not isinstance(sc, dict) or sc.get("type") not in SCENES:
            err(where, f"'type' must be one of {list(SCENES)}")
            continue
        _, req, opt = SCENES[sc["type"]]
        where = f"scenes[{i}] ({sc['type']})"
        for k in sc:
            if k not in COMMON and k not in req and k not in opt:
                err(where, f"unknown field '{k}'")
        for k in req:
            if k not in sc:
                err(where, f"'{k}' is required")
        for k in ("text", "sub", "eyebrow", "title", "caption", "label", "button", "url", "vo", "prefix", "suffix"):
            if k in sc:
                text(sc, k, where)
        if "duration" in sc and (not isinstance(sc["duration"], (int, float)) or not 1 <= sc["duration"] <= 20):
            err(where, "'duration' must be 1 to 20 seconds")
        if "transition" in sc and sc["transition"] not in TRANSITIONS:
            err(where, f"'transition' must be one of {TRANSITIONS}")
        for k in ("media", "before", "after"):
            if k in sc:
                media(sc, k, where)
        if "frame" in sc and sc["frame"] not in FRAMES:
            err(where, f"'frame' must be one of {FRAMES}")
        if "pan" in sc and sc["pan"] not in PANS:
            err(where, f"'pan' must be one of {PANS}")
        if "point" in sc:
            pt = sc["point"]
            if pt == "auto":
                pt = _auto_point(base, sc.get("media"))
                if pt is None and not check_media:
                    pass
                elif pt is None:
                    err(where, "'point' is 'auto' but captures.json has no click point for this media")
                else:
                    sc["point"] = pt
            elif not (isinstance(pt, list) and len(pt) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in pt)):
                err(where, "'point' must be [x, y] with values 0 to 1, or 'auto'")
        if "items" in sc:
            items = sc["items"]
            if not isinstance(items, list) or not 2 <= len(items) <= 6:
                err(where, "'items' must be a list of 2 to 6 features")
            else:
                for j, it in enumerate(items):
                    w = f"{where}.items[{j}]"
                    if not isinstance(it, dict) or set(it) - {"icon", "title", "text"}:
                        err(w, "must be {icon?, title, text?}")
                        continue
                    for k, lim in (("title", 28), ("text", 80), ("icon", 4)):
                        v = it.get(k)
                        if v is None and k != "title":
                            continue
                        if not isinstance(v, str) or not v.strip() or len(v) > lim:
                            err(w, f"'{k}' must be a string of at most {lim} characters")
                        elif looks_secret(v):
                            err(w, f"'{k}' looks like it contains a credential")
        if "labels" in sc:
            lb = sc["labels"]
            if not (isinstance(lb, list) and len(lb) == 2 and all(isinstance(s, str) and 0 < len(s) <= 20 for s in lb)):
                err(where, "'labels' must be two short strings")
        if sc["type"] == "stat":
            for k in ("value", "from"):
                if k in sc and (not isinstance(sc[k], (int, float)) or isinstance(sc[k], bool) or abs(sc[k]) >= 1e9):
                    err(where, f"'{k}' must be a number")
            if "decimals" in sc and sc["decimals"] not in (0, 1, 2, 3):
                err(where, "'decimals' must be 0 to 3")

    if "capture" in sb:
        _validate_capture(sb["capture"], errs)

    if errs:
        raise StoryboardError(errs)
    return sb


def _auto_point(base, media_rel):
    try:
        caps = json.loads((base / "captures.json").read_text(encoding="utf-8"))
        pt = caps.get(media_rel, {}).get("point")
        return [round(float(pt[0]), 4), round(float(pt[1]), 4)] if pt else None
    except (OSError, ValueError, TypeError, IndexError, AttributeError):
        return None


ACTIONS = {"goto", "wait", "click", "fill", "press", "scroll", "hover", "shot"}


def _validate_capture(cap, errs):
    def err(where, msg):
        errs.append(f"capture{where}: {msg}")

    if not isinstance(cap, dict):
        err("", "must be an object")
        return
    for k in cap:
        if k not in ("url", "viewports", "login", "mask", "steps"):
            err("", f"unknown field '{k}'")
    url = cap.get("url")
    if not isinstance(url, str) or not re.match(r"^(https?://[^\s/]+|file://|\./|[A-Za-z0-9_.-]+/)", url):
        err(".url", "must be an http(s) URL, a file:// URL, or a path relative to the storyboard")
    elif looks_secret(url):
        err(".url", "contains something that looks like a credential")
    vps = cap.setdefault("viewports", ["desktop"])
    if not isinstance(vps, list) or not vps or any(v not in VIEWPORTS for v in vps):
        err(".viewports", f"must be a non-empty list of {VIEWPORTS}")
    if cap.setdefault("login", "none") not in ("none", "session"):
        err(".login", "must be 'none' or 'session'")
    masks = cap.setdefault("mask", [])
    if not isinstance(masks, list) or any(not isinstance(m, str) or not m for m in masks):
        err(".mask", "must be a list of CSS selectors")
    steps = cap.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > 100:
        err(".steps", "must be a list of 1 to 100 steps")
        return
    shots = set()
    for i, st in enumerate(steps):
        w = f".steps[{i}]"
        if not isinstance(st, dict):
            err(w, "must be an object")
            continue
        acts = [k for k in st if k in ACTIONS and not (k == "shot" and "click" in st)]
        extra = set(st) - ACTIONS - {"full"}
        if len(acts) != 1 or extra:
            err(w, f"needs exactly one action of {sorted(ACTIONS)} (click may also have 'shot')")
            continue
        a = acts[0]
        v = st[a]
        if a in ("goto",) and (not isinstance(v, str) or looks_secret(v)):
            err(w, "goto needs a URL or path without credentials")
        if a in ("click", "hover") and not (isinstance(v, str) and v):
            err(w, f"{a} needs a selector")
        if a == "press" and not (isinstance(v, str) and re.match(r"^[A-Za-z0-9+]{1,30}$", v)):
            err(w, "press needs a key name such as Enter or Control+A")
        if a == "scroll" and not (isinstance(v, int) and -20000 <= v <= 20000):
            err(w, "scroll needs pixels (integer)")
        if a == "wait" and not ((isinstance(v, int) and 0 <= v <= 30000) or (isinstance(v, str) and v)):
            err(w, "wait needs milliseconds (<= 30000), 'networkidle', or a selector")
        if a == "fill":
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v) and v[0]):
                err(w, "fill needs [selector, value]")
            elif not SECRET_REF.match(v[1]) and looks_secret(v[1]):
                err(w, "fill value looks like a credential; use ${secret:name} so it is asked in a local popup")
            elif "${secret:" in v[1] and not SECRET_REF.match(v[1]):
                err(w, "secret reference must be exactly ${secret:name} (lowercase letters, digits, _)")
        name = st.get("shot") if a in ("shot", "click") else None
        if name is not None:
            if not (isinstance(name, str) and NAME.match(name)):
                err(w, "shot name must be a slug (lowercase, digits, - or _)")
            elif name in shots:
                err(w, f"shot name '{name}' is used twice")
            shots.add(name)
        if "full" in st and not (a == "shot" and isinstance(st["full"], bool)):
            err(w, "'full' only applies to a shot step and must be true or false")


def secret_names(sb):
    """Names of every ${secret:name} the capture section uses (never values)."""
    names = []
    for st in (sb.get("capture") or {}).get("steps") or []:
        v = st.get("fill") if isinstance(st, dict) else None
        if isinstance(v, list) and len(v) == 2 and isinstance(v[1], str):
            m = SECRET_REF.match(v[1])
            if m and m.group(1) not in names:
                names.append(m.group(1))
    return names


def timeline(sb, vo_seconds):
    """Scene start/duration/voice timing. vo_seconds[i] is the voiceover length or None.

    With music, every cut is moved later (never earlier, so speech always fits) to land on
    the beat: the seam's midpoint sits on a beat of the track."""
    speed = PERSONALITIES[sb["brand"]["personality"]]
    beat = 60.0 / sb["music"]["bpm"] if sb.get("music") else None
    plan = []
    for i, sc in enumerate(sb["scenes"]):
        tr_name = "cut" if i == 0 else sc.get("transition", sb["transition"])
        tr = 0.0 if tr_name == "cut" else TRANSITION_SECONDS * speed
        vo = vo_seconds[i] if i < len(vo_seconds) else None
        lead = max(VO_LEAD, tr)
        need = max(SCENES[sc["type"]][0] * speed, sc.get("duration") or 0, (lead + vo + VO_TAIL) if vo else 0)
        plan.append((sc, tr_name, tr, vo, lead, need))
    out, start = [], 0.0
    for i, (sc, tr_name, tr, vo, lead, need) in enumerate(plan):
        dur = need
        if i + 1 < len(plan):
            next_tr = plan[i + 1][2]
            if beat:
                cut = start + dur - next_tr / 2
                dur += math.ceil(cut / beat - 1e-6) * beat - cut
        else:
            dur += END_HOLD
        tm = {"index": i, "type": sc["type"], "start": round(start, 3), "dur": round(dur, 3), "transition": tr_name,
              "tr": round(tr, 3), "vo_at": round(start + lead, 3) if vo else None, "vo_len": round(vo, 3) if vo else None}
        if sc["type"] == "click":
            tm["click_at"] = round(start + tr * 0.5 + 1.6 * speed, 3)
        out.append(tm)
        if i + 1 < len(plan):
            start = start + dur - plan[i + 1][2]
    total = out[-1]["start"] + out[-1]["dur"]
    return {"scenes": out, "total": round(total, 3), "speed": speed, "beat": beat}


def caption_cues(sb, tl, max_chars=42):
    """Split each voiceover line into short cues, timed by character share."""
    cues = []
    for sc, tm in zip(sb["scenes"], tl["scenes"]):
        vo = sc.get("vo")
        if not vo or tm["vo_at"] is None:
            continue
        chunks, cur = [], ""
        for word in vo.split():
            if cur and len(cur) + 1 + len(word) > max_chars:
                chunks.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            chunks.append(cur)
        total = sum(len(c) for c in chunks)
        t = tm["vo_at"]
        for c in chunks:
            d = tm["vo_len"] * len(c) / total
            cues.append({"start": round(t, 3), "end": round(t + d, 3), "text": c})
            t += d
    return cues


def srt(cues):
    def ts(s):
        ms = int(round(s * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        sec, ms = divmod(ms, 1000)
        return f"{h:02}:{m:02}:{sec:02},{ms:03}"
    return "".join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))


def estimate_seconds(sb, words_per_second=2.6):
    """Rough length before TTS runs (for previews and the confirmation popup)."""
    vo = [len(sc["vo"].split()) / words_per_second if sc.get("vo") else None for sc in sb["scenes"]]
    return timeline(sb, vo)["total"]
