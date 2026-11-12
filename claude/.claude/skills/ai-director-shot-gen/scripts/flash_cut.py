"""Cut from clip A to clip B under a light flash (a fire catching, a spell igniting), done in post.

The flash is a soft radial bloom centred on the light source, added in linear light: it rises over the last
--pre frames of A, peaks on the cut, and decays over the first --post frames of B.

  python flash_cut.py a.mp4 b.mp4 --x 0.52 --y 0.48 --radius 0.35 --color 0.75,0.88,1.0 --peak 1.6 \
      --pre 2 --post 6 --out out.mp4 [--fps 24]
"""
import argparse
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image


def frames(path, d):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, os.path.join(d, "%05d.png")], check=True)
    return [os.path.join(d, f) for f in sorted(os.listdir(d))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--x", type=float, default=0.5); ap.add_argument("--y", type=float, default=0.5)
    ap.add_argument("--radius", type=float, default=0.35, help="fraction of frame width")
    ap.add_argument("--color", default="0.75,0.88,1.0")
    ap.add_argument("--peak", type=float, default=1.6)
    ap.add_argument("--haze", type=float, default=0.08, help="wide glow over the whole frame")
    ap.add_argument("--pre", type=int, default=2); ap.add_argument("--post", type=int, default=6)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="fc_")
    da, db, do = (os.path.join(tmp, n) for n in "abo")
    for d in (da, db, do):
        os.makedirs(d)
    fa, fb = frames(a.a, da), frames(a.b, db)
    seq = fa + fb
    cut = len(fa)
    w, h = Image.open(seq[0]).size
    yy, xx = np.mgrid[:h, :w]
    r = np.hypot(xx - a.x * w, yy - a.y * h) / (a.radius * w)
    bloom = (np.exp(-r ** 2 * 1.5) + a.haze * np.exp(-r ** 2 * 0.25))[..., None]
    col = np.array([float(c) for c in a.color.split(",")])
    for i, f in enumerate(seq):
        k = 0.0
        if cut - a.pre <= i < cut:
            k = (i - (cut - a.pre) + 1) / (a.pre + 1)
        elif cut <= i < cut + a.post:
            k = 1 - (i - cut) / a.post
            k = k * k
        im = np.power(np.asarray(Image.open(f).convert("RGB"), np.float64) / 255, 2.2)
        if k:
            im = im + bloom * col * a.peak * k
            im = im / (1 + 0.35 * im)        # soft shoulder so the peak blooms instead of clipping flat
        Image.fromarray((np.clip(np.power(np.clip(im, 0, 1), 1 / 2.2), 0, 1) * 255 + .5).astype(np.uint8)).save(
            os.path.join(do, f"{i:05d}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", os.path.join(do, "%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(a.out, len(seq), "frames")


if __name__ == "__main__":
    main()
