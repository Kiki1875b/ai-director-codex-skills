"""Score lip-sync results against the original shot and a REFERENCE result (the target look, e.g. sync.so sync-3).

  python lipsync_eval.py --orig shot.mp4 --audio dialogue.wav --ref ref.mp4 cand1.mp4 [cand2.mp4 ...] [--json out.json]

All clips must be the same shot with the same frame count (24 fps). The audio must sit on the shot timeline.
Metrics (per clip):
  lag_f      frames the mouth trails (+) / leads (-) the voice (best cross-correlation of mouth gap vs loudness);
             target = the reference's lag +-1 (the reference timing is what looked right; S3-5 sync-3 = +4)
  sync       correlation of mouth gap vs loudness at that best lag
  ref_corr   correlation of this clip's mouth-opening curve with the reference's (does it move like the reference?)
  amp        mouth opening while speaking / reference's (1.0 = same size of movement)
  width      mouth width change while speaking / reference's
  teeth      share of bright pixels inside the inner lips while open / reference's
  sharp      mouth-box sharpness (Laplacian variance) / original's
  lip_jit    lip landmark shake (2nd difference, px) / original's
  eye_jit    eye landmark shake / original's (should stay ~1.0)
  outside    mean pixel change outside the face (0-255), should be at re-encode level
  halo       share of pale, colourless pixels on the lip border (worst 5% of frames); target <= max(orig, ref)+0.03
TARGETS: the reference's own values define the target band; PASS needs every metric inside it.
"""
import argparse, json, subprocess, sys
import numpy as np, cv2, mediapipe as mp

OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]


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
        r = fm.process(f); h, w = f.shape[:2]
        cands = [np.array([[q.x * w, q.y * h] for q in lm.landmark]) for lm in (r.multi_face_landmarks or [])]
        if not cands:
            L.append(L[-1] if L else np.full((468, 2), np.nan)); continue
        p = max(cands, key=lambda c: np.ptp(c[:, 0])) if prev is None else \
            min(cands, key=lambda c: np.linalg.norm(c.mean(0) - prev.mean(0)))
        L.append(p); prev = p
    fm.close()
    return np.array(L)


def envelope(wav, n, fps=24):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-f", "f32le", "-ac", "1", "-ar", "24000", "-"],
                         capture_output=True).stdout
    x = np.abs(np.frombuffer(raw, np.float32)); hop = 24000 // fps
    return np.array([x[i * hop:(i + 1) * hop].mean() if i * hop < len(x) else 0 for i in range(n)])


def lagcorr(a, b, maxlag=6):
    best = (-9, 0)
    for l in range(-maxlag, maxlag + 1):
        x, y = (a[l:], b[:len(b) - l]) if l >= 0 else (a[:l], b[-l:])
        c = np.corrcoef(x, y)[0, 1]
        if c > best[0]: best = (c, l)
    return best


