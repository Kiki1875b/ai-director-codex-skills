"""Light change spreading from a point, done in post on a static-camera clip.

The clip is generated from the END key (e.g. blue light). A second, pixel-aligned key with the START light (e.g.
warm tungsten) gives a low-frequency gain map G = start/end. Each frame is relit to the start look with G, then a
soft circle centred on the source (a glowing bead) grows and reveals the original (end) light inside it.

  python relight_spread.py --video in.mp4 --start-key warm.png --end-key blue.png --x 0.351 --y 0.617 \
      --t0 0.6 --t1 2.4 --out out.mp4 [--soft 0.18 --blur 10 --fps 24]

--x/--y are fractions of the frame. Before t0 the frame is all start light, after t1 all end light.
"""
import argparse
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageFilter


def lin(a):
    return np.power(a / 255.0, 2.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--start-key", required=True)
    ap.add_argument("--end-key", required=True)
    ap.add_argument("--x", type=float, required=True)
    ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--t0", type=float, default=0.6)
    ap.add_argument("--t1", type=float, default=2.4)
    ap.add_argument("--soft", type=float, default=0.18, help="edge width, fraction of the frame diagonal")
    ap.add_argument("--blur", type=float, default=10, help="gain map blur radius in px")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="rl_")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, os.path.join(tmp, "f%05d.png")], check=True)
    names = sorted(f for f in os.listdir(tmp) if f.startswith("f"))
    w, h = Image.open(os.path.join(tmp, names[0])).size
    ld = lambda p: Image.open(p).convert("RGB").resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(a.blur))
    s, e = lin(np.asarray(ld(a.start_key), np.float64)), lin(np.asarray(ld(a.end_key), np.float64))
    gain = np.clip((s + 1e-3) / (e + 1e-3), 0.25, 4.0)

    yy, xx = np.mgrid[:h, :w]
    diag = np.hypot(w, h)
    d = np.hypot(xx - a.x * w, yy - a.y * h) / diag
    rmax = d.max() + a.soft
    for i, f in enumerate(names):
        t = i / a.fps
        p = np.clip((t - a.t0) / max(a.t1 - a.t0, 1e-6), 0, 1)
        p = p * p * (3 - 2 * p)                           # ease in/out
        r = -a.soft + p * (rmax + a.soft)                 # circle radius grows past the far corner
        m = np.clip((r - d) / a.soft, 0, 1)[..., None]    # 1 inside = end light
        fr = lin(np.asarray(Image.open(os.path.join(tmp, f)).convert("RGB"), np.float64))
        o = fr * m + np.clip(fr * gain, 0, 1) * (1 - m)
        Image.fromarray((np.power(o, 1 / 2.2) * 255 + 0.5).astype(np.uint8)).save(os.path.join(tmp, f"o{i:05d}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", os.path.join(tmp, "o%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(a.out)


if __name__ == "__main__":
    main()
