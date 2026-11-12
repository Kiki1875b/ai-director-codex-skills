"""Collect evidence for reviewing one finished SCENE (not a cut) from the timeline.

Outputs into --out:
  cuts.md          cut list in timeline order (shot, version, review status, start/end, length, transition, beat,
                   dialogue), shot-length stats, disabled clips, scene shots missing from the cut, entry/exit edit
                   points, audio clips overlapping the scene (J/L-cut evidence), loudness per cut and at edit points
  scene_sheet.jpg  one row per cut: 5 frames across the used range, from the SOURCE clips
  render_sheet.jpg (with --render) the same timeline times taken from the RENDER (grading, dissolves visible)
  boundaries.jpg   every edit point incl. entering (previous scene → first cut) and leaving (last cut → next scene)
  loudness.png     (with --render) loudness of the scene ±1 s, dB grid, cut lines
  evidence.json    the same numbers for the reviewer

The rendered video track follows render_timeline.py (first visible video track by order).
Times are timeline seconds (speed applied).

usage: python scene_evidence.py stories/<slug>/story.json <scene_id> --out <dir> [--render <full-timeline mp4>]
"""
import argparse, json, statistics, subprocess, sys
from pathlib import Path

import cv2
import numpy as np

PAD = 1.0  # seconds of context before/after the scene in loudness


def main_video_track_id(doc):
    tracks = doc.get("timeline", {}).get("tracks", [])
    vt = sorted((t for t in tracks if t.get("type") == "video" and not t.get("hidden")), key=lambda t: str(t.get("order", "")))
    return vt[0]["id"] if vt else None


def clip_len_ms(c):
    if "duration_ms" in c and "source_out_ms" not in c:
        return c["duration_ms"]
    return (c["source_out_ms"] - c.get("source_in_ms", 0)) / c.get("speed", 1)


def grab(path, t_ms, kind="video"):
    if kind == "image":
        return cv2.imread(str(path))
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t_ms))
    ok, f = cap.read()
    cap.release()
    return f if ok else None


def thumb(f, w=320, label=""):
    if f is None:
        f = np.zeros((180, 320, 3), np.uint8)
    h = int(w * f.shape[0] / f.shape[1])
    s = cv2.resize(f, (w, h))
    if label:
        cv2.rectangle(s, (0, 0), (w, 22), (0, 0, 0), -1)
        cv2.putText(s, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return s


def stack(rows):
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0))) for r in rows]
    return np.vstack(rows)


def shot_scene(doc):
    return {sh["id"]: sc["id"] for sc in doc["scenes"] for sh in sc["shots"]}


