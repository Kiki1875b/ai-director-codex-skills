"""Pre-check a keyframe BEFORE sending it to keyframe-reviewer (user decision 2026-11-10: "사전 점검 스크립트").
Measures the numeric items that kept failing reviews and that a region correction can fix, so review rounds are spent on
judgement (identity, expression, look, usability), not on numbers.

Thresholds come from stories/<slug>/precheck.json (written from RULES.md), section "default" merged with the section
named by --look (e.g. "lookA"). Boxes are x0,y0,x1,y1 in key pixels.

  python precheck_key.py stories/<slug> media/keys/K1.png [K2.png ...] --look lookA \
      --face-box 220,380,640,860 --hair-box 60,150,760,1350 [--json out.json]

Checks (each prints value, limit, OK/FAIL):
  black_p2        2nd percentile of grey                      <= black_p2_max
  shadow_q25      mean of the darkest 25% of grey             <= shadow_q25_max
  glow_p99        99th pct brightness of glow-hue pixels      in glow_p99 range
  glow_sat_top10  mean sat of the 10% most saturated glow px  in glow_sat range
  warm_px         count of warm saturated pixels (hue 0-25 / 165-180 deg OpenCV, sat>90, val>60) <= warm_px_max
  face_mean       grey mean inside --face-box                  in face_mean range
  chin_forehead   lower-third / upper-third grey of the face box >= chin_forehead_min   (light from below)
  hair_sat        mean sat of bright pixels in --hair-box outside the face box <= hair_sat_max
Exit code 1 if any check fails. Frame mean is printed for reference only (a close-up is naturally brighter than a wide)."""
import argparse, json, os, sys
import cv2, numpy as np

DEFAULT = {"black_p2_max": 4, "shadow_q25_max": 10.6, "glow_hue": [115, 165], "glow_p99": [153, 207], "glow_sat": [113, 144],
           "warm_px_max": 400, "face_mean": [70, 90], "chin_forehead_min": 1.3, "hair_sat_max": 80}


def box(s):
    return tuple(int(v) for v in s.split(",")) if s else None


def check(path, th, face_box, hair_box):
    img = cv2.imread(path)
    if img is None:
        return {"file": path, "error": "cannot read"}
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0].astype(np.int32), hsv[..., 1].astype(np.float32), hsv[..., 2].astype(np.float32)
    r = {"file": path, "frame_mean_ref_only": round(float(g.mean()), 1)}
    res = []

    def add(name, val, lim, ok):
        r[name] = round(float(val), 2) if val is not None else None
        res.append((name, r[name], lim, ok))

    p2 = np.percentile(g, 2); add("black_p2", p2, f"<= {th['black_p2_max']}", p2 <= th["black_p2_max"])
    q = np.sort(g.ravel()); q25 = q[: len(q) // 4].mean(); add("shadow_q25", q25, f"<= {th['shadow_q25_max']}", q25 <= th["shadow_q25_max"])
    lo, hi = th["glow_hue"]
    gm = (H >= lo) & (H <= hi) & (S > 60) & (V > 50)
    if gm.sum() > 200:
        gp = np.percentile(V[gm], 99); add("glow_p99", gp, th["glow_p99"], th["glow_p99"][0] <= gp <= th["glow_p99"][1])
        ss = np.sort(S[gm]); st = ss[int(len(ss) * 0.9):].mean(); add("glow_sat_top10", st, th["glow_sat"], th["glow_sat"][0] <= st <= th["glow_sat"][1])
    else:
        add("glow_p99", None, th["glow_p99"], False)
    warm = (((H <= 12) | (H >= 165)) & (S > 90) & (V > 60)) | ((H > 12) & (H <= 25) & (S > 90) & (V > 60))
    if face_box:   # skin is warm by nature: ignore the face box
        x0, y0, x1, y1 = face_box; warm[y0:y1, x0:x1] = False
    add("warm_px", int(warm.sum()), f"<= {th['warm_px_max']}", warm.sum() <= th["warm_px_max"])
    if face_box:
        x0, y0, x1, y1 = face_box; f = g[y0:y1, x0:x1]
        fm = f.mean(); add("face_mean", fm, th["face_mean"], th["face_mean"][0] <= fm <= th["face_mean"][1])
        t = f.shape[0] // 3; cf = f[2 * t:].mean() / max(f[:t].mean(), 1)
        add("chin_forehead", cf, f">= {th['chin_forehead_min']}", cf >= th["chin_forehead_min"])
    if hair_box:
        x0, y0, x1, y1 = hair_box; m = np.zeros_like(g, bool); m[y0:y1, x0:x1] = True
        if face_box:
            a0, b0, a1, b1 = face_box; m[b0:b1, a0:a1] = False
        m &= V > 90
        hs = S[m].mean() if m.sum() else 0; add("hair_sat", hs, f"<= {th['hair_sat_max']}", hs <= th["hair_sat_max"])
    r["checks"] = [{"name": n, "value": v, "limit": l, "ok": bool(o)} for n, v, l, o in res]
    r["pass"] = all(o for *_, o in res)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story_dir"); ap.add_argument("keys", nargs="+")
    ap.add_argument("--look"); ap.add_argument("--face-box"); ap.add_argument("--hair-box"); ap.add_argument("--json")
    a = ap.parse_args()
    th = dict(DEFAULT)
    pj = os.path.join(a.story_dir, "precheck.json")
    if os.path.exists(pj):
        cfg = json.load(open(pj, encoding="utf-8"))
        th.update(cfg.get("default", {}))
        if a.look: th.update(cfg.get(a.look, {}))
    out = []
    for k in a.keys:
        p = k if os.path.isabs(k) or os.path.exists(k) else os.path.join(a.story_dir, k)
        r = check(p, th, box(a.face_box), box(a.hair_box)); out.append(r)
        print(f"== {os.path.basename(p)}  {'PASS' if r.get('pass') else 'FAIL'}  (frame mean {r.get('frame_mean_ref_only')}, reference only)")
        for c in r.get("checks", []):
            print(f"   {'OK  ' if c['ok'] else 'FAIL'} {c['name']:<15} {c['value']}  limit {c['limit']}")
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.exit(0 if all(r.get("pass") for r in out) else 1)


if __name__ == "__main__":
    main()
