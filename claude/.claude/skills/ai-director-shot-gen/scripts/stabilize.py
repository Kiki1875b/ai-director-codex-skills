"""Lock a "locked-off" shot that the video model drifted: measure the translation of every frame against
frame 0 (phase correlation), shift it back, and crop/scale slightly so no black border shows.

  python stabilize.py in.mp4 out.mp4            # auto zoom from the largest drift
  python stabilize.py in.mp4 out.mp4 --zoom 1.1

Only translation is corrected (enough for small pans/tilts of inserts). Big moves or zooms: regenerate.
"""
import argparse
import subprocess
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from glow_overlay import shift_of  # noqa: E402


def frames(path, w, h, scale=1):
    vf = f"scale={w // scale}:{h // scale}" + (",format=gray" if scale > 1 else "")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-f", "rawvideo",
                          "-pix_fmt", "gray" if scale > 1 else "rgb24", "-"], stdout=subprocess.PIPE)
    ch = 1 if scale > 1 else 3
    size = (w // scale) * (h // scale) * ch
    while True:
        b = p.stdout.read(size)
        if len(b) < size:
            break
        yield np.frombuffer(b, np.uint8).reshape(h // scale, w // scale, ch)
    p.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--zoom", type=float, default=0)
    ap.add_argument("--crf", default="12")
    a = ap.parse_args()
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                         "stream=width,height,r_frame_rate", "-of", "csv=p=0", a.inp],
                        capture_output=True, text=True).stdout.strip().split(",")
    w, h, rate = int(pr[0]), int(pr[1]), pr[2]
    s = 4
    small = [f[..., 0].astype(np.float32) for f in frames(a.inp, w, h, s)]
    raw = np.array([shift_of(small[0], f) for f in small], np.float32) * s
    k = np.ones(5) / 5                                     # smooth the measured path
    off = np.stack([np.convolve(np.pad(raw[:, i], 2, mode="edge"), k, "valid") for i in range(2)], 1)
    need = max(np.abs(off[:, 0]).max() / w, np.abs(off[:, 1]).max() / h)
    zoom = a.zoom or 1 / (1 - 2 * need) + 0.01   # crop window may move by the drift on each side
    print(f"max drift dx={np.abs(off[:,0]).max():.0f}px dy={np.abs(off[:,1]).max():.0f}px -> zoom {zoom:.3f}",
          file=sys.stderr)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", rate, "-i", "-", "-c:v", "libx264", "-crf", a.crf, "-pix_fmt", "yuv420p", a.out],
                           stdin=subprocess.PIPE)
    from PIL import Image
    cw, chh = w / zoom, h / zoom
    for i, f in enumerate(frames(a.inp, w, h)):
        dx, dy = off[min(i, len(off) - 1)]
        x0 = (w - cw) / 2 + dx; y0 = (h - chh) / 2 + dy      # follow the content back to its frame-0 place
        im = Image.fromarray(f).crop((x0, y0, x0 + cw, y0 + chh)).resize((w, h), Image.LANCZOS)
        enc.stdin.write(np.asarray(im).tobytes())
    enc.stdin.close(); enc.wait()


if __name__ == "__main__":
    main()