def measure(F, L, O, LO, env, speech):
    face_h = np.linalg.norm(L[:, 10] - L[:, 152], axis=-1)
    gap = np.linalg.norm(L[:, 13] - L[:, 14], axis=-1) / face_h
    width = np.linalg.norm(L[:, 61] - L[:, 291], axis=-1) / face_h
    sync, lag = lagcorr(gap, env)
    # mouth box from the original's landmarks (stable across clips)
    m = LO[:, [61, 291, 0, 17, 152]]
    x1, x2 = int(np.nanmin(m[..., 0])) - 10, int(np.nanmax(m[..., 0])) + 10
    y1, y2 = int(np.nanmin(LO[:, 1, 1])), int(np.nanmax(LO[:, 152, 1]))
    lap = np.mean([cv2.Laplacian(cv2.cvtColor(f[y1:y2, x1:x2], cv2.COLOR_RGB2GRAY), cv2.CV_64F).var() for f in F])
    teeth = []
    for f, p, g in zip(F, L, gap):
        if g < 0.02: continue
        mk = np.zeros(f.shape[:2], np.uint8); cv2.fillPoly(mk, [np.round(p[INNER]).astype(np.int32)], 1)
        # teeth = mouth-interior pixels as bright as the lips but much less saturated (relative: works in dim scenes;
        # a fixed V>150 threshold read 0 teeth on the original although teeth are visible - S3-5 v3 strip)
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)
        lipm = np.zeros(f.shape[:2], np.uint8); cv2.fillPoly(lipm, [np.round(p[OUTER]).astype(np.int32)], 1); lipm[mk > 0] = 0
        lip = hsv[lipm > 0]; px = hsv[mk > 0]
        if len(px) and len(lip):
            teeth.append(((px[:, 2] > np.median(lip[:, 2]) * 0.9) & (px[:, 1] < np.median(lip[:, 1]) * 0.6)).mean())
    # pale halo on the lip border (S3-5 1.6 cfg2.25: lip edges turned whitish when puckered). Band = +-4 px around the
    # outer lip line; halo pixel = lighter than the skin just outside AND much less red than the lips. Worst 5% frames.
    halo = []
    for f, p in zip(F, L):
        poly = np.round(p[OUTER]).astype(np.int32)
        lipm = np.zeros(f.shape[:2], np.uint8); cv2.fillPoly(lipm, [poly], 1)
        band = cv2.dilate(lipm, np.ones((9, 9), np.uint8)) - cv2.erode(lipm, np.ones((9, 9), np.uint8))
        skin = cv2.dilate(lipm, np.ones((31, 31), np.uint8)) - cv2.dilate(lipm, np.ones((15, 15), np.uint8))
        lab = cv2.cvtColor(f, cv2.COLOR_RGB2LAB).astype(np.float32)
        sk, bd, lp = lab[skin > 0], lab[band > 0], lab[cv2.erode(lipm, np.ones((7, 7), np.uint8)) > 0]
        if len(sk) and len(bd) and len(lp):
            halo.append(((bd[:, 0] > np.median(sk[:, 0]) + 6) & (bd[:, 1] < np.median(lp[:, 1]) - 0.5 * (np.median(lp[:, 1]) - np.median(sk[:, 1])))).mean())
    halo = float(np.percentile(halo, 95)) if halo else 0.0
    j = lambda idx: np.linalg.norm(L[2:, idx] - 2 * L[1:-1, idx] + L[:-2, idx], axis=-1).mean()
    fx1, fx2 = int(np.nanmin(LO[..., 0])) - 40, int(np.nanmax(LO[..., 0])) + 40
    out = np.ones(F.shape[1:3], bool); out[:, max(0, fx1):fx2] = False
    outside = np.abs(F.astype(np.int16) - O.astype(np.int16)).mean(-1)[:, out].mean()
    return dict(gap=gap, lag_f=lag, sync=sync, amp=gap[speech].mean(), width=width[speech].std(),
                teeth=float(np.mean(teeth)) if teeth else 0.0, sharp=lap, lip_jit=j([61, 291, 0, 17]),
                eye_jit=j([33, 263, 133, 362]), outside=outside, halo=halo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True); ap.add_argument("--audio", required=True); ap.add_argument("--ref", required=True)
    ap.add_argument("cands", nargs="+"); ap.add_argument("--json")
    a = ap.parse_args()
    O = load(a.orig); n = len(O)
    env = envelope(a.audio, n); speech = env > env.max() * 0.08
    LO = track(O)
    clips = {"original": (O, LO)}
    for p in [a.ref] + a.cands:
        F = load(p, n)
        if len(F) != n: sys.exit(f"{p}: {len(F)} frames, original has {n}")
        clips[p] = (F, track(F))
    M = {k: measure(F, L, O, LO, env, speech) for k, (F, L) in clips.items()}
    o, r = M["original"], M[a.ref]
    rows = {}
    for k, m in M.items():
        rows[k] = dict(lag_f=m["lag_f"], sync=round(m["sync"], 2),
                       ref_corr=round(lagcorr(m["gap"], r["gap"], 2)[0], 2),
                       amp=round(m["amp"] / r["amp"], 2), width=round(m["width"] / (r["width"] + 1e-9), 2),
                       teeth=round(m["teeth"] / (r["teeth"] + 1e-9), 2), sharp=round(m["sharp"] / o["sharp"], 2),
                       lip_jit=round(m["lip_jit"] / o["lip_jit"], 2), eye_jit=round(m["eye_jit"] / o["eye_jit"], 2),
                       outside=round(m["outside"], 2), halo=round(m["halo"], 3))
    R = rows[a.ref]
    band = dict(lag_f=(R["lag_f"] - 1, R["lag_f"] + 1), sync=(R["sync"] - 0.07, 1), ref_corr=(0.8, 1), amp=(0.85, 1.15), width=(0.8, 1.25),
                teeth=(0.7, 1.4), sharp=(R["sharp"] * 0.9, 9), lip_jit=(0, max(1.4, R["lip_jit"] * 1.1)),
                eye_jit=(0, 1.15), outside=(0, max(2.5, R["outside"] * 1.2)),
                halo=(0, max(rows["original"]["halo"], R["halo"]) + 0.03))
    cols = list(band)
    print(f"{'clip':42s} " + " ".join(f"{c:>8s}" for c in cols) + "  verdict")
    print(f"{'TARGET':42s} " + " ".join(f"{band[c][0]:>4.2g}~{band[c][1]:<3.3g}" for c in cols))
    for k, v in rows.items():
        bad = [c for c in cols if not (band[c][0] <= v[c] <= band[c][1])]
        v["fail"] = bad
        name = k if len(k) <= 42 else "..." + k[-39:]
        print(f"{name:42s} " + " ".join(f"{v[c]:>8}" for c in cols) + ("  PASS" if not bad else "  fail: " + ",".join(bad)))
    if a.json:
        json.dump(dict(target=band, rows=rows), open(a.json, "w", encoding="utf8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
