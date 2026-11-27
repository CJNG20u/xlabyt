"""xlab-yt logo: a play button inside an open ring, drawn with Pillow at any size.

Mirrors static/favicon.svg (480x480 design grid) so PNG icons stay sharp without an SVG
renderer in the container. Run `python3 logo.py` to regenerate the static assets.
"""
import math
from PIL import Image, ImageDraw

DEFAULT_COLOR = '#fa233b'
GRID = 480
CENTER = 240
RING_R = 156          # radius of the ring's center line
RING_W = 48           # ring thickness
GAP = (-50, 260)      # ring drawn clockwise from -50° to 260° (0° = 3 o'clock, y down), gap at top right
TRI = [(205, 165), (320, 240), (205, 315)]
TRI_STROKE = 34


def _pt(angle, r=RING_R):
    return (CENTER + r * math.cos(math.radians(angle)), CENTER + r * math.sin(math.radians(angle)))


def _rounded_poly(d: ImageDraw.ImageDraw, pts, fill, width):
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=fill, width=int(width))
    for x, y in pts:
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=fill)


def hex_to_rgba(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def draw_logo(size: int, color=DEFAULT_COLOR, mark=None, bg=(0, 0, 0, 0), scale: float = 1.0) -> Image.Image:
    """scale: fraction of the canvas the 480 design grid occupies (1.0 = edge to edge).
    `mark` is accepted for compatibility; the logo is single-color."""
    if isinstance(color, str): color = hex_to_rgba(color)
    ss = 4
    S = size * ss
    img = Image.new('RGBA', (S, S), bg)
    d = ImageDraw.Draw(img)
    u = S * scale / GRID
    off = (S - GRID * u) / 2
    tf = lambda p: (off + p[0] * u, off + p[1] * u)

    outer = RING_R + RING_W / 2
    x0, y0 = tf((CENTER - outer, CENTER - outer))
    x1, y1 = tf((CENTER + outer, CENTER + outer))
    d.arc([x0, y0, x1, y1], start=GAP[0], end=GAP[1], fill=color, width=int(RING_W * u))
    for a in GAP:  # round caps
        cx, cy = tf(_pt(a))
        r = RING_W * u / 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    _rounded_poly(d, [tf(p) for p in TRI], color, TRI_STROKE * u)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def svg(color=DEFAULT_COLOR) -> str:
    (sx, sy), (ex, ey) = _pt(GAP[0]), _pt(GAP[1])
    large = 1 if (GAP[1] - GAP[0]) % 360 > 180 else 0
    tri = ' '.join(f'{x},{y}' for x, y in TRI)
    return (f'<svg width="480" height="480" viewBox="0 0 480 480" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
            f'<path d="M {sx:.1f} {sy:.1f} A {RING_R} {RING_R} 0 {large} 1 {ex:.1f} {ey:.1f}" stroke="{color}" stroke-width="{RING_W}" stroke-linecap="round"/>\n'
            f'<polygon points="{tri}" fill="{color}" stroke="{color}" stroke-width="{TRI_STROKE}" stroke-linejoin="round"/>\n'
            f'</svg>\n')


if __name__ == '__main__':
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'static', 'favicon.svg'), 'w') as f:
        f.write(svg())
    # white template, tinted with the theme color by the desktop app build
    draw_logo(256, color=(255, 255, 255, 255)).save(os.path.join(here, 'static', 'favicon-template.png'))
    for s in (48, 128):
        draw_logo(s, bg=(15, 15, 15, 255), scale=0.86).save(os.path.join(here, '..', 'extension', f'favicon{s}.png'))
    print('logo assets written')
