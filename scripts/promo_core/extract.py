"""Adopt a product's own look and copy: colours, font, logo, icons and text from its website,
or a palette from an image. Writes brand/ and a style named after the product."""
import base64
import colorsys
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import ff
from .browser import launch
from .mask_pii import mask
from .paths import PromoError, slug

# Runs inside the page. Returns raw facts; Python decides.
PAGE_JS = r"""() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const txt = (e) => (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
  const solid = (c) => c && !/rgba?\(0, 0, 0, 0\)|transparent/.test(c) && !/rgba\([^)]*, 0\)$/.test(c);
  const firstBg = () => { for (const e of [document.querySelector('main'), document.body, document.documentElement]) {
    if (e) { const c = getComputedStyle(e).backgroundColor; if (solid(c)) return c; } } return 'rgb(255, 255, 255)'; };
  const fontOf = (e) => e ? getComputedStyle(e).fontFamily : '';
  const h1 = [...document.querySelectorAll('h1')].find(vis);
  const p = [...document.querySelectorAll('p')].find((e) => vis(e) && txt(e).length > 30);
  const buttons = [...document.querySelectorAll('button, a, [role=button], input[type=submit]')]
    .filter((e) => vis(e) && txt(e).length > 0 && txt(e).length <= 28)
    .map((e) => ({ t: txt(e), bg: getComputedStyle(e).backgroundColor, fg: getComputedStyle(e).color,
                   img: getComputedStyle(e).backgroundImage, area: e.getBoundingClientRect().width * e.getBoundingClientRect().height }));
  const vars = {}; const rs = getComputedStyle(document.documentElement);
  for (const sheet of [...document.styleSheets]) { let rules; try { rules = sheet.cssRules; } catch (_) { continue; }
    for (const r of rules || []) { if (r.selectorText === ':root' && r.style) for (const n of r.style) if (n.startsWith('--')) vars[n] = rs.getPropertyValue(n).trim(); } }
  // The product's own logo: the home link at the top of the page wins over customer-logo walls.
  const home = `a[href="/"], a[href="${location.origin}"], a[href="${location.origin}/"], a[aria-label*=home i]`;
  const logoTiers = [
    `header :is(${home}) :is(svg, img), nav :is(${home}) :is(svg, img)`,
    `:is(${home}) :is(svg, img)`,
    'header [class*=logo i] :is(svg, img), nav [class*=logo i] :is(svg, img), header :is(svg, img)[class*=logo i]',
    '[class*=logo i] :is(svg, img), img[alt*=logo i]',
    'header img, header svg, nav img, nav svg',
  ];
  let logoEl = null;
  for (const sel of logoTiers) {
    let list = []; try { list = [...document.querySelectorAll(sel)]; } catch (_) { continue; }
    logoEl = list.find((e) => { const r = e.getBoundingClientRect(); return vis(e) && r.width >= 20 && r.top < 220 && r.top > -10; });
    if (logoEl) break;
  }
  let logo = null;
  if (logoEl && logoEl.tagName.toLowerCase() === 'svg') {
    const c = logoEl.cloneNode(true); c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    // CSS variables and stylesheet colours do not travel with the file: bake computed paint in.
    const src = [logoEl, ...logoEl.querySelectorAll('*')], dst = [c, ...c.querySelectorAll('*')];
    src.forEach((o, i) => { const s = getComputedStyle(o), d = dst[i]; if (!d) return;
      for (const p of ['fill', 'stroke', 'opacity', 'fill-opacity', 'stroke-width']) { const v = s.getPropertyValue(p); if (v) d.setAttribute(p, v); }
      d.removeAttribute('class'); });
    if (!c.getAttribute('viewBox')) { const b = logoEl.getBBox ? logoEl.getBBox() : null; if (b) c.setAttribute('viewBox', `${b.x} ${b.y} ${b.width} ${b.height}`); }
    const ink = getComputedStyle(logoEl).color;
    c.setAttribute('fill', c.getAttribute('fill') || ink);
    if (!c.getAttribute('width') && logoEl.getBoundingClientRect) { const r = logoEl.getBoundingClientRect(); c.setAttribute('width', Math.round(r.width)); c.setAttribute('height', Math.round(r.height)); }
    // Inside <img>, currentColor is black; bake in the colour the site actually shows.
    logo = { svg: c.outerHTML.replace(/currentColor/gi, ink) };
  } else if (logoEl) logo = { src: logoEl.currentSrc || logoEl.src };
  const icons = [...document.querySelectorAll('link[rel~=icon], link[rel=apple-touch-icon]')].map((l) => ({ href: l.href, sizes: l.sizes ? l.sizes.value : '', rel: l.rel }));
  const meta = (n) => (document.querySelector(`meta[name="${n}"], meta[property="${n}"]`) || {}).content || '';
  const features = [];
  for (const h of document.querySelectorAll('h3, h4')) { if (!vis(h) || features.length >= 8) continue;
    const t = txt(h); if (t.length < 3 || t.length > 40) continue;
    let n = h.nextElementSibling, body = ''; for (let i = 0; i < 3 && n && !body; i++, n = n.nextElementSibling) if (/^(P|DIV|SPAN)$/.test(n.tagName)) body = txt(n);
    features.push({ title: t, text: body.slice(0, 140) }); }
  const stats = [...document.querySelectorAll('h2, h3, h4, strong, b, span, div')].filter((e) => e.children.length === 0 && vis(e))
    .map(txt).filter((t) => t.length <= 16 && /^\+?\$?\d[\d,.]*\s?(%|x|\+|k|K|M|B|ms|s|h|min)?\+?$/.test(t)).slice(0, 8);
  return {
    title: document.title, description: meta('description') || meta('og:description'), ogImage: meta('og:image'),
    siteName: meta('og:site_name'), themeColor: meta('theme-color'),
    bg: firstBg(), fg: getComputedStyle(h1 || document.body).color, muted: p ? getComputedStyle(p).color : '',
    headingFont: fontOf(h1), bodyFont: fontOf(p || document.body),
    h1: h1 ? txt(h1).slice(0, 120) : '', h2: [...document.querySelectorAll('h2')].filter(vis).map(txt).filter((t) => t.length > 2 && t.length < 90).slice(0, 10),
    buttons: buttons.slice(0, 60), nav: [...document.querySelectorAll('nav a, header a')].filter(vis).map(txt).filter((t) => t && t.length < 24).slice(0, 10),
    features, stats, vars, logo, icons,
    links: [...document.querySelectorAll('a')].filter(vis).slice(0, 80).map((a) => getComputedStyle(a).color),
    used: (() => { // colour census: how much of the page each colour actually paints
      const w = {}; const add = (c, n) => { if (solid(c) && n > 0) w[c] = (w[c] || 0) + n; };
      [...document.querySelectorAll('body *')].slice(0, 2500).forEach((e) => {
        if (!vis(e)) return; const s = getComputedStyle(e), r = e.getBoundingClientRect();
        add(s.backgroundColor, Math.min(r.width * r.height, 250000) / 500);
        const own = [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('').length;
        add(s.color, own * 2);
        if (e instanceof SVGElement) { add(s.fill, 60); add(s.stroke, 30); }
      });
      return Object.entries(w).sort((a, b) => b[1] - a[1]).slice(0, 40);
    })(),
  };
}"""


