"""
Render Lamba store map markers as PNGs (normal + selected) at 1x..4x.

Geometry (in dp):
  - Shared canvas 56 x 64 so both variants use the same anchor.
  - Pin = circle of radius r plus two tangent lines meeting at a tip
    located 1.4 r below the circle centre. Tip sits at y = 60 for both
    variants -> anchor = (0.5, 60/64).
  - Inner fill = outer pin scaled about the circle centre by (r - bw) / r,
    which gives a perfectly uniform border (homothety preserves tangency).
"""
import io
import math
import os
import re

import cairocffi as cairo
import cairosvg
from PIL import Image, ImageFilter

PRIMARY = "#6C63FF"
WHITE = "#FFFFFF"

CANVAS_W, CANVAS_H = 56, 64
TIP_Y = 60
CX = CANVAS_W / 2
TIP_RATIO = 1.4  # distance centre->tip, as a multiple of r

VARIANTS = {
    "marker-store": dict(r=20, bw=2.5, icon=20, border=PRIMARY, fill=WHITE, glyph=PRIMARY),
    "marker-store-selected": dict(r=23, bw=2.75, icon=23, border=WHITE, fill=PRIMARY, glyph=WHITE),
}
SCALES = [1, 2, 3, 4]

SVG_PATH = os.path.join(os.path.dirname(__file__), "package/dist/svg/storefront.svg")
OUT_DIR = os.path.join(os.path.dirname(__file__), "out")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def pin_path(ctx, cx, cy, r, d):
    """Teardrop: arc over the top + two tangent lines to the tip at (cx, cy + d)."""
    theta = math.acos(r / d)             # angle between 'down' and each tangent point
    right = math.pi / 2 - theta          # screen coords: y down, angles clockwise
    left = math.pi / 2 + theta
    ctx.move_to(cx, cy + d)
    ctx.line_to(cx + r * math.cos(right), cy + r * math.sin(right))
    ctx.arc_negative(cx, cy, r, right, left)
    ctx.close_path()


def draw_pin(scale, r, color, k=1.0):
    """Return a PIL RGBA image of the pin (optionally scaled by k about the centre)."""
    w, h = CANVAS_W * scale, CANVAS_H * scale
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.scale(scale, scale)
    d = TIP_RATIO * r
    cy = TIP_Y - d
    pin_path(ctx, CX, cy, r * k, d * k)
    ctx.set_source_rgb(*hex_rgb(color))
    ctx.fill()
    buf = io.BytesIO()
    surface.write_to_png(buf)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def render_glyph(px, color):
    svg = open(SVG_PATH).read()
    svg = re.sub(r"<svg ", f'<svg fill="{color}" ', svg, count=1)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=px, output_height=px)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def render(name, spec, scale):
    r, bw = spec["r"], spec["bw"]
    w, h = CANVAS_W * scale, CANVAS_H * scale
    d = TIP_RATIO * r
    cy = TIP_Y - d

    # Soft drop shadow (baked in, so no runtime shadow/elevation needed)
    shadow_src = draw_pin(scale, r, "#000000")
    alpha = shadow_src.getchannel("A").point(lambda a: int(a * 0.30))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=2.0 * scale))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(shadow, (0, round(1.5 * scale)))

    # Border (outer pin) then fill (inner pin, uniform inset of bw)
    canvas.alpha_composite(draw_pin(scale, r, spec["border"]))
    canvas.alpha_composite(draw_pin(scale, r, spec["fill"], k=(r - bw) / r))

    # Storefront glyph centred in the circle
    icon_px = round(spec["icon"] * scale)
    glyph = render_glyph(icon_px, spec["glyph"])
    canvas.alpha_composite(glyph, (round(CX * scale - icon_px / 2), round(cy * scale - icon_px / 2)))
    return canvas


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, spec in VARIANTS.items():
        for s in SCALES:
            suffix = "" if s == 1 else f"@{s}x"
            path = os.path.join(OUT_DIR, f"{name}{suffix}.png")
            render(name, spec, s).save(path, optimize=True)
            print(path)
    print(f"anchor = {{ x: 0.5, y: {TIP_Y / CANVAS_H} }}")


if __name__ == "__main__":
    main()
