"""Join chained FLF segments without the stop-start 'twitch' at each seam.

Each first/last-frame segment eases out into its end key and eases in from its start frame, so a plain concat
shows a near-freeze of a few frames then a jolt. For every seam this script drops the near-static frames on both
sides (motion below --still x the clip median, at most --max-drop per side) and cross-fades --xfade frames.

  python smooth_join.py seg1.mp4 seg2.mp4 seg3.mp4 --out joined.mp4 [--xfade 4 --still 0.45 --max-drop 4 --fps 24]

Segments after the first are assumed to start on the previous segment's last frame (that duplicate is dropped).
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
    return [np.asarray(Image.open(os.path.join(d, f)).convert("RGB"), np.float32) for f in sorted(os.listdir(d))]


def motion(fr):
    g = [f.mean(2)[::4, ::4] for f in fr]
    return np.array([np.abs(g[i + 1] - g[i]).mean() for i in range(len(g) - 1)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--xfade", type=int, default=4)
    ap.add_argument("--still", type=float, default=0.45)
    ap.add_argument("--max-drop", type=int, default=4)
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="sj_")
    segs = []
    for i, s in enumerate(a.segs):
        d = os.path.join(tmp, f"s{i}"); os.makedirs(d)
        fr = frames(s, d)
        segs.append(fr[1:] if i else fr)
    med = np.median(np.concatenate([motion(s) for s in segs]))
    out = list(segs[0])
    for nxt in segs[1:]:
        mo, mn = motion(out[-(a.max_drop + 2):]), motion(nxt[:a.max_drop + 2])
        tail = 0
        while tail < a.max_drop and mo[-1 - tail] < a.still * med:
            tail += 1
        head = 0
        while head < a.max_drop and mn[head] < a.still * med:
            head += 1
        if tail:
            out = out[:-tail]
        nxt = nxt[head:]
        k = min(a.xfade, len(out), len(nxt))
        for j in range(k):
            t = (j + 1) / (k + 1)
            out[-k + j] = out[-k + j] * (1 - t) + nxt[j] * t
        out += nxt[k:]
        print(f"seam: dropped {tail} tail + {head} head frames, cross-faded {k}")
    od = os.path.join(tmp, "o"); os.makedirs(od)
    for i, f in enumerate(out):
        Image.fromarray(np.clip(f, 0, 255).astype(np.uint8)).save(os.path.join(od, f"{i:05d}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", os.path.join(od, "%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(a.out, len(out), "frames", round(len(out) / a.fps, 2), "s")


if __name__ == "__main__":
    main()