def _rgb(css):
    if not css:
        return None
    css = css.strip()
    m = re.match(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", css)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)", css)
    if not m:
        return None
    if m.group(4) is not None:
        a = m.group(4)
        alpha = float(a[:-1]) / 100 if a.endswith("%") else float(a)
        if alpha < 0.5:
            return None
    return tuple(min(255, int(float(m.group(i)))) for i in (1, 2, 3))


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _sat(rgb):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return s if 0.12 < l < 0.88 else 0


def _hue_shift(rgb, deg):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    r, g, b = colorsys.hls_to_rgb((h + deg / 360) % 1, l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def _hue_gap(a, b):
    ha = colorsys.rgb_to_hls(*(c / 255 for c in a))[0] * 360
    hb = colorsys.rgb_to_hls(*(c / 255 for c in b))[0] * 360
    d = abs(ha - hb) % 360
    return min(d, 360 - d)


BROWSER_DEFAULTS ={(0, 0, 238), (85, 26, 139), (0, 0, 255), (238, 0, 0)}  # unstyled link / visited / active colours


def _distinct(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) > 90


def palette(facts):
    bg = _rgb(facts.get("bg")) or (255, 255, 255)
    fg = _rgb(facts.get("fg")) or ((17, 24, 39) if _lum(bg) > 0.4 else (255, 255, 255))
    if contrast(fg, bg) < 4.5:
        fg = (17, 24, 39) if _lum(bg) > 0.4 else (255, 255, 255)
    muted = _rgb(facts.get("muted"))
    if not muted or contrast(muted, bg) < 3 or not _distinct(muted, fg):
        muted = tuple(round(f * 0.62 + b * 0.38) for f, b in zip(fg, bg))
    # Accent: the most prominent saturated button colour, then theme-color, then brand-ish CSS vars.
    cands = []
    for b in facts.get("buttons", []):
        c = _rgb(b.get("bg"))
        if c and _sat(c) > 0.25:
            cands.append((b.get("area", 0), c))
        for g in re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]{6}", b.get("img") or ""):
            c = _rgb(g)
            if c and _sat(c) > 0.25:
                cands.append((b.get("area", 0) * 0.8, c))
    for k, v in (facts.get("vars") or {}).items():
        c = _rgb(v)
        if c and _sat(c) > 0.25:
            # Brand-named variables count a lot; any other saturated design token counts a little.
            cands.append((5000 if re.search(r"primary|brand|accent|highlight|focus|ring|selection|interactive", k, re.I) else 40, c))
    for lc in facts.get("links", []):
        c = _rgb(lc)
        if c and _sat(c) > 0.25 and c not in BROWSER_DEFAULTS:
            cands.append((300, c))
    for css, n in facts.get("used", []):
        c = _rgb(css)
        if c and _sat(c) > 0.25 and c not in BROWSER_DEFAULTS:
            cands.append((n, c))
    tc = _rgb(facts.get("themeColor"))
    if tc and _sat(tc) > 0.25:
        cands.append((2, tc))
    weight = {}
    for area, c in cands:
        key = min(weight, key=lambda k: sum(abs(x - y) for x, y in zip(k, c)), default=None)
        if key is not None and not _distinct(key, c):
            weight[key] += area + 1
        else:
            weight[c] = area + 1
    ranked = sorted(weight, key=weight.get, reverse=True)
    accent = ranked[0] if ranked else ((108, 92, 255) if _lum(bg) < 0.4 else (37, 99, 235))
    # Second accent: a brand colour in a neighbouring hue (status reds/greens rarely belong in a gradient).
    accent2 = next((c for c in ranked[1:6] if _distinct(c, accent) and 12 <= _hue_gap(c, accent) <= 75), _hue_shift(accent, 40))
    return {"bg": _hex(bg), "fg": _hex(fg), "accent": _hex(accent), "accent2": _hex(accent2), "muted": _hex(muted),
            "theme": "dark" if _lum(bg) < 0.4 else "light"}


