"""Brand fonts for HyperFrames: bundled families resolve by name; any other Google Fonts family
is downloaded once into assets/fonts (latin subset) and declared with @font-face."""
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .paths import PromoError

# Families HyperFrames bundles (skills/hyperframes/references/format.md).
BUNDLED = {"inter", "montserrat", "outfit", "nunito", "oswald", "league gothic", "archivo black", "space mono", "ibm plex mono",
           "jetbrains mono", "eb garamond", "playfair display", "source code pro", "noto sans jp", "roboto", "open sans", "lato",
           "poppins"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def font_face_css(family, assets_dir, weights=(400, 600, 700, 800)):
    """Return @font-face CSS for `family`, downloading files if needed. '' for bundled families."""
    if not family or family.strip().lower() in BUNDLED:
        return ""
    if not re.match(r"^[A-Za-z0-9 \-]{1,40}$", family):
        raise PromoError(f"invalid font family name: {family}")
    out_dir = Path(assets_dir) / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    url = ("https://fonts.googleapis.com/css2?family=" + urllib.parse.quote_plus(family) +
           ":wght@" + ";".join(str(w) for w in weights) + "&display=block")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        css = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    except OSError:
        return ""  # not a Google font (or offline): the stack falls back to Inter
    faces = []
    # Keep only the latin block of each weight.
    for block in re.findall(r"/\*\s*latin\s*\*/\s*(@font-face\s*\{[^}]+\})", css):
        w = re.search(r"font-weight:\s*(\d+)", block)
        src = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        if not (w and src):
            continue
        name = f"{slug}-{w.group(1)}.woff2"
        dest = out_dir / name
        if not dest.is_file():
            data = urllib.request.urlopen(urllib.request.Request(src.group(1), headers={"User-Agent": UA}), timeout=30).read()
            dest.write_bytes(data)
        faces.append(f'@font-face {{ font-family: "{family}"; font-weight: {w.group(1)}; font-style: normal; font-display: block; '
                     f'src: url("assets/fonts/{name}") format("woff2"); }}')
    return "\n".join(faces)
