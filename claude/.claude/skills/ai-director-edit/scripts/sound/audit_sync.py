"""Audit every dialogue line of the rendered film: does a visible mouth move with the voice?

  python audit_sync.py export/picture.mp4 --story stories/<slug> [--lines cl_vo_S4-7_1 ...] [--json out.json]

--story: story folder or its story.json (required). The video and every media_url are relative to the story folder.

For each enabled tr_vo clip in story.json: decode the picture from 0.4 s before to 0.4 s after the line, track up to
3 faces with MediaPipe FaceMesh (identity by nearest face centre), and for each face compute the lip gap / face
height per frame. The voice loudness envelope (same frames) is cross-correlated with each face's lip gap at lags
-12..+12 frames. Reported per line: best face (largest correlation), its lag in frames (+ = mouth after voice),
correlation, mouth activity while speaking vs. after/before (does the mouth move when there is no voice?),
face width in px (small faces are not lip-readable), and a verdict:
  OK        corr >= 0.45 and lag in +2..+8 frames at 30 fps (reference offset +5 +-3)
  LAG       corr >= 0.45 but |lag| > 3  -> shift the line
  WEAK      0.2 <= corr < 0.45          -> check by eye
  NO-MATCH  corr < 0.2 with a mouth that moves (activity > 0.6 of speaking-level) -> mismatch
  OFF       no face, face < 60 px wide, or no mouth movement -> treated as off-screen / not lip-readable
"""
import argparse, json, os, subprocess, sys
import numpy as np, cv2, mediapipe as mp

ROOT = "."                                       # story folder, set from --story in main()
SR = 16000
# lip gap peaks after loudness even when sync looks right: the sync.so reference measured +4 f at 24 fps
# (= +5 f at 30 fps), so the accepted band is that offset +-3 frames at 30 fps.
LAG_LO, LAG_HI = 2, 8


def voice_env(c, t0, n, fps):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(ROOT, c["media_url"]), "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)[int(c["source_in_ms"] / 1000 * SR): int(c["source_out_ms"] / 1000 * SR)]
    off = c["timeline_start_ms"] / 1000 - t0
    e = np.zeros(n)
    for i in range(n):
        a = int((i / fps - off) * SR); b = int(((i + 1) / fps - off) * SR)
        if b > 0 and a < len(x): e[i] = np.sqrt((x[max(a, 0):min(b, len(x))] ** 2).mean() + 1e-12)
    return e


def frames(video, t0, t1):
    cap = cv2.VideoCapture(video); fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000); F = []
    while cap.get(cv2.CAP_PROP_POS_MSEC) < t1 * 1000:
        ok, f = cap.read()
        if not ok: break
        F.append(f)
    return F, fps


def face_tracks(F):
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=3, min_detection_confidence=.3)
    tracks = []   # each: {"c": last centre, "gap": [..], "w": []}
    for k, f in enumerate(F):
        h, w = f.shape[:2]
        r = fm.process(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        dets = []
        for lm in (r.multi_face_landmarks or []):
            P = np.array([[q.x * w, q.y * h] for q in lm.landmark])
            fh = np.linalg.norm(P[10] - P[152]) + 1e-6
            dets.append((P[1], np.linalg.norm(P[13] - P[14]) / fh, np.linalg.norm(P[234] - P[454])))
        for c, g, fw in dets:
            best = min(tracks, key=lambda t: np.linalg.norm(t["c"] - c), default=None)
            if best is None or np.linalg.norm(best["c"] - c) > 0.15 * w:
                best = {"c": c, "gap": np.full(len(F), np.nan), "w": []}; tracks.append(best)
            best["c"] = c
            best["gap"][k] = g; best["w"].append(fw)
    return [t for t in tracks if np.isfinite(t["gap"]).sum() > 0.6 * len(F)]


def corr_lag(e, g, maxlag=12):
    best = (-1, 0)
    for L in range(-maxlag, maxlag + 1):
        a = e[max(0, -L): len(e) - max(0, L)]; b = g[max(0, L): len(g) - max(0, -L)]
        m = np.isfinite(b)
        if m.sum() < 8 or a[m].std() == 0 or b[m].std() == 0: continue
        r = np.corrcoef(a[m], b[m])[0, 1]
        if r > best[0]: best = (r, L)
    return best


def main():
    global ROOT
    ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("--lines", nargs="*"); ap.add_argument("--json")
    ap.add_argument("--story", required=True, help="story folder or its story.json")
    a = ap.parse_args()
    if os.path.isdir(a.story): a.story = os.path.join(a.story, "story.json")
    ROOT = os.path.dirname(os.path.abspath(a.story))
    story = json.load(open(a.story, encoding="utf8"))
    vo = sorted([c for c in story["timeline"]["clips"] if c["track_id"] == "tr_vo" and c.get("enabled", True)],
                key=lambda c: c["timeline_start_ms"])
    out = []
    for c in vo:
        if a.lines and c["id"] not in a.lines: continue
        s = c["timeline_start_ms"] / 1000; e = s + (c["source_out_ms"] - c["source_in_ms"]) / 1000
        t0, t1 = max(0, s - 0.4), e + 0.4
        F, fps = frames(os.path.join(ROOT, a.video), t0, t1)
        env = voice_env(c, t0, len(F), fps)
        speak = env > env.max() * 0.1
        res = {"id": c["id"], "start": round(s, 2), "end": round(e, 2), "verdict": "OFF"}
        best = None
        for t in face_tracks(F):
            g = t["gap"]; r, L = corr_lag(env, g)
            act_s = np.nanstd(g[speak]) if speak.any() else 0
            act_q = np.nanstd(g[~speak]) if (~speak).sum() > 3 else 0
            cand = dict(corr=round(float(r), 2), lag=int(L), width=int(np.median(t["w"])),
                        act_speak=round(float(act_s), 3), act_quiet=round(float(act_q), 3),
                        x=int(t["c"][0]))
            if best is None or cand["corr"] > best["corr"]: best = cand
        if best:
            res.update(best)
            moving = best["act_speak"] > 0.004
            if best["width"] < 60 or not moving: res["verdict"] = "OFF"
            elif best["corr"] >= 0.45: res["verdict"] = "OK" if LAG_LO <= best["lag"] <= LAG_HI else "LAG"
            elif best["corr"] >= 0.2: res["verdict"] = "WEAK"
            else: res["verdict"] = "NO-MATCH"
        out.append(res)
        print(f"{res['id']:<16} {s:7.2f}-{e:7.2f} {res['verdict']:<8} " +
              (f"corr {res['corr']:+.2f} lag {res['lag']:+d}f face {res['width']}px x={res['x']} "
               f"mouth sd speaking {res['act_speak']:.3f} / silent {res['act_quiet']:.3f}" if best else "no face"), flush=True)
    if a.json: json.dump(out, open(a.json, "w", encoding="utf8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
