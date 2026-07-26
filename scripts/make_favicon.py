"""Generate the viewer favicon (see docs/superpowers/specs/2026-07-20-favicon-design.md).

Three book spines on a 64x64 grid: two upright, one tipping over at the
end of the shelf. Writes a theme-aware favicon.svg and a favicon-32.png
into the webapp's static directory. Output is committed, so this only
needs running when the table below changes.

Standard library only -- no imaging dependency for a one-off icon.
Tune the numbers interactively with scripts/favicon_tuner.html.

Run: .venv/Scripts/python scripts/make_favicon.py
"""
import math
import pathlib
import struct
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "humble_catalog" / "webapp" / "static"

VIEWBOX = 64

# (x, top_y, width, fill_light, fill_dark, lean_degrees)
# All spines stand on BASELINE; lean rotates about (x, BASELINE).
#
# Green / red / purple. Chosen by measuring minimum pairwise CIE Lab dE
# under simulated protanopia, deuteranopia and tritanopia: this triad
# never drops below dE 25 in any of them. Purple replaces the blue
# rather than the green -- purple sitting *between* red and blue
# collapses to dE 10 under tritanopia.
SPINES = [
    (6, 12, 13, "#2f9e28", "#63d452", 0),
    (23, 4, 13, "#d13a1e", "#ff8f70", 0),
    (40, 16, 12, "#7c3aed", "#c39cff", 17),
]
BASELINE = 58
CORNER_RADIUS = 1.5

# The PNG cannot carry a media query, so this single palette has to clear
# a contrast ratio of 3.0 against both a white and a dark tab strip.
PNG_FILLS = ["#3aa832", "#d6431f", "#9a5ff0"]


def spine_polygon(spine, baseline=BASELINE):
    """The spine's four corners in user units, with `lean` applied."""
    x, top, w, _light, _dark, lean = spine
    corners = [(x, top), (x + w, top), (x + w, baseline), (x, baseline)]
    if not lean:
        return [(float(cx), float(cy)) for cx, cy in corners]
    # SVG's rotate(a cx cy) turns clockwise on screen for positive a.
    rad = math.radians(lean)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    out = []
    for cx, cy in corners:
        dx, dy = cx - x, cy - baseline
        out.append((x + dx * cos_a - dy * sin_a,
                    baseline + dx * sin_a + dy * cos_a))
    return out


def render_svg(spines=SPINES, baseline=BASELINE, radius=CORNER_RADIUS):
    """The icon as a self-recolouring SVG document."""
    light = "".join(f".s{i}{{fill:{s[3]}}}" for i, s in enumerate(spines))
    dark = "".join(f".s{i}{{fill:{s[4]}}}" for i, s in enumerate(spines))
    rects = []
    for i, (x, top, w, _l, _d, lean) in enumerate(spines):
        attrs = (f'class="s{i}" x="{x}" y="{top}" width="{w}" '
                 f'height="{baseline - top}" rx="{radius}"')
        if lean:
            attrs += f' transform="rotate({lean} {x} {baseline})"'
        rects.append(f"  <rect {attrs}/>")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX} {VIEWBOX}">\n'
        f"  <style>\n"
        f"    {light}\n"
        f"    @media (prefers-color-scheme:dark){{{dark}}}\n"
        f"  </style>\n"
        + "\n".join(rects)
        + "\n</svg>\n"
    )


def write_svg(path):
    pathlib.Path(path).write_text(render_svg(), encoding="utf-8")


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _inside(px, py, poly):
    """Ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            crossing = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < crossing:
                inside = not inside
    return inside


def rasterize(size=32, spines=SPINES, fills=PNG_FILLS,
              baseline=BASELINE, supersample=4):
    """Render to non-premultiplied RGBA bytes, row-major.

    CORNER_RADIUS is deliberately ignored: at 32px it works out to
    0.75 device pixels, so rounded corners would be invisible.
    """
    polys = [(spine_polygon(s, baseline), _hex_to_rgb(f))
             for s, f in zip(spines, fills)]
    scale = VIEWBOX / size          # user units per device pixel
    step = 1.0 / supersample
    samples = supersample * supersample
    buf = bytearray(size * size * 4)

    for py in range(size):
        for px in range(size):
            acc = [0, 0, 0]
            hits = 0
            for sy in range(supersample):
                for sx in range(supersample):
                    ux = (px + (sx + 0.5) * step) * scale
                    uy = (py + (sy + 0.5) * step) * scale
                    # Later spines paint over earlier ones, so walk the
                    # list backwards and take the first (topmost) hit.
                    for poly, rgb in reversed(polys):
                        if _inside(ux, uy, poly):
                            acc[0] += rgb[0]
                            acc[1] += rgb[1]
                            acc[2] += rgb[2]
                            hits += 1
                            break
            if hits:
                i = (py * size + px) * 4
                buf[i] = round(acc[0] / hits)
                buf[i + 1] = round(acc[1] / hits)
                buf[i + 2] = round(acc[2] / hits)
                buf[i + 3] = round(255 * hits / samples)
    return buf


def encode_png(pixels, width, height):
    """Serialise RGBA bytes as a PNG, using only zlib and struct."""
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)                       # filter type 0 (None)
        raw.extend(pixels[y * stride:(y + 1) * stride])

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def write_png(path, size=32):
    pathlib.Path(path).write_bytes(encode_png(rasterize(size), size, size))


def main():
    write_svg(STATIC / "favicon.svg")
    write_png(STATIC / "favicon-32.png")
    print(f"wrote favicon.svg and favicon-32.png to {STATIC}")


if __name__ == "__main__":
    main()
