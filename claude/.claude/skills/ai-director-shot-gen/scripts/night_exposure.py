"""Lower the exposure of a night still while keeping practical light sources (lamps, bulbs, glowing tents) bright.

Image models tend to over-expose night scenes. Use this on location references and style frames
during look lock (ai-director-consistency/references/anti-slop.md section 4), then pass the darkened
reference into keyframe generation and apply the same values at render time.

Usage:
  python night_exposure.py in.png [--stops 0.9] [--gamma 1.15] [--vignette 0.35] [--out out.png] [--suffix _darkA]
  python night_exposure.py in.png --compare 0.9,1.5 --out compare.jpg   # side-by-side levels to show the user
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageFilter


def night(img, stops=0.9, gamma=1.15, vignette=0.35):
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    lum = (a @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
    # mask of bright practical sources, softened so their halo keeps its brightness too
    hi = np.clip((lum - 0.75) / 0.25, 0, 1)
    hi = Image.fromarray((hi[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(25))
    hi = np.asarray(hi).astype(np.float32)[..., None] / 255
    out = (a ** gamma) * (2 ** -stops) * (1 - hi) + a * hi
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    out *= (1 - vignette * np.clip(r - 0.5, 0, 1) ** 1.3)[..., None]
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--stops", type=float, default=0.9, help="exposure reduction in stops (0.9 ~ -1 stop)")
    ap.add_argument("--gamma", type=float, default=1.15, help=">1 pushes midtones down")
    ap.add_argument("--vignette", type=float, default=0.35)
    ap.add_argument("--out")
    ap.add_argument("--suffix", default="_darkA")
    ap.add_argument("--compare", help="comma list of stop values, writes a side-by-side jpg to --out")
    args = ap.parse_args()
    src = Image.open(args.image)
    if args.compare:
        levels = [0.0] + [float(x) for x in args.compare.split(",")]
        W = 800
        H = int(W * src.height / src.width)
        sheet = Image.new("RGB", (W * len(levels), H))
        for i, s in enumerate(levels):
            g = 1.0 + (args.gamma - 1.0) * (s / max(args.stops, 1e-6)) if s else 1.0
            im = src.convert("RGB") if s == 0 else night(src, s, g, args.vignette)
            sheet.paste(im.resize((W, H)), (i * W, 0))
        out = args.out or os.path.splitext(args.image)[0] + "_compare.jpg"
        sheet.save(out, quality=90)
    else:
        out = args.out or os.path.splitext(args.image)[0] + args.suffix + ".png"
        night(src, args.stops, args.gamma, args.vignette).save(out)
    print(out)


if __name__ == "__main__":
    sys.exit(main())