def _font(family):
    for name in (family or "").split(","):
        name = name.strip().strip("\"'")
        if name and not name.startswith(("-apple-system", "system-ui", "BlinkMacSystemFont", "ui-", "Segoe UI Emoji")) \
                and name.lower() not in ("sans-serif", "serif", "monospace", "inherit") and re.match(r"^[A-Za-z0-9 \-]{1,40}$", name):
            return name
    return "Inter"


def _write_logo(page, facts, out):
    logo = facts.get("logo")
    if logo and logo.get("svg"):
        p = out / "logo.svg"
        p.write_text(logo["svg"], encoding="utf-8")
        return p
    urls = []
    if logo and logo.get("src"):
        urls.append(logo["src"])
    icons = sorted(facts.get("icons", []), key=lambda i: ("apple-touch-icon" not in " ".join(i.get("rel") or []),
                                                          -max([int(x) for x in re.findall(r"\d+", i.get("sizes") or "")] or [0])))
    urls += [i["href"] for i in icons]
    for u in urls:
        if not u:
            continue
        try:
            if u.startswith("data:image/"):
                head, data = u.split(",", 1)
                ext = ".svg" if "svg" in head else ".png"
                blob = base64.b64decode(data) if ";base64" in head else data.encode()
            else:
                r = page.request.get(u, timeout=15000)
                if not r.ok:
                    continue
                ctype = r.headers.get("content-type", "").lower()
                ext = next((e for k, e in (("svg", ".svg"), ("png", ".png"), ("jpeg", ".jpg"), ("jpg", ".jpg"), ("webp", ".webp"))
                            if k in ctype), None)  # .ico is skipped: browsers render it, but it is too small for video
                if not ext:
                    continue
                blob = r.body()
            if len(blob) < 100 or len(blob) > 5_000_000:
                continue
            p = out / f"logo{ext}"
            p.write_bytes(blob)
            return p
        except Exception:  # a logo is nice to have; any single failure just moves to the next candidate
            continue
    return None


def _clean(s, limit):
    s = re.sub(r"\s+", " ", mask(str(s or ""))).strip()
    half = len(s) // 2
    if len(s) > 8 and s[:half].strip() == s[half:].strip():  # animated headings often repeat their text
        s = s[:half].strip()
    return s[:limit]


def _name(facts, url):
    site = (facts.get("siteName") or "").strip()
    first = re.split(r"\s[|–—\-:·]\s", facts.get("title") or "")[0].strip()
    host = (urlparse(url).hostname or "").removeprefix("www.").split(".")[0] if url else ""
    for cand in (site, first, host.capitalize()):
        if cand and len(cand) <= 28:
            return _clean(cand, 28)
    return "Brand"


