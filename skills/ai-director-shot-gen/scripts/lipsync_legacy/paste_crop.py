"""Paste the mouth of a lip-synced, upscaled face crop back into the full-size shot.

  python paste_crop.py --full shot.mp4 --crop crop_ls16_post.mp4 --x 740 --y 0 --size 360 --out out.mp4 [--audio v.wav]

For small or angled faces (S3-7: 3/4 profile, face found in 12/97 frames at full size, 97/97 after a 2x crop) the
lip sync runs on an upscaled crop. Here each crop frame is scaled back to --size and only the mouth area is blended
into the full frame: lip outline (MediaPipe on the crop) grown by 0.6 x mouth width, feathered, so the rest of the
face keeps the original's full-resolution pixels.
"""
import argparse, subprocess, sys
import numpy as np, cv2, mediapipe as mp

OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]


def load(p):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok: break
        F.append(f)
    return F, c.get(cv2.CAP_PROP_FPS)


def main():
    ap = argparse.ArgumentParser()
    for k in ("full", "crop", "out"): ap.add_argument("--" + k, required=True)
    ap.add_argument("--x", type=int, required=True); ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--size", type=int, required=True); ap.add_argument("--audio")
    a = ap.parse_args()
    Fu, fps = load(a.full); Cr, _ = load(a.crop); n = min(len(Fu), len(Cr))
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=.3)
    s = a.size / Cr[0].shape[1]; prev = None; out = []
    for i in range(n):
        c = Cr[i]; r = fm.process(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))
        if r.multi_face_landmarks:
            prev = np.array([[q.x * c.shape[1], q.y * c.shape[0]] for q in r.multi_face_landmarks[0].landmark])
        f = Fu[i].copy()
        if prev is None: out.append(f); continue
        small = cv2.resize(c, (a.size, a.size), interpolation=cv2.INTER_AREA)
        P = prev * s
        m = np.zeros((a.size, a.size), np.uint8); cv2.fillPoly(m, [np.round(P[OUTER]).astype(np.int32)], 255)
        mw = np.linalg.norm(P[61] - P[291]); k = max(3, int(mw * 0.6) // 2 * 2 + 1)
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        m = cv2.GaussianBlur(m, (0, 0), max(2.0, mw * 0.15)).astype(np.float32)[..., None] / 255.0
        roi = f[a.y:a.y + a.size, a.x:a.x + a.size].astype(np.float32)
        f[a.y:a.y + a.size, a.x:a.x + a.size] = np.clip(roi * (1 - m) + small * m, 0, 255).astype(np.uint8)
        out.append(f)
    h, w = out[0].shape[:2]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}", "-i", "-"]
    if a.audio: cmd += ["-i", a.audio, "-af", "apad", "-shortest", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE); p.stdin.write(np.stack(out).tobytes()); p.stdin.close(); p.wait()
    print("wrote", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
