"""xlab-yt logo: a rounded hexagon with a play button, drawn with Pillow at any size.

Mirrors static/favicon.svg (480x480 design grid) so PNG icons stay sharp without an SVG
renderer in the container.
"""
import math
from PIL import Image, ImageDraw

GRID = 480
HEX_R = 190          # hexagon "radius" (center to vertex) on the 480 grid
HEX_STROKE = 44      # round-join stroke that softens the corners
TRI = [(200, 168), (318, 240), (200, 312)]
TRI_STROKE = 30


def hex_points(cx=240, cy=240, r=HEX_R):
    # pointy-top hexagon
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(-90, 270, 60)]


def _rounded_poly(d: ImageDraw.ImageDraw, pts, fill, width):
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=fill, width=int(width))
    for x, y in pts:
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=fill)


def draw_logo(size: int, color=(255, 115, 0, 255), mark=(15, 15, 15, 255), bg=(0, 0, 0, 0), scale: float = 1.0) -> Image.Image:
    """scale: fraction of the canvas the logo's 480 grid occupies (1.0 = edge to edge)."""
    ss = 4
    S = size * ss
    img = Image.new('RGBA', (S, S), bg)
    d = ImageDraw.Draw(img)
    u = S * scale / GRID
    off = (S - GRID * u) / 2
    tf = lambda p: (off + p[0] * u, off + p[1] * u)
    _rounded_poly(d, [tf(p) for p in hex_points()], color, HEX_STROKE * u)
    _rounded_poly(d, [tf(p) for p in TRI], mark, TRI_STROKE * u)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def hex_to_rgba(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def svg(color='#ff7300', mark='#0f0f0f') -> str:
    pts = ' '.join(f'{x:.1f},{y:.1f}' for x, y in hex_points())
    tri = ' '.join(f'{x},{y}' for x, y in TRI)
    return (f'<svg width="480" height="480" viewBox="0 0 480 480" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
            f'<polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="{HEX_STROKE}" stroke-linejoin="round"/>\n'
            f'<polygon points="{tri}" fill="{mark}" stroke="{mark}" stroke-width="{TRI_STROKE}" stroke-linejoin="round"/>\n'
            f'</svg>\n')


if __name__ == '__main__':
    # regenerate the static assets: python3 logo.py
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'static', 'favicon.svg'), 'w') as f:
        f.write(svg())
    # white template, tinted with THEME_COLOR by the desktop app build
    draw_logo(256, color=(255, 255, 255, 255), mark=(0, 0, 0, 255)).save(os.path.join(here, 'static', 'favicon-template.png'))
    for s in (48, 128):
        draw_logo(s).save(os.path.join(here, '..', 'extension', f'favicon{s}.png'))
    print('logo assets written')
