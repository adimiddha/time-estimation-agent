"""Generate apple-touch-icon.png — an almost-untied knot matching the loading animation."""
import math
from PIL import Image, ImageDraw

SIZE = 512          # generate at 512 for retina, iOS downsamples as needed
PROGRESS = 0.12     # mostly knotted, just barely starting to unwind

# ── Knot path (mirrors drawThreadKnot in app.js) ─────────────────────────────
def knot_points(W, H, progress, N=600):
    cx, cy = W / 2, H / 2
    knot_r = min(H * 0.36, W * 0.36)   # square canvas: same ratio both axes
    tail_frac = 0.20
    loops = 3.5

    pts = []
    for i in range(N + 1):
        u = i / N
        # Straight target
        sx = W * (0.06 + u * 0.88)
        sy = cy

        # Knotted state
        if u <= tail_frac:
            kx = W * (0.06 + (u / tail_frac) * (0.5 - 0.06))
            ky = cy
        elif u >= 1 - tail_frac:
            t = (u - (1 - tail_frac)) / tail_frac
            kx = W * (0.5 + t * (0.94 - 0.5))
            ky = cy
        else:
            t = (u - tail_frac) / (1 - 2 * tail_frac)
            angle = t * math.pi * 2 * loops
            r = knot_r * math.sin(t * math.pi)
            kx = cx + r * math.cos(angle)
            ky = cy + r * math.sin(angle)

        pts.append((
            kx + (sx - kx) * progress,
            ky + (sy - ky) * progress,
        ))
    return pts


def draw_thick_polyline(draw, pts, color, width):
    """Draw a polyline with round caps/joins by overlaying circles at each vertex."""
    r = width / 2
    for i in range(1, len(pts)):
        draw.line([pts[i - 1], pts[i]], fill=color, width=width)
    for p in pts[::3]:   # dots at every 3rd point for smooth joins
        x, y = p
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    # End caps
    for p in [pts[0], pts[-1]]:
        x, y = p
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def generate_icon(path, size=SIZE):
    W = H = size
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Background: rounded square, deep forest green ────────────────────────
    bg = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    radius = int(W * 0.22)
    bg_draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius,
                               fill=(38, 90, 78))   # #26564e — dark forest green
    img = Image.alpha_composite(img, bg)
    draw = ImageDraw.Draw(img)

    # ── Subtle inner vignette ────────────────────────────────────────────────
    vig = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vig)
    vig_draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius,
                                fill=(0, 0, 0, 0))
    img = Image.alpha_composite(img, vig)
    draw = ImageDraw.Draw(img)

    pts = knot_points(W, H, PROGRESS)
    thick = max(14, int(W * 0.055))

    # Shadow layer (offset + blur via a separate image)
    shadow_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    offset = int(thick * 0.35)
    shifted = [(x + offset, y + offset * 1.5) for x, y in pts]
    draw_thick_polyline(shadow_draw, shifted, (15, 45, 38, 90), thick + 4)
    from PIL.ImageFilter import GaussianBlur
    shadow_img = shadow_img.filter(GaussianBlur(radius=thick * 0.6))

    # Clip shadow to rounded rect
    mask = Image.new('L', (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius, fill=255)
    shadow_img.putalpha(Image.fromarray(
        __import__('numpy').minimum(
            __import__('numpy').array(shadow_img.split()[3]),
            __import__('numpy').array(mask)
        )
    ))
    img = Image.alpha_composite(img, shadow_img)
    draw = ImageDraw.Draw(img)

    # Main rope — warm white/cream
    draw_thick_polyline(draw, pts, (230, 255, 248), thick)

    # Highlight sheen on top (lighter, thinner)
    draw_thick_polyline(draw, pts, (255, 255, 255, 100), max(4, int(thick * 0.30)))

    # End nubs
    nub_r = int(thick * 0.72)
    for p in [pts[0], pts[-1]]:
        x, y = p
        draw.ellipse([x - nub_r, y - nub_r, x + nub_r, y + nub_r],
                     fill=(150, 220, 200))

    img.save(path, 'PNG')
    print(f'Saved {path}  ({W}×{H})')


if __name__ == '__main__':
    import os
    out_dir = os.path.join(os.path.dirname(__file__),
                           'time_calibration_agent', 'static')
    generate_icon(os.path.join(out_dir, 'apple-touch-icon.png'), size=512)
    generate_icon(os.path.join(out_dir, 'favicon-192.png'), size=192)
