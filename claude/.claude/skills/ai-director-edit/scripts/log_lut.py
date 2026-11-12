"""LOG originals + LUT grading for stills (keyframes) and the conti.

  to-log   : Rec.709 still -> Sony S-Log3 encoded still (flat 'camera original', mid grey 18% -> 0.41)
  make-lut : write a 33^3 .cube LUT that takes S-Log3 in and gives a graded Rec.709 look out
  apply    : apply a .cube to an image with ffmpeg lut3d (same filter you would use on video)

Looks (make-lut --look):
  sl-blue  : S-Log3 -> 709 with a cool steel-blue night look: blue-cyan shadows, slightly muted mids,
             skin and tungsten practicals kept warm, soft highlight roll-off. Default fallback look when no
             genre-specific reference grade is available.

Usage:
  python log_lut.py to-log in.png out_log.png
  python log_lut.py make-lut --look sl-blue out.cube
  python log_lut.py apply in_log.png look.cube out.png
"""
import argparse
import colorsys
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

# ---- transfer functions -------------------------------------------------------------------------
def rec709_to_linear(v):
    v = np.asarray(v, np.float64)
    return np.where(v < 0.081, v / 4.5, ((v + 0.099) / 1.099) ** (1 / 0.45))

def linear_to_rec709(l):
    l = np.clip(l, 0, None)
    return np.where(l < 0.018, l * 4.5, 1.099 * np.power(l, 0.45) - 0.099)

def slog3_encode(x):
    x = np.asarray(x, np.float64)
    return np.where(x >= 0.01125000,
                    (420.0 + np.log10(np.maximum(x + 0.01, 1e-9) / (0.18 + 0.01)) * 261.5) / 1023.0,
                    (x * (171.2102946929 - 95.0) / 0.01125000 + 95.0) / 1023.0)

def slog3_decode(y):
    y = np.asarray(y, np.float64)
    return np.where(y >= 171.2102946929 / 1023.0,
                    np.power(10.0, (y * 1023.0 - 420.0) / 261.5) * (0.18 + 0.01) - 0.01,
                    (y * 1023.0 - 95.0) * 0.01125000 / (171.2102946929 - 95.0))

# ---- looks --------------------------------------------------------------------------------------
def filmic(x, white=6.0):
    """Soft shoulder tone curve on scene-linear; mid grey 0.18 stays near 0.18."""
    a = x * (1 + x / (white * white)) / (1 + x)
    return a * (0.18 * (1 + 0.18) / (0.18 * (1 + 0.18 / (white * white))))

def look_sl_blue(rgb_log):
    lin = slog3_decode(rgb_log)
    lin = np.clip(lin, 0, None) * 1.0
    lin = lin * np.array([0.95, 0.99, 1.07])               # cooler white balance
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    t = filmic(lin)
    tl = filmic(lum)[..., None]
    disp = linear_to_rec709(t)
    dl = linear_to_rec709(tl)
    # split tone: shadows -> steel blue/cyan, highlights -> neutral-warm
    sh = np.clip(1 - dl / 0.45, 0, 1) ** 1.5
    hi = np.clip((dl - 0.6) / 0.4, 0, 1)
    disp = disp + sh * np.array([-0.035, 0.0, 0.055]) + hi * np.array([0.02, 0.008, -0.02])
    # saturation: overall muted, skin/tungsten hues protected
    out = np.empty_like(disp)
    flat = disp.reshape(-1, 3)
    o = out.reshape(-1, 3)
    for i, (r, g, b) in enumerate(np.clip(flat, 0, 1)):
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        warm = 1.0 if (0.02 <= h <= 0.14) else 0.0          # ~7-50 deg: skin, tungsten, tarp
        s *= 0.80 + 0.15 * warm
        o[i] = colorsys.hls_to_rgb(h, l, s)
    # slight black lift kept tiny, gentle contrast
    out = 0.012 + out * 0.985
    return np.clip(out, 0, 1)

LOOKS = {"sl-blue": look_sl_blue}

def make_lut(look, path, n=33):
    g = np.linspace(0, 1, n)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")          # .cube order: R fastest
    grid = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = LOOKS[look](grid)
    with open(path, "w", encoding="ascii") as f:
        f.write(f'TITLE "{look} (S-Log3 in, Rec709 out)"\nLUT_3D_SIZE {n}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        for v in out:
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
    return path

def to_log(src, dst):
    a = np.asarray(Image.open(src).convert("RGB")).astype(np.float64) / 255
    lin = rec709_to_linear(a)
    Image.fromarray((np.clip(slog3_encode(lin), 0, 1) * 255 + 0.5).astype(np.uint8)).save(dst)

def apply(src, cube, dst):
    ff = shutil.which("ffmpeg")
    if not ff:
        sys.exit("ffmpeg not found")
    c = cube.replace("\\", "/").replace(":", "\\:")
    subprocess.run([ff, "-y", "-v", "error", "-i", src, "-vf", f"lut3d=file='{c}':interp=tetrahedral", dst], check=True)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("to-log"); a.add_argument("src"); a.add_argument("dst")
    b = sp.add_parser("make-lut"); b.add_argument("--look", default="sl-blue", choices=sorted(LOOKS)); b.add_argument("out")
    c = sp.add_parser("apply"); c.add_argument("src"); c.add_argument("cube"); c.add_argument("dst")
    x = ap.parse_args()
    if x.cmd == "to-log": to_log(x.src, x.dst)
    elif x.cmd == "make-lut": make_lut(x.look, x.out)
    else: apply(x.src, x.cube, x.dst)
    print("ok")

if __name__ == "__main__":
    main()
