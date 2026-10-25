"""Turn a recorded flow into an edited, Screen Studio-style HyperFrames block.

Plan (pure Python, deterministic): speed ramps over idle stretches, camera keyframes that
zoom into each click and typed field, pan between nearby actions and pull back for scrolls,
and a smoothed cursor path. Then write a HyperFrames sub-composition from
templates/hyperframes/promo-screen.html with everything baked in (renders never fetch).
"""
import json
import subprocess
from pathlib import Path

from . import ff
from .paths import TEMPLATES, PromoError

IDLE_GAP = 1.4        # seconds without input before a stretch counts as idle
IDLE_SPEED = 3.0      # how much faster idle stretches play
MOVE = 0.6            # camera move length (launch films: 0.4-0.6 s)
LEAD = 0.15           # arrive this long before the click
HOLD = 1.3            # stay on a click while the UI reacts
CHAIN_GAP = 2.2       # next action closer than this: pan straight there instead of pulling back


def _action_spans(events):
    spans = []
    for e in events:
        if e["type"] in ("click", "key", "nav"):
            spans.append((e["t"] - 0.6, e["t"] + 0.9))
        elif e["type"] in ("type", "scroll"):
            spans.append((e["t0"] - 0.6, e["t1"] + 0.6))
        elif e["type"] == "move":
            spans.append((e["t"] - 0.05, e["t"] + 0.05))
    return sorted(spans)


def speed_segments(events, duration, idle_speed=IDLE_SPEED):
    """[(start, end, speed)] covering the recording: idle gaps play faster."""
    if idle_speed <= 1:
        return [(0.0, duration, 1.0)]
    busy, segs = [], []
    for a, b in _action_spans(events):
        a, b = max(0.0, a), min(duration, b)
        if busy and a <= busy[-1][1]:
            busy[-1][1] = max(busy[-1][1], b)
        else:
            busy.append([a, b])
    t = 0.0
    for a, b in busy:
        if a - t >= IDLE_GAP:
            segs.append((t, a, idle_speed))
        elif a > t:
            segs.append((t, a, 1.0))
        segs.append((a, b, 1.0))
        t = b
    if duration - t >= IDLE_GAP:
        segs.append((t, duration, idle_speed))
    elif duration > t:
        segs.append((t, duration, 1.0))
    merged = []
    for s in segs:  # join neighbours with the same speed
        if merged and merged[-1][2] == s[2] and abs(merged[-1][1] - s[0]) < 1e-6:
            merged[-1] = (merged[-1][0], s[1], s[2])
        elif s[1] - s[0] > 1e-3:
            merged.append(s)
    return merged


def remap(segs):
    """Function mapping recording time to edited time."""
    def f(t):
        out = 0.0
        for a, b, sp in segs:
            if t <= a:
                break
            out += (min(t, b) - a) / sp
        return out
    return f


def camera_keys(events, length, zoom):
    """Camera keyframes [{t, s, x, y, ease}] in edited time; x, y = focus point 0..1."""
    focus = []
    for e in events:
        if e["type"] == "click":
            focus.append((e["t"], e["t"] + HOLD, e["x"], e["y"]))
        elif e["type"] == "type":
            focus.append((e["t0"], e["t1"] + 0.8, e["x"], e["y"]))
        elif e["type"] == "scroll":
            focus.append((e["t0"], e["t1"] + 0.3, None, None))  # wide shot while the page moves
        elif e["type"] == "nav":
            focus.append((e["t"] + 0.25, e["t"] + 1.2, None, None))  # new page: pull back to reveal it
    focus.sort()
    keys = [{"t": 0.0, "s": 1.0, "x": 0.5, "y": 0.5, "ease": "none"}]
    cur = (1.0, 0.5, 0.5)
    for i, (a, b, x, y) in enumerate(focus):
        target = (1.0, 0.5, 0.5) if x is None else (zoom, x, y)
        arrive = max(keys[-1]["t"] + 0.05, a - LEAD)
        depart = max(keys[-1]["t"], arrive - MOVE)
        if target != cur:
            keys.append({"t": round(depart, 3), "s": cur[0], "x": cur[1], "y": cur[2], "ease": "none"})
            keys.append({"t": round(arrive, 3), "s": target[0], "x": target[1], "y": target[2], "ease": "power3.inOut"})
            cur = target
        nxt = focus[i + 1][0] if i + 1 < len(focus) else None
        if cur[0] > 1 and (nxt is None or nxt - LEAD - MOVE - b > CHAIN_GAP):
            out_at = min(b, length - MOVE)
            if out_at > keys[-1]["t"]:
                keys.append({"t": round(out_at, 3), "s": cur[0], "x": cur[1], "y": cur[2], "ease": "none"})
                keys.append({"t": round(out_at + MOVE * 1.2, 3), "s": 1.0, "x": 0.5, "y": 0.5, "ease": "power3.inOut"})
                cur = (1.0, 0.5, 0.5)
    return [k for k in keys if k["t"] <= length + 0.01]


