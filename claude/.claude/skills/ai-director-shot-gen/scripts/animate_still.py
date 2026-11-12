"""Turn a still keyframe into a short video clip with a camera move (animatic fallback).

Codex can make images but not video. Until a video model is connected, each shot can be
an animated still: push-in, pull-out, pan or static, with ffmpeg zoompan.

Usage:
  python animate_still.py media/S1-1-key-v1.png media/S1-1-v1.mp4 --dur 5 --move push-in \
      [--width 1920 --height 1080 --fps 30 --amount 0.12]
Moves: static | push-in | pull-out | pan-left | pan-right | pan-up | pan-down
"""
import argparse
import shutil
import subprocess
import sys


def image_size(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def fit_filter(fit, w, h):
    W, H = w * 4, h * 4
    if fit == "pad":
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
    if fit == "blur":
        return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40[bg];"
                f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def zoompan(move, frames, amount, w, h, fps, fit="crop"):
    n = max(frames - 1, 1)
    z_in = f"1+{amount}*on/{n}"
    z_out = f"1+{amount}-{amount}*on/{n}"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    span_x, span_y = "(iw-iw/zoom)", "(ih-ih/zoom)"
    table = {
        "static": ("1", cx, cy),
        "push-in": (z_in, cx, cy),
        "pull-out": (z_out, cx, cy),
        "pan-right": (f"1+{amount}", f"{span_x}*on/{n}", cy),
        "pan-left": (f"1+{amount}", f"{span_x}*(1-on/{n})", cy),
        "pan-down": (f"1+{amount}", cx, f"{span_y}*on/{n}"),
        "pan-up": (f"1+{amount}", cx, f"{span_y}*(1-on/{n})"),
    }
    z, x, y = table[move]
    # upscale first so the crop window moves smoothly (zoompan rounds to whole pixels)
    return (f"{fit_filter(fit, w, h)},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--dur", type=float, default=5)
    ap.add_argument("--move", default="push-in",
                    choices=["static", "push-in", "pull-out", "pan-left", "pan-right", "pan-up", "pan-down"])
    ap.add_argument("--amount", type=float, default=0.12, help="zoom amount (0.12 = 12%%)")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fit", choices=["crop", "pad", "blur"], default="crop",
                    help="how to fit a still whose aspect differs from the output (default crop)")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    if not 0 < args.amount <= 1:
        sys.exit("--amount must be in (0, 1]")
    if args.width % 2 or args.height % 2:
        sys.exit("--width and --height must be even (H.264 yuv420p)")
    size = image_size(args.image)
    if size and args.fit == "crop":
        src_ar, dst_ar = size[0] / size[1], args.width / args.height
        if abs(src_ar / dst_ar - 1) > 0.1:
            kept = min(src_ar, dst_ar) / max(src_ar, dst_ar)
            print(f"WARN {args.image} is {size[0]}x{size[1]}; crop keeps only {kept:.0%} of it. "
                  f"Use --fit pad|blur or regenerate the still in the output aspect.", file=sys.stderr)
    frames = max(int(round(args.dur * args.fps)), 1)
    vf = zoompan(args.move, frames, args.amount, args.width, args.height, args.fps, args.fit)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", args.image,
           "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", args.out]
    res = subprocess.run(cmd)
    if res.returncode:
        sys.exit(f"ffmpeg failed with code {res.returncode}")
    print(f"done: {args.out} ({args.dur}s, {args.move})")


if __name__ == "__main__":
    main()
