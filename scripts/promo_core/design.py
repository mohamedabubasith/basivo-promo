"""Design directions from UI UX Pro Max data (vendor/uupm, MIT): product type -> style, palette,
font pairing and motion feel. Three distinct directions so the person picks a taste, not a default."""
import csv
import json
import re
from pathlib import Path

from .paths import VENDOR, PromoError

DATA = VENDOR / "uupm"
WORD = re.compile(r"[a-z0-9]+")


def _rows(name):
    with open(DATA / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _words(text):
    return set(WORD.findall(str(text).lower()))


STOP = {"a", "an", "and", "the", "for", "of", "to", "with", "app", "apps", "our", "my", "your", "tool", "platform", "product"}


def _score(query, *fields):
    """Exact word matches count 2; a shared prefix of 3+ letters (devops ~ developer) counts 1."""
    q = _words(query) - STOP
    hay = _words(" ".join(fields)) - STOP
    exact = q & hay
    prefix = {w for w in q - exact for h in hay if len(w) >= 3 and len(h) >= 3 and (h.startswith(w[:3]) and w.startswith(h[:3]))}
    return 2 * len(exact) + len(prefix)


def _best_product(query, products):
    """Rank product types by query words weighted by rarity (a word in few product types says more)."""
    import math
    docs = [_words(p["Product Type"] + " " + p["Keywords"]) - STOP for p in products]
    n = len(docs)
    q = _words(query) - STOP

    def idf(w):
        df = sum(1 for d in docs if w in d)
        return math.log((n + 1) / (df + 1)) + 1

    def score(i):
        d, total = docs[i], 0.0
        for w in q:
            if w in d:
                total += 2 * idf(w)
            elif len(w) >= 3 and any(h.startswith(w[:3]) and w.startswith(h[:3]) for h in d if len(h) >= 3):
                total += 0.5 * idf(w)
        return total

    order = sorted(range(n), key=score, reverse=True)
    return [products[i] for i in order[:5] if score(i) > 0] or [products[0]]  # fallback: SaaS (General)


def _hexes(text):
    return re.findall(r"#[0-9A-Fa-f]{6}", text or "")


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _personality(text):
    t = text.lower()
    if re.search(r"\b(luxur\w*|elegan\w*|premium|sophisticated|editorial|refined)\b", t):
        return "premium"
    if re.search(r"\b(playful|fun|friendly|whimsical|cute|kids|candy)\b", t):
        return "playful"
    if re.search(r"\b(bold|energetic|neon|brutal\w*|cyber\w*|gaming|vibrant|dynamic|punchy)\b", t):
        return "energetic"
    return "corporate"


def _sat(h):
    import colorsys
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    _, l, s = colorsys.rgb_to_hls(r, g, b)
    return s if 0.15 < l < 0.85 else 0


def _accents(candidates, bg, fallback):
    """Two visible brand accents: saturated and at least 3:1 against the background."""
    good = []
    for h in candidates + fallback:
        if h and _sat(h) > 0.3 and _contrast(h, bg) >= 3 and all(sum(abs(int(h[i:i + 2], 16) - int(g[i:i + 2], 16)) for i in (1, 3, 5)) > 90 for g in good):
            good.append(h)
        if len(good) == 2:
            break
    good += ["#6C5CFF", "#FF5C8A"][len(good):]
    return good[0], good[1]


MUSIC = {"premium": "cinematic", "corporate": "calm", "playful": "playful", "energetic": "peppy"}
TRANSITION = {"premium": "push-up", "corporate": "push-left", "playful": "push-left", "energetic": "zoom"}


def _style(name, styles):
    """Find a style row by (part of) its category name."""
    name = name.strip().lower()
    for s in styles:
        if s["Style Category"].strip().lower() == name:
            return s
    for s in styles:
        if name and (name in s["Style Category"].lower() or s["Style Category"].lower() in name):
            return s
    return None


def _palette_from_style(style, dark):
    hexes = _hexes(style.get("Primary Colors", "")) + _hexes(style.get("Secondary Colors", ""))
    sat = [h for h in hexes if 0.03 < _lum(h) < 0.7]
    accent = sat[0] if sat else "#6C5CFF"
    accent2 = next((h for h in sat[1:] if h.lower() != accent.lower()), "#FF5C8A")
    bg, fg = ("#0B0D12", "#FFFFFF") if dark else ("#F8FAFC", "#0F172A")
    return {"bg": bg, "fg": fg, "accent": accent, "accent2": accent2, "muted": "#9AA3B2" if dark else "#5B6472"}


def directions(query, n=3, product_type=None):
    products, colors, styles, fonts = _rows("products"), _rows("colors"), _rows("styles"), _rows("typography")
    styles = [s for s in styles if (s.get("Status") or "active").lower() in ("", "active")]
    candidates = _best_product(query, products)
    if product_type:
        best = next((p for p in products if p["Product Type"].strip().lower() == product_type.strip().lower()), None)
        if not best:
            raise PromoError(f"unknown product type '{product_type}'")
    else:
        best = candidates[0]
    pal_row = next((c for c in colors if c["Product Type"].strip() == best["Product Type"].strip()), colors[0])
    names = [x.strip() for x in re.split(r"\+|,", best["Primary Style Recommendation"] + "," + best["Secondary Styles"]) if x.strip()]
    picked = []
    for nm in names:
        s = _style(nm, styles)
        if s and s not in picked:
            picked.append(s)
    # A deliberate contrast as the last option: a dark, high-energy style.
    bold = max((s for s in styles if s.get("Dark Mode ✓", "").strip() == "supported" and s not in picked),
               key=lambda s: _score("bold dark cinematic neon motion premium " + query, s["Keywords"], s["Best For"]), default=None)
    if bold:
        picked = picked[:n - 1] + [bold]
    ranked_fonts = sorted(fonts, key=lambda f: -_score(query + " " + best["Keywords"], f["Mood/Style Keywords"], f["Best For"]))
    out, used_fonts = [], set()
    for i, s in enumerate(picked[:n]):
        dark = i == len(picked[:n]) - 1 and s is bold
        product_colours = [pal_row["Primary"], pal_row["Accent"], pal_row["Ring"], pal_row["Secondary"]]
        if i == 0:
            pal = {"bg": pal_row["Background"], "fg": pal_row["Foreground"], "muted": pal_row["Muted Foreground"]}
            pal["accent"], pal["accent2"] = _accents(product_colours, pal["bg"], [])
        else:
            pal = _palette_from_style(s, dark)
            style_colours = _hexes(s.get("Primary Colors", "")) + _hexes(s.get("Secondary Colors", ""))
            pal["accent"], pal["accent2"] = _accents(style_colours, pal["bg"], product_colours)
        if _contrast(pal["fg"], pal["bg"]) < 7:
            pal["fg"] = "#0F172A" if _lum(pal["bg"]) > 0.4 else "#FFFFFF"
        font = next((f for f in sorted(ranked_fonts, key=lambda f: -_score(s["Keywords"] + " " + query, f["Mood/Style Keywords"], f["Best For"]))
                     if f["Heading Font"] not in used_fonts), ranked_fonts[0])
        used_fonts.add(font["Heading Font"])
        pers = _personality(s["Keywords"] + " " + s["Style Category"])
        out.append({
            "style": s["Style Category"], "for": best["Product Type"], "palette": pal,
            "font": {"heading": font["Heading Font"], "body": font["Body Font"], "pairing": font["Font Pairing Name"]},
            "personality": pers, "music": MUSIC[pers], "transition": TRANSITION[pers],
            "motion": (s.get("Effects & Animation") or "")[:220], "keywords": (s.get("Keywords") or "")[:160],
            "avoid": (s.get("Do Not Use For") or "")[:120],
        })
    return best, out, candidates


def to_profile(d, name):
    pal = d["palette"]
    dark = _lum(pal["bg"]) < 0.4
    return {
        "name": name,
        "description": f"{d['style']} for {d['for']}: {d['font']['pairing']} type, {d['personality']} pace.",
        "brand": {"bg": pal["bg"].lower(), "fg": pal["fg"].lower(), "accent": pal["accent"].lower(), "accent2": pal["accent2"].lower(),
                  "muted": pal["muted"].lower(), "font": d["font"]["heading"], "personality": d["personality"]},
        "music": {"style": d["music"], "seed": 7, "volume": 0.5},
        "transition": d["transition"],
        "look": {"backdrop": "aurora" if dark else "grid", "cursor": "light" if dark else "dark"},
        "direction": f"{d['style']}. Motion: {d['motion']} Feel: {d['keywords']}. Body font: {d['font']['body']}.",
    }


def write_profile(d, name, where):
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,39}$", name):
        raise PromoError("style name must be a lowercase slug")
    where = Path(where)
    where.mkdir(parents=True, exist_ok=True)
    path = where / f"{name}.json"
    path.write_text(json.dumps(to_profile(d, name), indent=2) + "\n", encoding="utf-8")
    return path