def plan(meta, idle_speed=IDLE_SPEED, zoom=None):
    events = meta["events"]
    segs = speed_segments(events, meta["duration"], idle_speed)
    f = remap(segs)
    length = round(f(meta["duration"]), 3)
    mapped = []
    for e in events:
        e2 = dict(e)
        for k in ("t", "t0", "t1"):
            if k in e2:
                e2[k] = round(f(e2[k]), 3)
        mapped.append(e2)
    zoom = zoom or (1.5 if meta.get("viewport") == "mobile" else 1.9)
    cursor = [[e["t"], e["x"], e["y"]] for e in mapped if e["type"] in ("move", "click", "type") and "x" in e]
    clicks = [[e["t"], e["x"], e["y"]] for e in mapped if e["type"] == "click"]
    return {"segments": segs, "length": length, "camera": camera_keys(mapped, length, zoom), "cursor": cursor,
            "clicks": clicks, "zoom": zoom}


def retime(src, dst, segs):
    """Re-encode the recording with the speed ramps (video only)."""
    if len(segs) == 1 and segs[0][2] == 1.0:
        return src
    parts, labels = [], []
    for i, (a, b, sp) in enumerate(segs):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{sp}[v{i}]")
        labels.append(f"[v{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(segs)}:v=1:a=0,fps=60,format=yuv420p[out]"
    ff.run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264",
            "-preset", "slow", "-crf", "16", "-movflags", "+faststart", str(dst)], "applying speed ramps")
    return dst


def write_block(project, meta, name, chrome="auto", idle_speed=IDLE_SPEED, zoom=None, width=None, height=None, fit=0.8, lift=5):
    """Create compositions/<name>.html in a HyperFrames project; returns (path, length, mount snippet)."""
    project = Path(project)
    if not (project / "hyperframes.json").is_file():
        raise PromoError(f"{project} is not a HyperFrames project (run promo scaffold first)")
    rec_dir = project / "assets" / "recordings"
    src = rec_dir / Path(meta["src"]).name
    if not src.is_file():
        raise PromoError(f"recording not found: {src}")
    p = plan(meta, idle_speed, zoom)
    edited = retime(src, rec_dir / f"{Path(meta['src']).stem}.edit.mp4", p["segments"])
    real = ff.probe(edited)["duration"]
    length = round(min(p["length"], real), 3)
    if chrome == "auto":
        chrome = "phone" if meta.get("viewport") == "mobile" else "browser"
    w = width or _root_size(project)[0]
    h = height or _root_size(project)[1]
    data = {"rw": meta["width"], "rh": meta["height"], "length": length, "chrome": chrome, "camera": p["camera"],
            "cursor": p["cursor"], "clicks": p["clicks"], "touch": meta.get("viewport") == "mobile"}
    tpl = (TEMPLATES / "hyperframes" / "promo-screen.html").read_text(encoding="utf-8")
    html = (tpl.replace("__ID__", name).replace("__W__", str(w)).replace("__H__", str(h))
            .replace("__DUR__", f"{length:.3f}").replace("__SRC__", f"assets/recordings/{Path(edited).name}")
            .replace("__FIT__", f"{fit:.3f}").replace("__LIFT__", f"{lift:g}")
            .replace("__DATA__", json.dumps(data, separators=(",", ":"))))
    out = project / "compositions" / f"{name}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    mount = (f'<div id="{name}-host" class="clip" data-composition-src="compositions/{name}.html" '
             f'data-composition-id="{name}" data-start="0" data-duration="{length:.2f}" data-track-kind="graphics"></div>')
    return out, length, mount


def _root_size(project):
    import re
    html = (Path(project) / "index.html").read_text(encoding="utf-8")
    w = re.search(r'data-width="(\d+)"', html)
    h = re.search(r'data-height="(\d+)"', html)
    if not (w and h):
        raise PromoError("could not read the project's size from index.html")
    return int(w.group(1)), int(h.group(1))
