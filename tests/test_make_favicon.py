import importlib.util
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    # scripts/ is not a package, so the generator is loaded by path.
    spec = importlib.util.spec_from_file_location(
        "make_favicon", ROOT / "scripts" / "make_favicon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mf = _load()


def test_every_spine_has_a_png_fill():
    # The PNG carries no media query, so it needs its own palette -- one
    # entry per spine or the rasterizer silently drops a book.
    assert len(mf.PNG_FILLS) == len(mf.SPINES)


def test_upright_spine_is_an_axis_aligned_rect():
    x, top, w, _light, _dark, lean = mf.SPINES[0]
    assert lean == 0, "this test assumes the first spine stands straight"
    poly = mf.spine_polygon(mf.SPINES[0])
    assert poly == [(x, top), (x + w, top),
                    (x + w, mf.BASELINE), (x, mf.BASELINE)]


def test_lean_pivots_about_the_foot():
    # A leaning book stays planted on the shelf: rotating about its own
    # bottom-left corner keeps that corner fixed. Rotating about the
    # shape's centre instead would float it off the baseline.
    leaning = next(s for s in mf.SPINES if s[5] != 0)
    x = leaning[0]
    poly = mf.spine_polygon(leaning)
    foot = (float(x), float(mf.BASELINE))
    assert any(abs(px - foot[0]) < 1e-9 and abs(py - foot[1]) < 1e-9
               for px, py in poly)
    # and the top edge has actually moved sideways
    assert abs(poly[0][0] - x) > 1.0


def test_svg_has_one_rect_per_spine():
    svg = mf.render_svg()
    assert svg.count("<rect ") == len(mf.SPINES)


def test_svg_carries_both_palettes():
    # A favicon renders outside the page's CSS cascade, so it cannot read
    # style.css custom properties or the data-theme attribute. Carrying
    # its own media query is the only way it can follow the OS theme.
    svg = mf.render_svg()
    assert "@media (prefers-color-scheme:dark)" in svg
    for _x, _top, _w, light, dark, _lean in mf.SPINES:
        assert light in svg
        assert dark in svg
    # the dark fills must sit inside the media query, not before it
    head, _, tail = svg.partition("@media (prefers-color-scheme:dark)")
    for _x, _top, _w, _light, dark, _lean in mf.SPINES:
        assert dark not in head
        assert dark in tail


def test_leaning_spine_rotates_about_its_foot():
    svg = mf.render_svg()
    leaning = next(s for s in mf.SPINES if s[5] != 0)
    assert f'transform="rotate({leaning[5]} {leaning[0]} {mf.BASELINE})"' in svg


def test_write_svg_round_trips(tmp_path):
    out = tmp_path / "favicon.svg"
    mf.write_svg(out)
    assert out.read_text(encoding="utf-8") == mf.render_svg()


def _pixel(buf, size, px, py):
    i = (py * size + px) * 4
    return tuple(buf[i:i + 4])


def test_rasterizer_fills_inside_a_spine_and_leaves_gaps_clear():
    # At size 32 each device pixel is 2 user units. Pixel (14, 15) sits
    # inside the middle spine (x 23..36); pixel (10, 15) sits in the gap
    # between the first two (user x 19..23). If that gap ever fills in,
    # the mark has smeared into a blob at small sizes.
    size = 32
    buf = mf.rasterize(size)
    assert _pixel(buf, size, 14, 15)[3] == 255
    assert _pixel(buf, size, 10, 15)[3] == 0
    # nothing is painted below the shelf
    assert _pixel(buf, size, 14, 31)[3] == 0


def test_rasterizer_antialiases_edges():
    # Supersampling is the whole point of the 4x grid: a spine edge that
    # lands mid-pixel must come out partly transparent, not hard-clipped.
    size = 32
    buf = mf.rasterize(size)
    alphas = {_pixel(buf, size, px, py)[3]
              for py in range(size) for px in range(size)}
    assert any(0 < a < 255 for a in alphas)


def test_png_header_declares_32x32_rgba():
    data = mf.encode_png(mf.rasterize(32), 32, 32)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR payload starts at byte 16: width, height, depth, colour type
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth) == (32, 32, 8)
    assert colour == 6, "colour type 6 is RGBA"


def test_png_output_is_deterministic():
    # Generated files are committed, so an unstable encoder would dirty
    # the working tree every time the generator is run.
    a = mf.encode_png(mf.rasterize(32), 32, 32)
    b = mf.encode_png(mf.rasterize(32), 32, 32)
    assert a == b


def test_write_png_round_trips(tmp_path):
    out = tmp_path / "favicon-32.png"
    mf.write_png(out)
    assert out.read_bytes() == mf.encode_png(mf.rasterize(32), 32, 32)


STATIC = ROOT / "humble_catalog" / "webapp" / "static"


def test_committed_svg_is_current():
    # The generator is not run at serve time, so a stale committed file
    # would ship silently. This fails if someone edits SPINES without
    # re-running scripts/make_favicon.py.
    on_disk = (STATIC / "favicon.svg").read_text(encoding="utf-8")
    assert on_disk == mf.render_svg()


def test_committed_png_is_current():
    on_disk = (STATIC / "favicon-32.png").read_bytes()
    assert on_disk == mf.encode_png(mf.rasterize(32), 32, 32)
