"""Add slow breathing to a locked-off close-up in post: the subject region rises and falls, the background barely.

A vertical displacement field (sine over time, --period seconds, --amp px) is weighted by a soft mask: 1 inside
--box (the chest / hand / held object), fading to 0 over --feather px. Each frame is remapped with bilinear
sampling, so there is no tearing at the mask edge.

Optional --coat-fix: inside --coat-box, pull warm-cast low-saturation pixels back toward a dark navy hue
(keeps luminance), for a dark coat that a warm light turned brown.

  python breathe_warp.py in.mp4 out.mp4 --box 0,180,1280,720 --amp 3 --period 4 [--coat-fix --coat-box ...]
"""
import argparse
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageFilter


def bilinear(img, ys, xs):
    h, w = img.shape[:2]
    ys = np.clip(ys, 0, h - 1.001); xs = np.clip(xs, 0, w - 1.001)
    y0 = ys.astype(int); x0 = xs.astype(int); fy = (ys - y0)[..., None]; fx = (xs - x0)[..., None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1 region that breathes")
    ap.add_argument("--feather", type=int, default=120)
    ap.add_argument("--amp", type=float, default=3.0, help="peak vertical travel in px")
    ap.add_argument("--period", type=float, default=4.0, help="seconds per breath")
    ap.add_argument("--phase", type=float, default=0.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--coat-fix", action="store_true")
    ap.add_argument("--coat-box", default="")
    ap.add_argument("--coat-strength", type=float, default=0.6)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="bw_")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.inp, os.path.join(tmp, "f%05d.png")], check=True)
    fs = sorted(f for f in os.listdir(tmp) if f.startswith("f"))
    w, h = Image.open(os.path.join(tmp, fs[0])).size
    x0, y0, x1, y1 = map(int, a.box.split(","))
    m = Image.new("L", (w, h), 0); m.paste(255, (x0, y0, x1, y1))
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(a.feather / 2)), np.float64) / 255
    yy, xx = np.mgrid[:h, :w].astype(np.float64)
    cm = None
    if a.coat_fix and a.coat_box:
        c0, c1, c2, c3 = map(int, a.coat_box.split(","))
        cmi = Image.new("L", (w, h), 0); cmi.paste(255, (c0, c1, c2, c3))
        cm = np.asarray(cmi.filter(ImageFilter.GaussianBlur(40)), np.float64)[..., None] / 255
    navy = np.array([0.55, 0.75, 1.25])
    for i, f in enumerate(fs):
        t = i / a.fps
        dy = -a.amp * np.sin(2 * np.pi * t / a.period + a.phase)   # negative = up (breath in)
        img = np.asarray(Image.open(os.path.join(tmp, f)).convert("RGB"), np.float64)
        o = bilinear(img, yy - dy * m, xx)
        if cm is not None:
            lum = o.mean(2, keepdims=True)
            sat = (o.max(2, keepdims=True) - o.min(2, keepdims=True)) / (o.max(2, keepdims=True) + 1)
            dark = np.clip((90 - lum) / 60, 0, 1)            # only dark fabric, never the bright glass or skin
            k = cm * dark * a.coat_strength * np.clip(1 - sat * 1.5, 0, 1)
            o = o * (1 - k) + np.clip(lum * navy, 0, 255) * k
        Image.fromarray(np.clip(o, 0, 255).astype(np.uint8)).save(os.path.join(tmp, f"o{i:05d}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", os.path.join(tmp, "o%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(a.out, len(fs))


if __name__ == "__main__":
    main()
