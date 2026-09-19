"""Generate the demo catalog's covers (see scripts/demo_catalog.py).

One invented cover per DEMO_ROWS entry that names a `cover` ratio: a
coloured panel, a spine band and the row's title. Written to
scripts/demo_covers/ and committed, so every visual check has covers to
look at -- the demo used to have none, which is how a stretched-cover bug
reached a real phone unseen.

SVG rather than PNG on purpose. An SVG is text, so leak_check.py reads the
titles inside it like any other tracked file; a PNG is pixels that only a
person could review (see the Privacy section of CLAUDE.md). The folder is
demo_covers/, not covers/: check_no_data_tracked.py refuses anything under
a covers/ folder, which is where the REAL covers live.

Standard library only. Output is deterministic, and
tests/test_demo_catalog.py fails until the committed files match it.

Run: .venv/Scripts/python scripts/make_demo_covers.py
"""
import pathlib
import sys
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "scripts" / "demo_covers"

# Every cover is this wide; the height follows the row's ratio. 240 keeps
# 2:3 (360), 1:1 (240) and 16:9 (135) all whole pixels.
WIDTH = 240
SPINE = 14
FONT = 20
LINE = 24
WRAP = 16          # characters per title line

# Muted, and distinct per type, so a glance tells the types apart.
COLOURS = {"ebook": "#4f6d8f", "audiobook": "#8f5f4f", "comic": "#5f8f5a",
           "music": "#7a5f8f", "android": "#8f834f"}


def _lines(title):
    """The title broken into lines of at most WRAP characters, by word."""
    lines, line = [], ""
    for word in title.split():
        if line and len(line) + 1 + len(word) > WRAP:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


def render(row):
    """The SVG text for one demo row's cover."""
    rw, rh = row["cover"]
    height = WIDTH * rh // rw
    fill = COLOURS.get(row["type"], "#666666")
    text = "".join(
        f'<text x="{SPINE + 12}" y="{28 + n * LINE}">{escape(line)}</text>'
        for n, line in enumerate(_lines(row["name"])))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
            f'height="{height}" viewBox="0 0 {WIDTH} {height}">'
            f'<rect width="{WIDTH}" height="{height}" fill="{fill}"/>'
            f'<rect width="{SPINE}" height="{height}" fill="#000" '
            f'fill-opacity="0.25"/>'
            f'<g fill="#fff" font-family="sans-serif" font-size="{FONT}">'
            f'{text}</g></svg>\n')


def render_all(rows):
    """{file name: SVG text} for every row that names a cover."""
    return {f"{r['mn']}.svg": render(r) for r in rows if r.get("cover")}


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    from demo_catalog import DEMO_ROWS
    wanted = render_all(DEMO_ROWS)
    OUT_DIR.mkdir(exist_ok=True)
    # A row that lost its cover must lose its file too, or the committed
    # folder drifts from the table.
    for stray in OUT_DIR.glob("*.svg"):
        if stray.name not in wanted:
            stray.unlink()
    for name, svg in wanted.items():
        (OUT_DIR / name).write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {len(wanted)} covers to {OUT_DIR}")


if __name__ == "__main__":
    main()
