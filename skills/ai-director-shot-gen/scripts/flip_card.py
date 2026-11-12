"""Render a rigid flat card (photo, letter, playing card) falling over a hinge edge on a top-down shot.

Video models cannot turn a thin card past 90 degrees: they swap the front picture for the back instead
of rotating it. This renders the rotation geometrically, frame by frame, onto a clean plate.

  python flip_card.py --plate plate.png --front front.png --back back.png --out flip.mp4 \
      --x0 502 --x1 803 --hinge 245 --height 203 --from 79 --to 180 --frames 9

Geometry (top-down camera, card hinged on a horizontal edge at y=hinge, spanning x0..x1):
  angle a = 0 means lying flat on the NEAR side (below the hinge, front up); 90 = upright; 180 = flat on the
  FAR side (above the hinge, back up). Projected height = height*|cos a|; a<90 draws the front below the
  hinge, a>90 draws the back above it. The free edge is closer to the camera when upright, so it is drawn
  slightly wider (--persp). The fall accelerates like gravity (ease-in). A soft contact shadow follows.
`back` must already be oriented as it will lie at 180 degrees (e.g. tape on the hinge edge).
"""
import argparse
import math
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def quad_warp(tex, quad, size):
    """Map texture onto quad [(tl),(tr),(br),(bl)] in an image of `size`; returns RGBA layer."""
    w, h = tex.size
    # PIL's QUAD transform maps output-quad -> input rectangle; we need the inverse, so use PERSPECTIVE
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    A, B = [], []
    for (x, y), (u, v) in zip(quad, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    coef = np.linalg.solve(np.array(A, float), np.array(B, float))
    layer = tex.convert("RGBA").transform(size, Image.PERSPECTIVE, tuple(coef), Image.BICUBIC)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(quad, fill=255)
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(0.6)))
    return layer


def frame_at(plate, front, back, a, p):
    W, H = plate.size
    x0, x1, hy, ch = p.x0, p.x1, p.hinge, p.height
    rad = math.radians(a)
    proj = ch * abs(math.cos(rad))
    lift = math.sin(rad)                                 # 1 when upright
    grow = (x1 - x0) * p.persp * lift / 2                # free edge nearer the camera -> wider
    img = plate.convert("RGBA")
    # contact shadow: soft, darker when the card is low, offset toward the light's opposite side
    sh = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(sh)
    sy = hy + (p.shadow_dy * lift)
    if a < 90:
        d.rectangle((x0 + 4, hy, x1 + 4, hy + proj + 6 + 40 * lift), fill=int(110 * (0.4 + 0.6 * lift)))
    else:
        d.rectangle((x0 + 4, hy - proj, x1 + 4, sy + 30 * lift), fill=int(110 * (0.4 + 0.6 * lift)))
    sh = sh.filter(ImageFilter.GaussianBlur(10 + 18 * lift))
    dark = Image.new("RGBA", (W, H), (20, 12, 6, 0)); dark.putalpha(sh)
    img = Image.alpha_composite(img, dark)
    if proj > 1.5:
        if a < 90:   # front side, below the hinge
            quad = [(x0, hy), (x1, hy), (x1 + grow, hy + proj), (x0 - grow, hy + proj)]
            tex, shade = front, 0.55 + 0.45 * abs(math.cos(rad))
        else:        # back side, above the hinge
            quad = [(x0 - grow, hy - proj), (x1 + grow, hy - proj), (x1, hy), (x0, hy)]
            tex, shade = back, 0.55 + 0.45 * abs(math.cos(rad))
        t = Image.eval(tex.convert("RGB"), lambda v: int(v * shade))
        img = Image.alpha_composite(img, quad_warp(t, [tuple(map(float, q)) for q in quad], (W, H)))
    # card thickness at the free edge (visible as a thin light line near upright)
    if lift > 0.2:
        ey = hy + proj if a < 90 else hy - proj
        edge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(edge).line((x0 - grow, ey, x1 + grow, ey), fill=(225, 210, 180, int(200 * lift)), width=3)
        img = Image.alpha_composite(img, edge)
    return img.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    for k in ("plate", "front", "back", "out"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--x0", type=float, required=True); ap.add_argument("--x1", type=float, required=True)
    ap.add_argument("--hinge", type=float, required=True); ap.add_argument("--height", type=float, required=True)
    ap.add_argument("--from", dest="a0", type=float, default=80); ap.add_argument("--to", dest="a1", type=float, default=180)
    ap.add_argument("--frames", type=int, default=9)
    ap.add_argument("--hold", type=int, default=2, help="extra frames lying flat at the end")
    ap.add_argument("--persp", type=float, default=0.06)
    ap.add_argument("--shadow-dy", type=float, default=30)
    ap.add_argument("--fps", default="24")
    p = ap.parse_args()
    plate = Image.open(p.plate).convert("RGB")
    front, back = Image.open(p.front).convert("RGB"), Image.open(p.back).convert("RGB")
    W, H = plate.size
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", p.fps, "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", p.out],
                           stdin=subprocess.PIPE)
    for i in range(1, p.frames + 1):
        t = i / p.frames
        a = p.a0 + (p.a1 - p.a0) * t * t                  # gravity: accelerate into the fall
        enc.stdin.write(np.asarray(frame_at(plate, front, back, a, p)).tobytes())
    last = frame_at(plate, front, back, p.a1, p)
    for _ in range(p.hold):
        enc.stdin.write(np.asarray(last).tobytes())
    last.save(p.out.rsplit(".", 1)[0] + "_last.png")
    enc.stdin.close(); enc.wait()


if __name__ == "__main__":
    main()
