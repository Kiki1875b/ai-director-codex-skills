"""Paste a SeedVR2-restored face crop back onto a lip-synced shot, lower face only (nose bridge down, inside the jaw).

  python sv_mouth_composite.py --orig shot.mp4 --synced synced.mp4 --sv crop_sv.mp4 --crop x,y,w,h --audio voice.wav --out out.mp4

orig  : the original shot (landmarks are tracked on it, so the mask follows the real face)
synced: the LatentSync result (full frame) the crop was cut from
sv    : SeedVR2 output of that crop (any scale; resized back to w x h, trimmed to the shot's frame count)
Eyes, hair and background stay the synced (= original) pixels.
"""
import argparse, os, re, subprocess, sys
import numpy as np, cv2, mediapipe as mp

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "..", "remote", "latentsync_run.py")      # helpers are read from this file, not run


def load(p):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok: break
        F.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    return np.stack(F)


def helpers():
    """Reuse track_face / smooth / lower_face_mask from latentsync_run.py (same mask as the lip-sync pass)."""
    src = open(RUN, encoding="utf8").read()
    g = {"np": np, "cv2": cv2, "mp": mp}
    for name in ["track_face", "smooth", "lower_face_mask"]:
        exec(re.search(rf"\ndef {name}\(.*?(?=\n\S)", src, re.S).group(0), g)
    return g


def main():
    ap = argparse.ArgumentParser()
    for k in ["orig", "synced", "sv", "crop", "audio", "out"]: ap.add_argument("--" + k, required=k != "audio")
    ap.add_argument("--feather", type=int, default=15)
    a = ap.parse_args()
    x, y, w, h = map(int, a.crop.split(","))
    O, S, V = load(a.orig), load(a.synced), load(a.sv)
    n = min(len(O), len(S)); O, S = O[:n], S[:n]
    if len(V) < n: sys.exit(f"sv has {len(V)} frames < {n}")
    V = np.stack([cv2.resize(v, (w, h), interpolation=cv2.INTER_AREA) for v in V[:n]])
    g = helpers()
    L = g["smooth"](g["track_face"](O))
    M = g["lower_face_mask"](L, O.shape[1], O.shape[2], a.feather)[:, y:y + h, x:x + w, None]
    out = S.copy()
    reg = out[:, y:y + h, x:x + w].astype(np.float32)
    # match the restored crop's mean colour to the synced crop inside the mask (SeedVR2 can shift tone slightly)
    m = M[..., 0] > 0.5
    shift = np.array([(reg[..., c][m] - V[..., c].astype(np.float32)[m]).mean() for c in range(3)])
    print("colour shift applied", shift.round(2))
    Vc = np.clip(V.astype(np.float32) + shift, 0, 255)
    out[:, y:y + h, x:x + w] = np.clip(reg * (1 - M) + Vc * M, 0, 255).astype(np.uint8)
    fps = cv2.VideoCapture(a.orig).get(cv2.CAP_PROP_FPS)
    H, W = out.shape[1:3]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps:.6f}", "-i", "-"]
    if a.audio: cmd += ["-i", a.audio, "-af", "apad", "-shortest", "-c:a", "aac", "-b:a", "192k"]  # endless pad + shortest = video length
    cmd += ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE); p.stdin.write(out.tobytes()); p.stdin.close(); p.wait()
    print("wrote", a.out)


if __name__ == "__main__":
    main()
