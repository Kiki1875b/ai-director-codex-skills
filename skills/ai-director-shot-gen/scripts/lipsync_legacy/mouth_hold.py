"""Stop the mouth "mumbling" after a line ends: from --start on, the mouth area is taken from one closed-mouth frame
(warped every frame to follow the head), cross-faded in over --fade frames.

  python mouth_hold.py --video shot_ls16_post.mp4 --start 1.05 --out out.mp4 [--audio voice.wav] [--hold auto|<frame>]
                       [--end <sec>] [--fade 4] [--margin 0.45]

Why: LatentSync takes each frame of the original as its reference, so when the original mouth keeps moving after the
line, the synced mouth keeps moving too (S6-3 "처음 오셨죠?": lip-shape motion 3.8-4.9 after the line vs 4.2-7.6 while
speaking). --hold auto = the frame in the first 0.5 s after --start with the smallest lip opening.
Head motion: similarity transform from stable points (eye corners, nose bridge) of the hold frame to each frame.
"""
import argparse, subprocess, sys
import numpy as np, cv2, mediapipe as mp

OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
STABLE = [33, 133, 362, 263, 168, 6, 197, 195, 1, 4]


def load(p):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok: break
        F.append(f)
    return np.stack(F), c.get(cv2.CAP_PROP_FPS)


def track(F):
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=.3)
    h, w = F.shape[1:3]; L = []
    for f in F:
        r = fm.process(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        L.append(np.array([[q.x * w, q.y * h] for q in r.multi_face_landmarks[0].landmark]) if r.multi_face_landmarks else L[-1])
    from scipy.signal import savgol_filter
    return savgol_filter(np.array(L), 7, 2, axis=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True); ap.add_argument("--out", required=True); ap.add_argument("--audio")
    ap.add_argument("--start", type=float, required=True); ap.add_argument("--end", type=float)
    ap.add_argument("--hold", default="auto"); ap.add_argument("--fade", type=int, default=4)
    ap.add_argument("--margin", type=float, default=0.45)
    a = ap.parse_args()
    F, fps = load(a.video); n = len(F); L = track(F)
    s = int(round(a.start * fps)); e = n if a.end is None else int(round(a.end * fps))
    gap = np.linalg.norm(L[:, 13] - L[:, 14], axis=-1) / np.linalg.norm(L[:, 10] - L[:, 152], axis=-1)
    if a.hold == "auto":
        win = range(s, min(n, s + int(0.5 * fps)) + 1)
        k = min(win, key=lambda i: gap[i])
    else:
        k = int(a.hold)
    print(f"hold frame {k} ({k / fps:.2f}s, lip gap {gap[k]:.3f}); replacing frames {s}-{e - 1}")
    out = F.copy(); h, w = F.shape[1:3]
    for i in range(s, e):
        M, _ = cv2.estimateAffinePartial2D(L[k, STABLE].astype(np.float32), L[i, STABLE].astype(np.float32))
        held = cv2.warpAffine(F[k], M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        lk = cv2.transform(L[k][None, OUTER].astype(np.float32), M)[0]
        m = np.zeros((h, w), np.uint8)
        for p in (lk, L[i, OUTER]): cv2.fillPoly(m, [np.round(p).astype(np.int32)], 255)
        mw = np.linalg.norm(L[i, 61] - L[i, 291]); ks = max(3, int(mw * a.margin) // 2 * 2 + 1)
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
        m = cv2.GaussianBlur(m, (0, 0), max(3, ks / 4)).astype(np.float32)[..., None] / 255.0
        wgt = min(1.0, (i - s + 1) / (a.fade + 1))
        if a.end is not None: wgt = min(wgt, (e - i) / (a.fade + 1))
        m *= wgt
        # match brightness of the held patch to the current frame around the mouth (lighting flicker)
        ring = (m[..., 0] > 0.05) & (m[..., 0] < 0.5)
        if ring.any(): held = np.clip(held.astype(np.float32) + (F[i][ring].mean(0) - held[ring].mean(0)), 0, 255)
        out[i] = np.clip(F[i] * (1 - m) + held * m, 0, 255).astype(np.uint8)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}", "-i", "-"]
    if a.audio: cmd += ["-i", a.audio, "-af", "apad", "-shortest", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE); p.stdin.write(out.tobytes()); p.stdin.close(); p.wait()
    print("wrote", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
