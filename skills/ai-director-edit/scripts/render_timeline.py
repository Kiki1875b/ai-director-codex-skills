"""Render a Director story.json timeline to mp4/mov with ffmpeg.

Usage:
  python render_timeline.py story.json -o export/final.mp4 [--dry-run] [--preview]
                            [--font C:/Windows/Fonts/malgun.ttf] [--font-size 48]

Model (mirrors the OpenArt Director timeline schema):
  - main video = enabled clips on the video track with the lowest `order`
  - clip length = (source_out_ms - source_in_ms) / speed; images are held for that length
  - gaps before a clip become black; transition_in overlaps the previous clip (xfade)
  - audio = original audio of video clips (placed where the clip lands) + every audio track clip
    (placed at timeline_start_ms), mixed without normalization
  - text clips become drawtext captions
Requires ffmpeg and ffprobe on PATH.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

XFADE = {
    "dissolve": lambda d: "dissolve",
    "fade": lambda d: "fadeblack",
    "slide": lambda d: {"right": "slideright", "up": "slideup", "down": "slidedown"}.get(d, "slideleft"),
    "wipe": lambda d: {"right": "wiperight", "up": "wipeup", "down": "wipedown"}.get(d, "wipeleft"),
    "clock_wipe": lambda d: "radial",
    "iris": lambda d: "circleclose" if d == "in" else "circleopen",
    "zoom": lambda d: "zoomin",
}
DEFAULT_FONT = "C:/Windows/Fonts/malgun.ttf"


def ff_escape_path(p):
    """Escape a path for use inside a quoted filter option value."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "'\\''")


def resolve_media(url, base):
    if url.startswith(("http://", "https://")):
        return url
    p = Path(url)
    return str(p if p.is_absolute() else (base / p).resolve())


