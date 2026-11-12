"""Composite a soft light glow at a FIXED spot of a clip (AI video models smear/move small light sources).

  python glow_overlay.py in.mp4 out.mp4 --x 0.615 --y 0.69 --radius 0.11 --color 70,150,255 \
      --curve "0:0,1.2:0.35,2.2:0.9,3.0:0.75,4.0:1.0"      # time(s):intensity keyframes, linear
  python glow_overlay.py key.png test.png ...               # still test (uses the last curve value)

The glow is light shining through cloth: a wide soft halo plus a smaller hot core, added on top of the
frame and modulated by the frame's own texture so the fibres stay visible (it never looks like a sticker).
"""
import argparse
import subprocess
import sys

import numpy as np


def curve_fn(spec):
    pts = sorted((float(a), float(b)) for a, b in (p.split(":") for p in spec.split(",")))
    ts, vs = zip(*pts)
    return lambda t: float(np.interp(t, ts, vs))


def shift_of(ref, cur):
    """Translation (dx, dy) of cur relative to ref by phase correlation (grayscale float arrays)."""
    win = np.outer(np.hanning(ref.shape[0]), np.hanning(ref.shape[1]))
    F = np.fft.fft2(ref * win) * np.conj(np.fft.fft2(cur * win))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-6)).real
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    h, w = ref.shape
    if dy > h // 2: dy -= h
    if dx > w // 2: dx -= w
    return -dx, -dy


def glow_layer(h, w, a, off=(0.0, 0.0)):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy, r = a.x * w + off[0], a.y * h + off[1], a.radius * w
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (r * r)
    halo = np.exp(-d2 * 1.2)                # wide soft spill
    core = np.exp(-d2 * 6.0)                # brighter centre, still soft
    return halo * 0.55 + core * 0.9


def apply(frame, g, k, col, a):
    f = frame.astype(np.float32) / 255.0
    lum = f.mean(axis=2, keepdims=True)
    tex = 0.55 + 0.9 * np.clip(lum / (lum.mean() + 1e-4), 0, 2.5) * 0.5   # fibres catch more light
    add = (g * k)[..., None] * col[None, None, :] * tex * a.gain
    out = 1 - (1 - f) * (1 - np.clip(add, 0, 1))                          # screen blend
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--x", type=float, required=True, help="centre x as a fraction of width")
    ap.add_argument("--y", type=float, required=True, help="centre y as a fraction of height")
    ap.add_argument("--radius", type=float, default=0.1, help="fraction of width")
    ap.add_argument("--color", default="70,150,255")
    ap.add_argument("--gain", type=float, default=0.8)
    ap.add_argument("--curve", default="0:1")
    ap.add_argument("--crf", default="12")
    ap.add_argument("--track", action="store_true",
                    help="follow the subject: move the glow with the image drift around it (phase correlation vs frame 0)")
    a = ap.parse_args()
    col = np.array([int(c) for c in a.color.split(",")], np.float32) / 255.0
    cv = curve_fn(a.curve)

    if a.inp.lower().endswith((".png", ".jpg", ".jpeg")):
        from PIL import Image
        im = np.array(Image.open(a.inp).convert("RGB"))
        g = glow_layer(*im.shape[:2], a)
        Image.fromarray(apply(im, g, cv(1e9), col, a)).save(a.out)
        return

    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                            "stream=width,height,r_frame_rate", "-of", "csv=p=0", a.inp],
                           capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    num, den = probe[2].split("/")
    fps = float(num) / float(den)
    g = glow_layer(h, w, a)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.inp, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", probe[2], "-i", "-", "-c:v", "libx264", "-crf", a.crf, "-pix_fmt", "yuv420p",
                            a.out], stdin=subprocess.PIPE)
    n, size = 0, w * h * 3
    # tracking patch: a box around the glow, 4x downscaled
    bw, bh = int(w * 0.5), int(h * 0.6)
    x0 = int(min(max(a.x * w - bw / 2, 0), w - bw)); y0 = int(min(max(a.y * h - bh / 2, 0), h - bh))
    ref, sm = None, np.zeros(2)
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        if a.track:
            patch = fr[y0:y0 + bh:4, x0:x0 + bw:4].mean(axis=2).astype(np.float32)
            if ref is None:
                ref = patch
            else:
                d = np.array(shift_of(ref, patch), np.float32) * 4
                sm = d if n == 1 else sm * 0.5 + d * 0.5          # light smoothing against jitter
            g = glow_layer(h, w, a, tuple(sm))
        enc.stdin.write(apply(fr, g, cv(n / fps), col, a).tobytes())
        n += 1
    enc.stdin.close(); enc.wait(); dec.wait()
    print(f"{n} frames -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
