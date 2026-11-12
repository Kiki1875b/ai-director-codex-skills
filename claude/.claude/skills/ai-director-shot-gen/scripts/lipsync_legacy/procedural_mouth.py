"""Open and close a closed mouth in time with the voice by warping the lower lip and jaw down (no lip-sync model).

  python procedural_mouth.py --video face_crop.mp4 --audio voice.wav --out out.mp4 [--max-open 0.05] [--lead 0.04]

For faces where LatentSync keeps the mouth shut (S3-7: 3/4 profile looking down; guidance 1.75 and 2.5 both gave a
max lip gap of 1.1-1.2 % of face height vs 4-7 % when speaking). Per frame (MediaPipe on the upscaled crop):
  - opening d(t) = max_open x face height x voice loudness (16 ms frames, fast attack 30 ms / release 90 ms, shifted
    --lead s earlier because the mouth opens a little before the sound);
  - everything below the inner-lip line, inside the mouth width, is pulled down by d x w, where w falls off with a
    cosine across the mouth (0 at the corners) and linearly to 0 at 1.6 x mouth width below the line (jaw);
  - the opened band between the lips is filled with a dark, warm mouth-interior colour (L = 0.3 x cheek), feathered.
"""
import argparse, subprocess, sys
import numpy as np, cv2, mediapipe as mp

UPPER_INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]


def load(p):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok: break
        F.append(f)
    return F, c.get(cv2.CAP_PROP_FPS)


def envelope(path, fps, n, lead):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32); hop = 256
    e = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, len(x) - hop, hop)])
    e = np.clip(20 * np.log10(e + 1e-9) - (20 * np.log10(e.max() + 1e-9) - 30), 0, 30) / 30   # 0..1 over the top 30 dB
    a, r = np.exp(-hop / 16000 / 0.03), np.exp(-hop / 16000 / 0.09); s = 0.0; out = []
    for v in e:
        s = a * s + (1 - a) * v if v > s else r * s + (1 - r) * v
        out.append(s)
    out = np.array(out); t = np.arange(len(out)) * hop / 16000
    return np.interp(np.arange(n) / fps + lead, t, out, left=0, right=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True); ap.add_argument("--audio", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--max-open", type=float, default=0.05); ap.add_argument("--lead", type=float, default=0.04)
    a = ap.parse_args()
    F, fps = load(a.video); n = len(F)
    env = envelope(a.audio, fps, n, a.lead)
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=.3)
    prev = None; out = []
    for i, f in enumerate(F):
        r = fm.process(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)); h, w = f.shape[:2]
        if r.multi_face_landmarks: prev = np.array([[q.x * w, q.y * h] for q in r.multi_face_landmarks[0].landmark])
        P = prev
        if P is None or env[i] < 0.02: out.append(f); continue
        fh = np.linalg.norm(P[10] - P[152]); d = a.max_open * fh * env[i]
        x0, x1 = P[61][0], P[291][0]
        if x0 > x1: x0, x1 = x1, x0
        mw = x1 - x0; up = P[UPPER_INNER]
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        line = np.interp(xs, up[:, 0][np.argsort(up[:, 0])], up[:, 1][np.argsort(up[:, 0])])   # inner upper-lip line y(x)
        u = np.clip((xs - x0) / max(mw, 1), 0, 1)
        wx = np.where((xs > x0) & (xs < x1), np.sin(np.pi * u), 0)                          # 0 at corners, 1 at centre
        below = ys - line
        wy = np.clip(1 - below / (1.6 * mw), 0, 1) * (below > 0)
        disp = d * wx * wy
        src_y = (ys - disp).astype(np.float32)
        g = cv2.remap(f, xs, src_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        gap = ((below > 0) & (below < d * wx)).astype(np.float32)                              # the opened band
        gap = cv2.GaussianBlur(gap, (0, 0), max(0.8, d * 0.25))[..., None]
        lab = cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32)
        cheek = lab[int(P[50][1]) - 3:int(P[50][1]) + 3, int(P[50][0]) - 3:int(P[50][0]) + 3, 0].mean()
        inside = np.array([0.3 * cheek, 150, 140], np.float32)                                   # dark, warm (LAB)
        fill = cv2.cvtColor(np.full((1, 1, 3), inside, np.uint8), cv2.COLOR_LAB2BGR)[0, 0].astype(np.float32)
        out.append(np.clip(g * (1 - gap) + fill * gap, 0, 255).astype(np.uint8))
    hh, ww = out[0].shape[:2]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ww}x{hh}", "-r", f"{fps:.6f}", "-i", "-",
           "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE); p.stdin.write(np.stack(out).tobytes()); p.stdin.close(); p.wait()
    print("wrote", a.out, "max opening %.1f px" % (a.max_open * np.max(env) * (np.linalg.norm(prev[10] - prev[152]) if prev is not None else 0)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
