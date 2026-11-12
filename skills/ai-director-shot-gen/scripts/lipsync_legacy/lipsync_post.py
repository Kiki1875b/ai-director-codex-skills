"""Post-process a lip-sync result to cut skin shimmer: keep the model's pixels only around the mouth.

  python lipsync_post.py --orig shot.mp4 --synced synced_noaudio.mp4 --out out.mp4 [--audio voice.wav]
                         [--margin 0.35 --feather 9]

Why: the model regenerates the whole lower face every frame, so cheek/chin skin "boils" (S3-5 1.6: cheek
frame-to-frame change 0.87-0.95 vs original 0.63-0.78). The original's skin is stable, so only the mouth needs the
model. Mask per frame = union of the lip outlines in the original and the synced frame, grown by --margin x mouth
width (covers the jaw-side skin the lips move into).
Feathered edge so no seam.
"""
import argparse, subprocess, sys
import numpy as np, cv2, mediapipe as mp

OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]


def load(p, n=None):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok or (n and len(F) >= n): break
        F.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    return np.stack(F)


def track(F):
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=3, min_detection_confidence=.3)
    L, prev = [], None
    for f in F:
        h, w = f.shape[:2]
        r = fm.process(f)
        cs = [np.array([[q.x * w, q.y * h] for q in lm.landmark]) for lm in (r.multi_face_landmarks or [])]
        if not cs: L.append(L[-1] if L else None); continue
        p = max(cs, key=lambda c: np.ptp(c[:, 0])) if prev is None else min(cs, key=lambda c: np.linalg.norm(c.mean(0) - prev.mean(0)))
        L.append(p); prev = p
    fm.close()
    first = next((p for p in L if p is not None), None)
    if first is None: raise SystemExit("no face found in any frame")
    L = np.array([first if p is None else p for p in L])           # leading misses take the first found face
    from scipy.signal import savgol_filter
    return savgol_filter(L, 7, 2, axis=0) if len(L) >= 7 else L


INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
CHEEK = [50, 280]


def lift_mouth(f, P, g):
    """LatentSync paints the open mouth interior nearly black (S3-5: median L 23 vs 48 in the sync.so reference,
    relative to cheek 0.17 vs 0.33). Inside the inner-lip outline, L is remapped with a gamma curve anchored at the
    cheek brightness: dark pixels rise a lot, teeth (bright) barely change. Feathered so the lip edge stays clean."""
    h, w = f.shape[:2]
    m = np.zeros((h, w), np.uint8); cv2.fillPoly(m, [np.round(P[INNER]).astype(np.int32)], 255)
    if m.sum() < 255 * 20: return f                                   # mouth closed
    mw = np.linalg.norm(P[61] - P[291])
    m = cv2.GaussianBlur(m, (0, 0), max(1.0, mw * 0.03)).astype(np.float32) / 255.0
    lab = cv2.cvtColor(f, cv2.COLOR_RGB2LAB).astype(np.float32)
    cheek = np.zeros((h, w), np.uint8)
    for c in CHEEK: cv2.circle(cheek, tuple(np.round(P[c]).astype(int)), max(2, int(mw * 0.08)), 255, -1)
    ref = max(60.0, float(lab[..., 0][cheek > 0].mean()))
    L = lab[..., 0]; lifted = np.where(L < ref, ref * (np.clip(L, 0, None) / ref) ** g, L)
    lab[..., 0] = L * (1 - m) + lifted * m
    lab[..., 1] = lab[..., 1] + 4.0 * m * (1 - np.clip(L / ref, 0, 1))  # a little warmth in the dark part (not grey)
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def mouth_box(P, f):
    h, w = f.shape[:2]; cx, cy = P[13]; mw = np.linalg.norm(P[61] - P[291])
    return slice(max(0, int(cy - mw * 0.6)), min(h, int(cy + mw * 0.6))), slice(max(0, int(cx - mw * 0.9)), min(w, int(cx + mw * 0.9)))


