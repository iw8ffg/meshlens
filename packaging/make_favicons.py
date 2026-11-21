"""Generate the raster favicons from the MeshLens logo geometry (docs/img/logo.svg).

Run once by hand from the worktree root, with the Pillow of the `tray` extra:
    ../../.venv/Scripts/python packaging/make_favicons.py

Writes web/public/favicon.ico (16, 32, 48 px, transparent background) and
web/public/apple-touch-icon.png (180x180, opaque #0f172a background, logo at 80 %).
The SVG favicon is a byte-for-byte copy of docs/img/logo.svg and is not generated here.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public"

SRC = 256  # viewBox of docs/img/logo.svg
CANVAS = 1024
S = CANVAS / SRC  # 4.0

TEAL = (20, 184, 166)  # #14b8a6
SKY = (14, 165, 233)  # #0ea5e9
DEEP = (15, 118, 110)  # #0f766e
AMBER = (245, 158, 11)  # #f59e0b
NAVY = (15, 23, 42)  # #0f172a


def p(x: float, y: float) -> tuple[float, float]:
    return (x * S, y * S)


def r(v: float) -> float:
    return v * S


def layer() -> Image.Image:
    return Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))


def polyline(draw: ImageDraw.ImageDraw, pts, color, width):
    """Stroke a polyline with round joins and round caps, like the SVG."""
    scaled = [p(x, y) for x, y in pts]
    w = r(width)
    draw.line(scaled, fill=color, width=round(w), joint="curve")
    for x, y in (scaled[0], scaled[-1]):
        draw.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)


def disc(draw: ImageDraw.ImageDraw, cx, cy, rad, color):
    x, y = p(cx, cy)
    rr = r(rad)
    draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=color)


def draw_logo() -> Image.Image:
    base = layer()

    # Mesh edges: the five paths of the SVG, stroke #14b8a6 width 5.
    edges = layer()
    d = ImageDraw.Draw(edges)
    for path in (
        [(48, 70), (110, 44), (176, 70), (208, 128)],
        [(48, 70), (66, 138), (110, 44)],
        [(66, 138), (128, 168), (176, 70)],
        [(128, 168), (208, 128)],
        [(66, 138), (48, 200)],
    ):
        polyline(d, path, TEAL + (255,), 5)
    base = Image.alpha_composite(base, edges)

    # Nodes: six discs r=10 in sky blue.
    nodes = layer()
    d = ImageDraw.Draw(nodes)
    for cx, cy in ((48, 70), (110, 44), (176, 70), (66, 138), (208, 128), (48, 200)):
        disc(d, cx, cy, 10, SKY + (255,))
    base = Image.alpha_composite(base, nodes)

    # Lens: fill #14b8a6 at 18 % opacity, then a 12-wide #0f766e ring (centred on r=52).
    lens_fill = layer()
    d = ImageDraw.Draw(lens_fill)
    cx, cy = p(128, 124)
    rr = r(52)
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=TEAL + (46,))
    base = Image.alpha_composite(base, lens_fill)

    ring = layer()
    d = ImageDraw.Draw(ring)
    outer, inner = r(52 + 6), r(52 - 6)
    d.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), fill=DEEP + (255,))
    d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(0, 0, 0, 0))
    base = Image.alpha_composite(base, ring)

    # Handle: #0f766e, width 18, round caps.
    handle = layer()
    d = ImageDraw.Draw(handle)
    polyline(d, [(166, 162), (222, 218)], DEEP + (255,), 18)
    base = Image.alpha_composite(base, handle)

    # Amber dot.
    dot = layer()
    disc(ImageDraw.Draw(dot), 128, 168, 11, AMBER + (255,))
    return Image.alpha_composite(base, dot)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    logo = draw_logo()

    # favicon.ico: transparent background, 16/32/48 px.
    icon48 = logo.resize((48, 48), Image.LANCZOS)
    icon48.save(OUT / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    # apple-touch-icon.png: opaque navy tile, logo at 80 %.
    tile = Image.new("RGBA", (180, 180), NAVY + (255,))
    inner = round(180 * 0.8)
    scaled = logo.resize((inner, inner), Image.LANCZOS)
    offset = (180 - inner) // 2
    tile.alpha_composite(scaled, (offset, offset))
    tile.convert("RGB").save(OUT / "apple-touch-icon.png", format="PNG")


if __name__ == "__main__":
    main()