def src_time(c, tl_ms):
    """source ms in clip c for timeline ms"""
    return c.get("source_in_ms", 0) + (tl_ms - c["timeline_start_ms"]) * c.get("speed", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story"); ap.add_argument("scene"); ap.add_argument("--out", required=True)
    ap.add_argument("--render", help="mp4 rendered from the same timeline (render_timeline.py --preview) for loudness and graded frames")
    a = ap.parse_args()
    sp = Path(a.story); base = sp.parent
    doc = json.load(open(sp, encoding="utf-8"))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    scene = next((s for s in doc["scenes"] if s["id"] == a.scene), None)
    if not scene:
        sys.exit(f"scene {a.scene} not found")
    shots = {s["id"]: s for s in scene["shots"]}
    sc_of = shot_scene(doc)
    beats = (scene.get("direction") or {}).get("beats") or []
    beat_of = {sid: i + 1 for i, b in enumerate(beats) for sid in b.get("shot_ids", [])}
    main = main_video_track_id(doc)
    track_all = sorted([c for c in doc["timeline"]["clips"] if c.get("track_id") == main], key=lambda c: c["timeline_start_ms"])
    on = [c for c in track_all if c.get("enabled", True)]
    clips = [c for c in on if c.get("shot_id") in shots]
    if not clips:
        sys.exit(f"no enabled clips of {a.scene} on the rendered track {main}")
    t0 = clips[0]["timeline_start_ms"]; t1 = max(c["timeline_start_ms"] + clip_len_ms(c) for c in clips)
    i_first, i_last = on.index(clips[0]), on.index(clips[-1])
    prev_c = on[i_first - 1] if i_first > 0 else None
    next_c = on[i_last + 1] if i_last + 1 < len(on) else None
    foreign = [c for c in on[i_first:i_last + 1] if c.get("shot_id") not in shots]
    disabled = [c for c in track_all if not c.get("enabled", True) and c.get("shot_id") in shots]
    used = {c["shot_id"] for c in clips}
    missing = [sid for sid in shots if sid not in used and not any(c.get("shot_id") == sid for c in disabled)]

    md, notes = [], []
    md.append(f"# Scene {a.scene} evidence — {scene.get('title', '')}\n")
    d = scene.get("direction") or {}
    md.append(f"- timeline {t0/1000:.2f}–{t1/1000:.2f} s ({(t1-t0)/1000:.2f} s), track {main}, {len(clips)} cuts")
    md.append(f"- viewpoint: {d.get('viewpoint', '입력 없음')}")
    md.append(f"- dramatic_turn: {d.get('dramatic_turn', '입력 없음')}")
    for i, b in enumerate(beats, 1):
        md.append(f"- beat {i}: {b.get('action', '')} → 관객: {b.get('audience_learns', '')} ({', '.join(b.get('shot_ids', []))})")
    if disabled:
        notes.append("꺼진 클립(enabled:false, 사용자 결정일 수 있음): " + ", ".join(f"{c['id']}({c['shot_id']})" for c in disabled))
    if missing:
        notes.append("타임라인 렌더 트랙에 없는 이 씬의 샷(다른 씬 클립 안에 들어갔거나 빠짐 — 씬 범위가 실제와 다를 수 있음): " + ", ".join(missing))
    if foreign:
        notes.append("씬 범위 안의 다른 씬 클립: " + ", ".join(f"{c['id']}({c.get('shot_id')})" for c in foreign))
    if next_c and next_c.get("transition_in"):
        tr = next_c["transition_in"]
        notes.append(f"다음 클립 {next_c['id']}의 {tr.get('type')} {tr.get('duration_ms', 500)}ms가 씬 끝과 겹침")
    if clips[0].get("transition_in"):
        tr = clips[0]["transition_in"]
        notes.append(f"씬 첫 클립이 {tr.get('type')} {tr.get('duration_ms', 500)}ms로 들어옴")
    md += [f"- **주의**: {n}" for n in notes]

    gaps, lens, rows, ev_cuts = [], [], [], []
    md.append("\n| # | clip | shot | version | review | start s | len s | transition | beat | dialogue |\n|---|---|---|---|---|---|---|---|---|---|")
    prev_end = None
    for i, c in enumerate(clips, 1):
        sh = shots[c["shot_id"]]
        ver = next((v for v in sh.get("versions", []) if v["id"] == c.get("version_id")), {})
        rv = (ver.get("review") or {}).get("status", "없음(story.json)")
        L = clip_len_ms(c); lens.append(L / 1000)
        st = c["timeline_start_ms"]
        if prev_end is not None and abs(st - prev_end) > 1:
            gaps.append({"before": c["id"], "gap_ms": round(st - prev_end)})
        prev_end = st + L
        tr = c.get("transition_in") or {}
        dia = " / ".join(x.get("text", "") for x in sh.get("dialogue", []) if x.get("text"))
        md.append(f"| {i} | {c['id']} | {c['shot_id']} | {c.get('version_id','')} | {rv} | {st/1000:.2f} | {L/1000:.2f} | "
                  f"{tr.get('type','cut')}{'' if not tr else ' ' + str(tr.get('duration_ms',''))} | {beat_of.get(c['shot_id'], '-')} | {dia} |")
        ev_cuts.append({"clip": c["id"], "shot": c["shot_id"], "version": c.get("version_id"), "review": rv,
                        "start_s": st / 1000, "len_s": L / 1000, "transition": tr or None, "beat": beat_of.get(c["shot_id"])})
        path = base / c["media_url"]; kind = c.get("media_kind", "video")
        rows.append(np.hstack([thumb(grab(path, src_time(c, st + L * k / 4 - (40 if k == 4 else 0)), kind), 256,
                                     f"{c['shot_id']} t={(st + L * k / 4)/1000:.2f}s") for k in range(5)]))
    cv2.imwrite(str(out / "scene_sheet.jpg"), stack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])

    # edit points incl. entering and leaving the scene
    pairs = ([(prev_c, clips[0])] if prev_c else []) + list(zip(clips, clips[1:])) + ([(clips[-1], next_c)] if next_c else [])
    b_rows = []
    for A, B in pairs:
        fa = grab(base / A["media_url"], A["source_out_ms"] - 40, A.get("media_kind", "video"))
        fb = grab(base / B["media_url"], B.get("source_in_ms", 0), B.get("media_kind", "video"))
        tr = (B.get("transition_in") or {}).get("type", "cut")
        tag = " [씬 진입]" if A is prev_c else (" [씬 퇴장]" if B is next_c else "")
        b_rows.append(np.hstack([thumb(fa, 384, f"END {A.get('shot_id', A['id'])}{tag}"),
                                 thumb(fb, 384, f"START {B.get('shot_id', B['id'])} ({tr})")]))
    cv2.imwrite(str(out / "boundaries.jpg"), stack(b_rows), [cv2.IMWRITE_JPEG_QUALITY, 82])

    md.append(f"\n- shot length s: {[round(x, 2) for x in lens]}")
    md.append(f"- mean {statistics.mean(lens):.2f}, median {statistics.median(lens):.2f}, min {min(lens):.2f}, max {max(lens):.2f}")
    untrimmed = [c["shot_id"] for c in clips if c.get("source_in_ms", 0) == 0 and abs(c["source_out_ms"] - (shots[c["shot_id"]].get("duration_ms") or -1)) < 100]
    if untrimmed:
        md.append(f"- 생성 길이 그대로(트림 안 함)로 보이는 컷: {untrimmed} — 결함이 아니라 E2에서 길이를 의도했는지 확인할 대상")
    if gaps:
        md.append(f"- **gaps/overlaps on the video track**: {gaps}")

    tracks = {t["id"]: t for t in doc["timeline"]["tracks"]}
    au = []
    for c in doc["timeline"]["clips"]:
        t = tracks.get(c.get("track_id"), {})
        if t.get("type") != "audio" or not c.get("enabled", True):
            continue
        s = c["timeline_start_ms"]; e = s + clip_len_ms(c)
        if e > t0 and s < t1:
            au.append({"clip": c["id"], "track": t["id"], "subtype": t.get("subtype"), "start_s": s / 1000, "end_s": e / 1000,
                       "starts_before_scene": s < t0, "ends_after_scene": e > t1, "media": c.get("media_url")})
    md.append("\n## audio clips on timeline tracks in scene range\n")
    md += [f"- {x['track']}/{x['clip']} {x['start_s']:.2f}–{x['end_s']:.2f}s {'(starts before scene)' if x['starts_before_scene'] else ''}"
           f"{'(runs past scene)' if x['ends_after_scene'] else ''} {x['media']}" for x in au] or \
          ["- 타임라인 오디오 트랙에는 없음. 렌더 소리가 타임라인 밖의 믹스(효과음 큐 파일 등)에서 왔을 수 있으니 호출자가 확인한다"]

    loud = None
    if a.render:
        # graded frames from the render at the same timeline times
        cap_rows = []
        for c, L in zip(clips, lens):
            st = c["timeline_start_ms"]
            cap_rows.append(np.hstack([thumb(grab(a.render, st + L * 1000 * k / 4 - (60 if k == 4 else 0)), 256,
                                             f"R {c['shot_id']} t={(st + L * 1000 * k / 4)/1000:.2f}s") for k in range(5)]))
        cv2.imwrite(str(out / "render_sheet.jpg"), stack(cap_rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
        s0 = max(0.0, t0 / 1000 - PAD); dur = (t1 / 1000 + PAD) - s0
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{s0:.3f}", "-t", f"{dur:.3f}", "-i", a.render,
               "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]
        pcm = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.int16).astype(np.float32) / 32768
        if len(pcm):
            win = 800  # 0.1 s
            n = len(pcm) // win
            db = 20 * np.log10(np.sqrt((pcm[:n * win].reshape(n, win) ** 2).mean(1)) + 1e-9)
            tt = s0 + np.arange(n) / 10  # timeline seconds
            def mean_db(x0, x1):
                m = (tt >= x0) & (tt < x1)
                return round(float(10 * np.log10(np.mean(10 ** (db[m] / 10)) + 1e-12)), 1) if m.any() else None
            per_cut = []
            for c, L in zip(clips, lens):
                st = c["timeline_start_ms"] / 1000
                per_cut.append({"shot": c["shot_id"], "mean_db": mean_db(st, st + L)})
            edges = []
            for A, B in pairs:
                te = B["timeline_start_ms"] / 1000
                edges.append({"edit": f"{A.get('shot_id', A['id'])}→{B.get('shot_id', B['id'])}", "t": round(te, 2),
                              "before_db": mean_db(te - 0.5, te), "after_db": mean_db(te, te + 0.5)})
            sil, i = [], 0
            low = db < -50
            while i < n:
                if low[i]:
                    j = i
                    while j + 1 < n and low[j + 1]: j += 1
                    if (j - i + 1) >= 5: sil.append([round(float(tt[i]), 1), round(float(tt[j]) + 0.1, 1)])
                    i = j + 1
                else:
                    i += 1
            H, W, M = 240, 1000, 40
            img = np.full((H, W, 3), 255, np.uint8)
            X = lambda t: int(M + (t - s0) / dur * (W - M - 5))
            Y = lambda v: int(10 + (1 - np.clip((v + 70) / 70, 0, 1)) * (H - 40))
            for v in (-60, -40, -20, 0):
                cv2.line(img, (M, Y(v)), (W, Y(v)), (225, 225, 225), 1); cv2.putText(img, str(v), (2, Y(v) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (90, 90, 90), 1)
            for k in range(1, n): cv2.line(img, (X(tt[k-1]), Y(db[k-1])), (X(tt[k]), Y(db[k])), (60, 60, 200), 1)
            for A, B in pairs:
                te = B["timeline_start_ms"] / 1000
                col = (0, 140, 255) if (A is prev_c or B is next_c) else (0, 160, 0)
                cv2.line(img, (X(te), 0), (X(te), H - 25), col, 1)
            for t in np.arange(np.ceil(s0), s0 + dur, 1.0):
                cv2.putText(img, f"{t:.0f}", (X(t) - 8, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (90, 90, 90), 1)
            cv2.putText(img, "dBFS / timeline s; green = cuts, orange = scene in/out", (M, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
            cv2.imwrite(str(out / "loudness.png"), img)
            loud = {"per_cut": per_cut, "edit_points": edges, "silence_runs_timeline_s": sil}
            md.append(f"\n## loudness (render, timeline s, scene ±{PAD:.0f}s)")
            md += [f"- {p['shot']}: mean {p['mean_db']} dBFS" for p in per_cut]
            md += [f"- edit {e['edit']} @{e['t']}s: {e['before_db']} → {e['after_db']} dBFS (0.5 s each side)" for e in edges]
            md.append(f"- silence ≥0.5 s (< -50 dBFS): {sil or '없음'}")
            md.append(f"- render: {a.render} — 현재 타임라인에서 렌더한 파일인지 호출자가 확인한다. 소리 갈래(발소리/음악)는 이 수치로 나눌 수 없다")
        else:
            md.append(f"\n## loudness\n- **렌더에서 소리를 읽지 못함** (렌더가 짧거나 소리 없음): {a.render}")
    else:
        md.append("\n## loudness\n- --render 없음: 소리 항목은 렌더 후 또는 사용자 시청으로 확인")

    (out / "cuts.md").write_text("\n".join(md), encoding="utf-8")
    json.dump({"scene": a.scene, "range_s": [t0 / 1000, t1 / 1000], "notes": notes, "cuts": ev_cuts, "gaps": gaps,
               "audio": au, "shot_len_s": lens, "loudness": loud}, open(out / "evidence.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(out / "cuts.md")


if __name__ == "__main__":
    main()
