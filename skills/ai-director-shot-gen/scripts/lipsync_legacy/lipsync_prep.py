"""Cut a shot's used range and build its dialogue track on the shot timeline (for latentsync_run.py).

  python lipsync_prep.py --story stories/<slug> S2-3 S6-3 ...
      -> <story>/media/video/_lipsync/in/<shot>_video.mp4, <shot>_voice.wav
Voice = every tr_vo clip that overlaps the shot, placed at its offset, its own source in/out, padded with
silence to the shot length (no music/effects)."""
import argparse, json, os, subprocess, sys
import numpy as np
ROOT = OUT = None; SR = 48000                    # ROOT = story folder, set from --story


def main(ids):
    s = json.load(open(os.path.join(ROOT, "story.json"), encoding="utf8")); clips = s["timeline"]["clips"]
    shots = {c["shot_id"]: c for c in clips if c["track_id"] == "tr_v1"}
    vo = [c for c in clips if c["track_id"] == "tr_vo" and c.get("enabled", True)]
    os.makedirs(OUT, exist_ok=True)
    for sid in ids:
        c = shots[sid]; t0 = c["timeline_start_ms"]; dur = c["source_out_ms"] - c["source_in_ms"]
        v = os.path.join(OUT, f"{sid}_video.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['source_in_ms'] / 1000:.3f}", "-i", os.path.join(ROOT, c["media_url"]),
                        "-t", f"{dur / 1000:.3f}", "-an", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", v], check=True)
        track = np.zeros(int(dur / 1000 * SR) + 1, np.float32); used = []
        for l in vo:
            off = l["timeline_start_ms"] - t0
            ln = l["source_out_ms"] - l["source_in_ms"]
            if off >= dur or off + ln <= 0: continue   # any overlap with the shot (a line may start in the silence before it)
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{l['source_in_ms'] / 1000:.3f}", "-i", os.path.join(ROOT, l["media_url"]),
                                  "-t", f"{(l['source_out_ms'] - l['source_in_ms']) / 1000:.3f}", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                                 capture_output=True, check=True).stdout
            x = np.frombuffer(raw, np.float32) * l.get("volume", 1)
            a = int(off / 1000 * SR); b = min(len(track), a + len(x))
            if a < 0: x = x[-a:]; a = 0
            track[a:b] += x[:b - a]; used.append(f"{l['id']}@{off / 1000:+.2f}s{'(cut)' if a + len(x) > len(track) else ''}")
        w = os.path.join(OUT, f"{sid}_voice.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", w],
                       input=np.clip(track, -1, 1).tobytes(), check=True)
        n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames",
                            "-of", "csv=p=0", v], capture_output=True, text=True).stdout.strip()
        print(f"{sid}: {dur / 1000:.2f}s, {n} frames, lines {used}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Cut shots and build their dialogue tracks for lip-sync.")
    ap.add_argument("--story", required=True, help="story folder (holds story.json)")
    ap.add_argument("shots", nargs="+")
    a = ap.parse_args()
    ROOT = a.story; OUT = os.path.join(ROOT, "media", "video", "_lipsync", "in")
    main(a.shots)
