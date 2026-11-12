"""Static shot from a still: a key image + moving rain layers + temporal grain.

Wan 2.2 I2V drifts or pushes in on near-static night shots even with "locked-off"
(S1 2026-11-08: 6 of 6 clips moved). For a wide where nothing but rain should move,
this makes a truly locked shot. Rain brightness follows the light in the picture
(streaks show where they cross lamp or tent light), three depth layers.

  python still_rain.py KEY.png OUT.mp4 --dur 5 [--density 1.0] [--seed 1]
       [--keep x0,y0,x1,y1 ...]   regions where no rain is drawn in front (none by default)
"""
import argparse, subprocess, json
import numpy as np
from PIL import Image, ImageFilter

W, H, FPS = 1280, 720, 24

LAYERS = [  # count per frame-area, length px, speed px/frame, alpha, width blur
    dict(n=900, length=18, speed=34, alpha=0.26, blur=0.6),   # far: short, dim
    dict(n=420, length=34, speed=58, alpha=0.40, blur=0.9),   # mid
    dict(n=75,  length=70, speed=110, alpha=0.38, blur=1.6),  # near: long, soft (x density)
]


def light_map(img):
    g = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(25))).astype(float) / 255
    g = (g / max(g.max(), 1e-6)) ** 1.3          # streaks show mostly where it is lit
    return 0.05 + 0.95 * g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key"); ap.add_argument("out")
    ap.add_argument("--dur", type=float, default=5.0)
    ap.add_argument("--density", type=float, default=1.0)
    ap.add_argument("--angle", type=float, default=4.0, help="degrees from vertical")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--grain", type=float, default=1.2)
    ap.add_argument("--splash-y", type=int, default=0, help="ground starts at this y (1280x720); 0 = no splashes")
    ap.add_argument("--splash-n", type=int, default=90, help="new splashes per frame")
    ap.add_argument("--range", nargs=2, type=float, metavar=("IN_S", "OUT_S"), help="when KEY is a video: part to use")
    a = ap.parse_args()

    video = None
    if a.key.lower().endswith((".mp4", ".mov", ".mkv")):
        # a locked-camera clip (e.g. first+last key) as the base: rain goes on top of every frame
        cmd = ["ffmpeg", "-v", "error"] + (["-ss", str(a.range[0]), "-to", str(a.range[1])] if a.range else []) +               ["-i", a.key, "-vf", f"scale={W}:{H}", "-sws_flags", "accurate_rnd+full_chroma_int", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        video = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.uint8).reshape(-1, H, W, 3)
        base = Image.fromarray(video[0])
        a.dur = len(video) / FPS
    else:
        base = Image.open(a.key).convert("RGB").resize((W, H), Image.LANCZOS)
    B = np.asarray(base).astype(float)
    L = light_map(base)[..., None]
    keep = np.ones((H, W, 1))
    for k in a.keep:
        x0, y0, x1, y1 = map(int, k.split(","))
        keep[y0:y1, x0:x1] = 0
    rng = np.random.default_rng(a.seed)
    th = np.deg2rad(a.angle)
    drops = []
    for ly in LAYERS:
        n = int(ly["n"] * a.density)
        drops.append(dict(ly, x=rng.uniform(-50, W + 50, n), y=rng.uniform(-200, H, n),
                          v=ly["speed"] * rng.uniform(0.85, 1.15, n)))
    color = np.array([0.92, 0.95, 1.0])           # cold lamp light; tent areas tint via the base

    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-sws_flags", "accurate_rnd+full_chroma_int", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", a.out],
                           stdin=subprocess.PIPE)
    nf = int(round(a.dur * FPS))
    splashes = []
    tint = np.asarray(base.filter(ImageFilter.GaussianBlur(40))).astype(float)
    tint = tint / np.maximum(tint.max(axis=2, keepdims=True), 1)       # local light colour
    for f in range(nf):
        layer = np.zeros((H, W), np.float32)
        for d in drops:
            img = Image.new("L", (W, H), 0)
            from PIL import ImageDraw
            dr = ImageDraw.Draw(img)
            dx, dy = np.sin(th) * d["length"], np.cos(th) * d["length"]
            v = int(255 * d["alpha"])
            for x, y in zip(d["x"], d["y"]):
                dr.line([(x, y), (x + dx, y + dy)], fill=v, width=1)
            if d["blur"]:
                img = img.filter(ImageFilter.GaussianBlur(d["blur"]))
            layer = np.maximum(layer, np.asarray(img, np.float32))
            d["y"] += d["v"]; d["x"] += d["v"] * np.tan(th)
            wrap = d["y"] > H
            d["y"][wrap] -= H + 200 + rng.uniform(0, 100, wrap.sum())
            d["x"][wrap] = rng.uniform(-50, W + 50, wrap.sum())
        if a.splash_y:
            # short-lived splashes on the lit ground: a dot and a tiny crown, 2 frames each
            img = Image.new("L", (W, H), 0)
            from PIL import ImageDraw
            dr = ImageDraw.Draw(img)
            for p in splashes:
                x, y, age = p
                r_ = 1 + age
                dr.ellipse([x - r_ * 1.6, y - r_ * 0.6, x + r_ * 1.6, y + r_ * 0.6], outline=int(150 / (1 + age)))
                dr.point((x, y - 1 - age), fill=int(170 / (1 + age)))
            layer = np.maximum(layer, np.asarray(img.filter(ImageFilter.GaussianBlur(0.5)), np.float32))
            splashes = [[x, y, age + 1] for x, y, age in splashes if age < 1]
            ys = rng.uniform(a.splash_y, H, a.splash_n * 3)
            xs = rng.uniform(0, W, a.splash_n * 3)
            lit = L[ys.astype(int), xs.astype(int), 0] > rng.uniform(0.25, 1.0, ys.size)
            splashes += [[x, y, 0] for x, y in list(zip(xs[lit], ys[lit]))[:a.splash_n]]
        r = (layer[..., None] / 255) * L * keep
        if video is not None:
            B = video[f].astype(float)
        out = B + r * 255 * (0.55 * color + 0.45 * tint) * 0.9
        out += rng.normal(0, a.grain, (H, W, 1))
        enc.stdin.write(np.rint(np.clip(out, 0, 255)).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait()
    print(json.dumps({"out": a.out, "frames": nf, "fps": FPS}))


if __name__ == "__main__":
    main()
