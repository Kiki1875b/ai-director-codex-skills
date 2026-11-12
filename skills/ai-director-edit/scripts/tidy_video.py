"""Tidy stories/<slug>/media/video: one deliverable per generation stays on top, everything else moves.

  media/video/            final clip of each generation: graded 24 fps (<stem>_graded_24fps.mp4, or <stem>_graded.mp4
                          when it was already 24 fps from RIFE)
  media/video/_src/       camera originals, 16 fps grades, workflow json, masks, one-take segments
  media/video/_rejected/  every file of a version whose status is "failed" or "superseded" in story.json

Nothing is deleted. story.json media_url / graded_url are rewritten to the new paths. Safe to re-run.
  python tidy_video.py stories/<slug>
"""
import json
import os
import re
import shutil
import subprocess
import sys

root = sys.argv[1]
vd = os.path.join(root, "media", "video")
sp = os.path.join(root, "story.json")
story = json.load(open(sp, encoding="utf-8"))
SUF = ("_graded_24fps.mp4", "_graded.mp4", "_24fps.mp4", "_workflow.json", "_mask.png", ".mp4")


def stem(f):
    for s in SUF:
        if f.endswith(s):
            return f[: -len(s)]
    return os.path.splitext(f)[0]


def fps(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    n, _, d = r.partition("/")
    return float(n) / float(d or 1) if n else 0


versions = [v for sc in story["scenes"] for sh in sc["shots"] for v in sh.get("versions", [])]
failed = {os.path.basename(v["media_url"]).replace(".mp4", "") for v in versions
          if v.get("kind") == "video" and v.get("status") in ("failed", "superseded") and v.get("media_url")}
failed |= {stem(os.path.basename(v["media_url"])) for v in versions
           if v.get("kind") == "video" and v.get("status") in ("failed", "superseded") and v.get("media_url")}
segments = re.compile(r"-seg[A-Z]-v\d+$")

files = [f for f in os.listdir(vd) if os.path.isfile(os.path.join(vd, f))]
groups = {}
for f in files:
    groups.setdefault(stem(f), []).append(f)

moved = {}
for st, fs in groups.items():
    if st in failed:
        keep, dest = None, "_rejected"
    else:
        dest = "_src"
        if st + "_graded_24fps.mp4" in fs:
            keep = st + "_graded_24fps.mp4"
        elif st + "_graded.mp4" in fs and fps(os.path.join(vd, st + "_graded.mp4")) >= 23.9:
            keep = st + "_graded.mp4"
        elif st + "_graded.mp4" not in fs and st + ".mp4" in fs and fps(os.path.join(vd, st + ".mp4")) >= 23.9:
            keep = st + ".mp4"  # LOG/LUT step skipped: the 24 fps camera original is the deliverable
        else:
            keep = None  # no 24 fps clip yet: leave the group as it is
            continue
        if segments.search(st):
            keep = None  # pieces of a one-take: the joined clip is the deliverable
    for f in fs:
        if f == keep:
            continue
        os.makedirs(os.path.join(vd, dest), exist_ok=True)
        shutil.move(os.path.join(vd, f), os.path.join(vd, dest, f))
        moved[f"media/video/{f}"] = f"media/video/{dest}/{f}"

for v in versions:
    for k in ("media_url", "graded_url"):
        if v.get(k) in moved:
            v[k] = moved[v[k]]
json.dump(story, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"moved {len(moved)} files")
for a, b in moved.items():
    print(f"  {a} -> {b}")
