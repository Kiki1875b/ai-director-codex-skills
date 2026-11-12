"""Align dialogue clips to the on-screen mouth: measure when the speaker's mouth starts opening in each shot
(MediaPipe face mesh, inner-lip gap / face height) and when the voice starts in the audio file, then move the
dialogue clip so the two coincide.

  python mouth_sync.py --story stories/<slug> [--line cl_vo_S4-2_1=S4-2:left ...] [--fps 24]   # report only
  python mouth_sync.py --story stories/<slug> ... --apply    # write new timeline_start_ms to story.json (backup first)

--line CLIP=SHOT[:PICK]: dialogue clip -> the shot whose mouth it follows and which face speaks. PICK = left / right /
largest (default largest; two-shots need left/right). Without --line, every enabled tr_vo clip named
cl_vo_<shot>_<n> is matched to <shot> with "largest".
"""
import argparse, json, os, re, shutil, subprocess, sys, datetime
import numpy as np
import mediapipe as mp

FPS = 24                                         # set from --fps in main()


def frames(path, t0, dur):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", path, "-vf", "scale=960:540",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 540, 960, 3)


def mouth_curve(F, pick):
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=2, refine_landmarks=False,
                                         min_detection_confidence=0.3, min_tracking_confidence=0.3)
    out = []
    for f in F:
        r = fm.process(f)
        if not r.multi_face_landmarks:
            out.append(np.nan); continue
        faces = []
        for lm in r.multi_face_landmarks:
            p = np.array([[q.x, q.y] for q in lm.landmark])
            h = np.linalg.norm(p[10] - p[152]) + 1e-6            # forehead-chin
            gap = np.linalg.norm(p[13] - p[14]) / h             # inner lips
            faces.append((p[:, 0].mean(), h, gap))
        if pick == "left": face = min(faces, key=lambda z: z[0])
        elif pick == "right": face = max(faces, key=lambda z: z[0])
        else: face = max(faces, key=lambda z: z[1])
        out.append(face[2])
    fm.close()
    return np.array(out)


def voice_onset(path, thresh_db=-35):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    x = np.abs(np.frombuffer(raw, np.float32)); hop = 160
    env = np.array([x[i:i + hop].max(initial=0) for i in range(0, len(x), hop)])
    db = 20 * np.log10(env / (env.max() + 1e-9) + 1e-9)
    i = int(np.argmax(db > thresh_db)); return i * hop / 16000


def mouth_onset(c):
    """First frame where the inner-lip gap rises clearly above its closed level and stays open for 3 frames."""
    v = c.copy(); ok = ~np.isnan(v)
    if ok.sum() < 5: return None, None
    v[~ok] = np.nanmin(v)
    base = np.percentile(v[ok], 15); peak = np.percentile(v[ok], 95)
    thr = base + 0.35 * (peak - base)
    for i in range(len(v) - 3):
        if (v[i:i + 3] > thr).all():
            return i / FPS, (base, peak)
    return None, (base, peak)


def main():
    global FPS
    ap = argparse.ArgumentParser(description="Move dialogue clips so the voice starts when the mouth opens.")
    ap.add_argument("--story", required=True, help="story folder or its story.json")
    ap.add_argument("--line", action="append", default=[], metavar="CLIP=SHOT[:PICK]")
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--apply", action="store_true", help="write the new start times to story.json (backup first)")
    a = ap.parse_args()
    FPS = a.fps
    STORY = os.path.join(a.story, "story.json") if os.path.isdir(a.story) else a.story
    ROOT = os.path.dirname(os.path.abspath(STORY))
    s = json.load(open(STORY, encoding="utf8"))
    clips = s["timeline"]["clips"]
    shots = {c["shot_id"]: c for c in clips if c["track_id"] == "tr_v1"}
    vo = {c["id"]: c for c in clips if c["track_id"] == "tr_vo"}
    lines = {}                                   # dialogue clip -> (shot, which face speaks)
    for spec in a.line:
        cid, rest = spec.split("=", 1)
        shot, _, pick = rest.partition(":")
        lines[cid] = (shot, pick or "largest")
    if not a.line:
        for cid, c in vo.items():
            m = re.match(r"cl_vo_(.+)_\d+$", cid)
            if m and c.get("enabled", True) and m.group(1) in shots:
                lines[cid] = (m.group(1), "largest")
    changes = {}
    for cid, (shot, pick) in lines.items():
        sc, v = shots[shot], vo[cid]
        shot_start = sc["timeline_start_ms"] / 1000; shot_dur = (sc["source_out_ms"] - sc["source_in_ms"]) / 1000
        F = frames(os.path.join(ROOT, sc["media_url"]), sc["source_in_ms"] / 1000, shot_dur)
        curve = mouth_curve(F, pick)
        mo, lv = mouth_onset(curve)
        vo_on = voice_onset(os.path.join(ROOT, v["media_url"]))
        cur_voice = v["timeline_start_ms"] / 1000 + vo_on
        detected = np.mean(~np.isnan(curve))
        if mo is None:
            print(f"{cid}: no clear mouth opening (face found in {detected:.0%} of frames) - unchanged"); continue
        target_voice = shot_start + mo
        new_start = target_voice - vo_on
        print(f"{cid}: mouth opens {mo:.2f}s into {shot} (faces {detected:.0%}); voice now {cur_voice - shot_start:+.2f}s "
              f"-> move {new_start - v['timeline_start_ms'] / 1000:+.2f}s")
        changes[cid] = int(round(new_start * 1000))
    if a.apply and changes:
        shutil.copy(STORY, STORY + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        for cid, ms in changes.items():
            vo[cid]["timeline_start_ms"] = ms
        json.dump(s, open(STORY, "w", encoding="utf8"), ensure_ascii=False, indent=2)
        print("applied", len(changes))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