def lap_var(img):
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())


def lip_edge(img, P):
    """Mean gradient magnitude across the outer lip border (the vermilion edge), sampled at the outline points.
    Texture/noise elsewhere in the mouth box does not count, so a soft lip line is detected even on grainy skin."""
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 1.0)
    h, w = g.shape; pts = np.round(P[OUTER]).astype(int)
    return float(np.mean([mag[min(h - 1, max(0, y)), min(w - 1, max(0, x))] for x, y in pts])) + 1e-6


def unsharp(img, amount, sigma=1.2):
    b = cv2.GaussianBlur(img, (0, 0), sigma)
    return np.clip(img.astype(np.float32) * (1 + amount) - b.astype(np.float32) * amount, 0, 255).astype(np.uint8)


def pick_sharpen(O, S, LO, LS, idx):
    """LatentSync redraws the face at 512 px, so lip edges come out softer than the original (lip border blur the user
    pointed at; sharpness ratio 0.7-0.78). Choose the unsharp amount whose mouth-box Laplacian variance matches the
    original's on sample frames."""
    ref = np.median([lip_edge(O[i], LO[i]) for i in idx])
    best, err = 0.0, 1e9
    for a in (0.0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0):
        v = np.median([lip_edge(unsharp(S[i], a), LS[i]) for i in idx])
        if abs(np.log(v / ref)) < err: best, err = a, abs(np.log(v / ref))
    return best, ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True); ap.add_argument("--synced", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--audio"); ap.add_argument("--margin", type=float, default=0.35); ap.add_argument("--feather", type=int, default=9)
    ap.add_argument("--mask-png", help="save the middle frame's mask here")
    ap.add_argument("--sharpen", type=float, default=None, help="unsharp amount on the model's mouth (default: auto-match the original)")
    ap.add_argument("--mouth-gamma", type=float, default=0.58,
                    help="lift the dark mouth interior (1.0 = off); 0.58 matches the sync.so reference on S3-5")
    a = ap.parse_args()
    O = load(a.orig); S = load(a.synced, len(O)); n = min(len(O), len(S)); O, S = O[:n], S[:n]
    LO, LS = track(O), track(S)
    if a.sharpen is None:
        amt, ref = pick_sharpen(O, S, LO, LS, list(range(0, n, max(1, n // 12))))
        print(f"mouth sharpen amount {amt} (original lip-edge gradient {ref:.1f})")
    else: amt = a.sharpen
    if amt > 0: S = np.stack([unsharp(f, amt) for f in S])
    out = np.empty_like(O)
    for i in range(n):
        m = np.zeros(O.shape[1:3], np.uint8)
        for p in (LO[i], LS[i]):
            cv2.fillPoly(m, [np.round(p[OUTER]).astype(np.int32)], 255)
        mw = np.linalg.norm(LS[i][61] - LS[i][291])
        k = max(3, int(mw * a.margin) // 2 * 2 + 1)
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        m = cv2.GaussianBlur(m, (0, 0), a.feather).astype(np.float32)[..., None] / 255.0
        out[i] = np.clip(O[i] * (1 - m) + S[i] * m, 0, 255).astype(np.uint8)
        if a.mouth_gamma < 1.0:
            out[i] = lift_mouth(out[i], LS[i], a.mouth_gamma)
        if a.mask_png and i == n // 2: cv2.imwrite(a.mask_png, (m[..., 0] * 255).astype(np.uint8))
    h, w = out.shape[1:3]
    fps = cv2.VideoCapture(a.orig).get(cv2.CAP_PROP_FPS)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}", "-i", "-"]
    if a.audio: cmd += ["-i", a.audio, "-af", "apad", "-shortest", "-c:a", "aac", "-b:a", "192k"]  # endless pad + shortest = video length
    cmd += ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE); p.stdin.write(out.tobytes()); p.stdin.close(); p.wait()
    print("wrote", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