def has_audio(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60,
        ).stdout
        return bool(out.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def media_kind(c):
    kind = c.get("media_kind")
    if kind:
        return kind
    return "image" if Path(c["media_url"].split("?")[0]).suffix.lower() in IMAGE_EXT else "video"


def clip_len_s(c):
    return (c["source_out_ms"] - c.get("source_in_ms", 0)) / 1000 / c.get("speed", 1)


def build(doc, base, out_path, preview, font, font_size, tmpdir):
    exp = doc.get("export", {})
    fps = exp.get("fps", 30)
    width, height = exp.get("width", 1920), exp.get("height", 1080)
    sample_rate = exp.get("sample_rate", 48000)
    if preview:
        width, height = int(round(width * 540 / height / 2)) * 2, 540
        fps = min(fps, 24)

    tracks = {t["id"]: t for t in doc["timeline"]["tracks"]}
    clips = [c for c in doc["timeline"]["clips"] if c.get("enabled", True)]
    video_tracks = sorted((t for t in tracks.values() if t["type"] == "video" and not t.get("hidden")),
                          key=lambda t: str(t.get("order", "")))
    if not video_tracks:
        sys.exit("no visible video track")
    main_track = video_tracks[0]
    if len(video_tracks) > 1:
        print(f"WARN only the first video track ({main_track['id']}) is rendered", file=sys.stderr)

    inputs, filters, audio_labels = [], [], []

    def add_input(args):
        inputs.extend(args)
        return sum(1 for a in inputs if a == "-i") - 1

    vclips = sorted((c for c in clips if c["track_id"] == main_track["id"]), key=lambda c: c["timeline_start_ms"])
    if not vclips:
        sys.exit("main video track has no enabled clips")

    norm = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p,settb=AVTB")
    acc_label, acc_len, seg_no = None, 0.0, 0

    prev_len = 0.0

    def join(label, length, transition=None, overlap=0.0):
        nonlocal acc_label, acc_len, seg_no, prev_len
        start = acc_len
        if acc_label is None:
            acc_label, acc_len, prev_len = label, length, length
            return 0.0
        out = f"j{seg_no}"
        seg_no += 1
        if transition:
            d = min(overlap, prev_len, length) * 0.999
            kind = XFADE[transition["type"]](transition.get("direction"))
            filters.append(f"[{acc_label}][{label}]xfade=transition={kind}:duration={d:.3f}:offset={acc_len - d:.3f}[{out}]")
            start = acc_len - d
            acc_len = acc_len - d + length
        else:
            filters.append(f"[{acc_label}][{label}]concat=n=2:v=1:a=0[{out}]")
            acc_len += length
        acc_label, prev_len = out, length
        return start

    for i, c in enumerate(vclips):
        path = resolve_media(c["media_url"], base)
        si, so, speed = c.get("source_in_ms", 0) / 1000, c["source_out_ms"] / 1000, c.get("speed", 1)
        length = clip_len_s(c)
        kind = media_kind(c)
        # timeline_start_ms is authoritative: overlap with the previous clip = transition window
        offset = c["timeline_start_ms"] / 1000 - acc_len
        transition = c.get("transition_in") if acc_label is not None else None
        overlap = 0.0
        if transition:
            tdur = transition.get("duration_ms", 500) / 1000
            overlap = min(tdur, -offset) if offset < -0.04 else 0.0
            if overlap <= 0:
                print(f"WARN {c['id']}: transition_in ignored (clip does not overlap the previous clip; "
                      f"set timeline_start_ms = previous end - transition)", file=sys.stderr)
                transition = None
        elif offset < -0.04 and acc_label is not None:
            print(f"WARN {c['id']}: overlaps the previous clip by {-offset:.2f}s without a transition; "
                  f"placed right after it", file=sys.stderr)
        if offset > 0.04 and not transition:
            filters.append(f"color=c=black:s={width}x{height}:r={fps}:d={offset:.3f},format=yuv420p,setsar=1,settb=AVTB[gap{i}]")
            join(f"gap{i}", offset)
        if kind == "image":
            k = add_input(["-loop", "1", "-t", f"{length:.3f}", "-i", path])
            filters.append(f"[{k}:v]{norm},trim=duration={length:.3f},setpts=PTS-STARTPTS,settb=AVTB[v{i}]")
        else:
            k = add_input(["-i", path])
            filters.append(f"[{k}:v]trim=start={si:.3f}:end={so:.3f},setpts=(PTS-STARTPTS)/{speed},{norm}[v{i}]")
        start = join(f"v{i}", length, transition, overlap)
        vol = c.get("volume", 1) * main_track.get("volume", 1)
        if kind != "image" and not c.get("muted") and not main_track.get("muted") and vol > 0 and has_audio(path):
            ms = int(round(start * 1000))
            filters.append(f"[{k}:a]atrim=start={si:.3f}:end={so:.3f},asetpts=PTS-STARTPTS,atempo={speed},"
                           f"volume={vol},aresample={sample_rate},adelay=delays={ms}:all=1[a{i}]")
            audio_labels.append(f"a{i}")

    total = acc_len

    for j, c in enumerate(c for c in clips if tracks[c["track_id"]]["type"] == "audio"):
        t = tracks[c["track_id"]]
        vol = c.get("volume", 1) * t.get("volume", 1)
        if t.get("muted") or t.get("hidden") or c.get("muted") or vol <= 0:
            continue
        path = resolve_media(c["media_url"], base)
        if not has_audio(path):
            print(f"WARN {c['id']}: no audio stream in {path}; skipped", file=sys.stderr)
            continue
        k = add_input(["-i", path])
        si, so, speed = c.get("source_in_ms", 0) / 1000, c["source_out_ms"] / 1000, c.get("speed", 1)
        filters.append(f"[{k}:a]atrim=start={si:.3f}:end={so:.3f},asetpts=PTS-STARTPTS,atempo={speed},"
                       f"volume={vol},aresample={sample_rate},adelay=delays={int(c['timeline_start_ms'])}:all=1[t{j}]")
        audio_labels.append(f"t{j}")

    vout = acc_label
    texts = [c for c in clips if c.get("kind") == "text" and not tracks[c["track_id"]].get("hidden")]
    if texts:
        if not Path(font).exists():
            sys.exit(f"font not found: {font} (pass --font)")
        fs = font_size if not preview else max(16, int(font_size * 540 / (doc.get("export", {}).get("height", 1080))))
        ypos = {"top": "h*0.08", "center": "(h-text_h)/2"}
        draws = []
        for n, c in enumerate(texts):
            tf = Path(tmpdir) / f"cap{n}.txt"
            tf.write_text(c["text"], encoding="utf-8")
            s = c["timeline_start_ms"] / 1000
            e = s + c["duration_ms"] / 1000
            y = ypos.get(c.get("position"), "h-text_h-h*0.08")
            draws.append(f"drawtext=fontfile='{ff_escape_path(font)}':textfile='{ff_escape_path(tf)}':"
                         f"fontsize={fs}:fontcolor=white:borderw=3:bordercolor=black@0.85:"
                         f"expansion=none:x=(w-text_w)/2:y={y}:enable='between(t,{s:.3f},{e:.3f})'")
        filters.append(f"[{vout}]{','.join(draws)}[vtxt]")
        vout = "vtxt"

    if audio_labels:
        mix = "".join(f"[{a}]" for a in audio_labels)
        filters.append(f"{mix}amix=inputs={len(audio_labels)}:duration=longest:normalize=0,"
                       f"atrim=end={total:.3f},apad=whole_dur={total:.3f}[aout]")
    else:
        filters.append(f"anullsrc=r={sample_rate}:cl=stereo,atrim=end={total:.3f}[aout]")

    fmt = exp.get("file_format", "mp4")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
           "-filter_complex", ";".join(filters), "-map", f"[{vout}]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-crf", "23" if preview else "18",
           "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate),
           "-t", f"{total:.3f}"]
    if fmt == "mp4":
        cmd += ["-movflags", "+faststart"]
    cmd.append(str(out_path))
    return cmd, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("-o", "--output")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the ffmpeg command (caption textfiles live in a temp dir deleted on exit)")
    ap.add_argument("--preview", action="store_true", help="fast 540p render")
    ap.add_argument("--font", default=DEFAULT_FONT)
    ap.add_argument("--font-size", type=int, default=48)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe not found on PATH")

    story_path = Path(args.story).resolve()
    doc = json.loads(story_path.read_text(encoding="utf-8"))
    base = story_path.parent
    ext = doc.get("export", {}).get("file_format", "mp4")
    out = Path(args.output) if args.output else base / "export" / f"final{'_preview' if args.preview else ''}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        cmd, total = build(doc, base, out, args.preview, args.font, args.font_size, tmp)
        if args.dry_run:
            print(subprocess.list2cmdline(cmd))
            return
        print(f"rendering {total:.2f}s → {out}")
        res = subprocess.run(cmd)
        if res.returncode:
            sys.exit(f"ffmpeg failed with code {res.returncode}")
    print(f"done: {out}")


if __name__ == "__main__":
    main()