def from_url(url, folder, session=None, log=print):
    from playwright.sync_api import sync_playwright

    if urlparse(url).scheme not in ("http", "https"):
        raise PromoError("extract needs an http(s) URL")
    out = Path(folder) / "brand"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser, _ = launch(p)
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                      storage_state=str(session) if session else None, color_scheme="light")
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                page.goto(url, wait_until="load", timeout=45000)
            page.wait_for_timeout(800)
            page.add_style_tag(content="*::-webkit-scrollbar{display:none!important}")
            facts = page.evaluate(PAGE_JS)
            page.screenshot(path=str(out / "hero.png"), animations="disabled", caret="hide")
            h = page.evaluate("Math.min(document.documentElement.scrollHeight, 7000)")
            page.set_viewport_size({"width": 1440, "height": int(h)})
            page.wait_for_timeout(500)
            page.screenshot(path=str(out / "page.png"), animations="disabled", caret="hide")
            logo = _write_logo(page, facts, out)
        finally:
            browser.close()
    return _finish(facts, url, folder, out, logo)


def from_image(image, folder, is_logo=False):
    """Palette from an image (screenshot, brand board or logo)."""
    import numpy as np

    src = Path(image)
    if not src.is_file():
        raise PromoError(f"image not found: {src}")
    out = Path(folder) / "brand"
    out.mkdir(parents=True, exist_ok=True)
    ff.need("ffmpeg")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", "scale=96:96:flags=area,format=rgba", "-f", "rawvideo", "-"],
                         capture_output=True)
    if raw.returncode != 0 or not raw.stdout:
        raise PromoError("could not read that image")
    px = np.frombuffer(raw.stdout, dtype=np.uint8).reshape(-1, 4)
    px = px[px[:, 3] > 200][:, :3]
    if not len(px):
        raise PromoError("the image is fully transparent")
    q = (px // 16).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    order = np.argsort(-counts)
    colours = [tuple(int(v) for v in px[(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]) == keys[i]].mean(axis=0)) for i in order[:24]]
    sat = sorted((c for c in colours if _sat(c) > 0.3), key=lambda c: -_sat(c))
    facts = {"bg": _hex(colours[0]) if not is_logo else "#0b0d12", "fg": "", "muted": "",
             "buttons": [{"bg": _hex(c), "area": 10 - i} for i, c in enumerate(sat[:4])]}
    logo = None
    if is_logo:
        logo = out / f"logo{src.suffix.lower()}"
        shutil.copyfile(src, logo)
    else:
        shutil.copyfile(src, out / f"source{src.suffix.lower()}")
    return _finish(facts, None, folder, out, logo)


def _finish(facts, url, folder, out, logo):
    pal = palette(facts)
    name = _name(facts, url)
    content = {
        "source": url, "name": name, "title": _clean(facts.get("title"), 120), "description": _clean(facts.get("description"), 300),
        "h1": _clean(facts.get("h1"), 120), "headings": [_clean(h, 90) for h in facts.get("h2", [])],
        "ctas": sorted({_clean(b["t"], 28) for b in facts.get("buttons", []) if _rgb(b.get("bg")) and _sat(_rgb(b["bg"])) > 0.25})[:6],
        "nav": [_clean(n, 24) for n in facts.get("nav", [])],
        "features": [{"title": _clean(f["title"], 40), "text": _clean(f["text"], 140)} for f in facts.get("features", [])],
        "stats": [_clean(s, 16) for s in facts.get("stats", [])],
        "fonts": {"heading": _font(facts.get("headingFont")), "body": _font(facts.get("bodyFont"))},
    }
    rel_logo = logo.relative_to(Path(folder)).as_posix() if logo else None
    brand = {"name": name, "colors": pal, "font": content["fonts"]["heading"], "logo": rel_logo,
             "screens": [p.relative_to(Path(folder)).as_posix() for p in (out / "hero.png", out / "page.png") if p.is_file()]}
    (out / "brand.json").write_text(json.dumps(brand, indent=2), encoding="utf-8")
    (out / "content.json").write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    style_name = slug(name)
    style = {"name": style_name, "description": f"Adopted from {url or 'an image'}: colours, font and logo.",
             "brand": {k: pal[k] for k in ("bg", "fg", "accent", "accent2", "muted")} | {"font": brand["font"], "personality": "corporate"},
             "look": {"backdrop": "aurora" if pal["theme"] == "dark" else "grid", "cursor": "light" if pal["theme"] == "dark" else "dark"}}
    if rel_logo:
        style["brand"]["logo"] = "../" + rel_logo  # style logos are relative to the style file
    styles = Path(folder) / "promo-styles"
    styles.mkdir(exist_ok=True)
    (styles / f"{style_name}.json").write_text(json.dumps(style, indent=2), encoding="utf-8")
    return brand, content, style_name
