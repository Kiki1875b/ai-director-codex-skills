"""Validate a Director story.json: references, continuity fields, timeline limits.

Usage: python validate_story.py path/to/story.json [--target-ms 60000]
Exit code 1 when errors are found. Warnings never fail.
"""
import argparse
import json
import sys
from pathlib import Path

TRANSITIONS = {"dissolve", "fade", "slide", "wipe", "clock_wipe", "iris", "zoom"}
DIRECTIONS = {"left", "right", "up", "down", "in", "out"}
MODES = {"text2video", "image2video", "reference2video", "element2video", "extend", "modify"}
TRACK_TYPES = {"video", "audio", "text", "other"}
MAX_TRANSITION_MS = 5000


def clip_length_ms(clip):
    if clip.get("kind") == "text":
        return clip.get("duration_ms", 0)
    return (clip.get("source_out_ms", 0) - clip.get("source_in_ms", 0)) / (clip.get("speed") or 1)


def validate(doc, target_ms=None):
    errors, warnings = [], []
    bible = doc.get("bible", {})
    entity_ids = set()
    for group in ("characters", "objects", "worlds"):
        for ent in bible.get(group, []):
            if ent["id"] in entity_ids:
                errors.append(f"bible: duplicate id {ent['id']}")
            entity_ids.add(ent["id"])
            if not ent.get("anchor"):
                errors.append(f"bible: {ent['id']} has no anchor sentence")
            if not ent.get("ref_images"):
                warnings.append(f"bible: {ent['id']} has no reference images yet")
    if not bible.get("style", {}).get("anchor"):
        warnings.append("bible: style.anchor is empty")

    shots, shot_ids = [], set()
    for scene in sorted(doc.get("scenes", []), key=lambda s: s.get("order", 0)):
        if scene.get("world_id") and scene["world_id"] not in entity_ids:
            errors.append(f"{scene['id']}: unknown world_id {scene['world_id']}")
        for shot in sorted(scene.get("shots", []), key=lambda s: s.get("order", 0)):
            sid = shot["id"]
            if sid in shot_ids:
                errors.append(f"duplicate shot id {sid}")
            shot_ids.add(sid)
            shots.append(shot)
            for ref in shot.get("characters", []) + shot.get("objects", []):
                if ref not in entity_ids:
                    errors.append(f"{sid}: unknown bible entity {ref}")
            if shot.get("mode") and shot["mode"] not in MODES:
                errors.append(f"{sid}: unknown mode {shot['mode']}")
            if not shot.get("action"):
                errors.append(f"{sid}: missing action")
            for field in ("start_state", "end_state", "camera"):
                if not shot.get(field):
                    warnings.append(f"{sid}: missing {field}")
            if shot.get("duration_ms", 0) <= 0:
                errors.append(f"{sid}: duration_ms must be > 0")
            versions = {v["id"] for v in shot.get("versions", [])}
            active = shot.get("active_version_id")
            if active and active not in versions:
                errors.append(f"{sid}: active_version_id {active} not in versions")

    for prev, cur in zip(shots, shots[1:]):
        if cur.get("chain_from") and cur["chain_from"] != prev["id"]:
            warnings.append(f"{cur['id']}: chain_from={cur['chain_from']} is not the previous shot {prev['id']}")
        for ref in cur.get("characters", []):
            if ref in prev.get("characters", []) and prev.get("end_state") and not cur.get("start_state"):
                warnings.append(f"{cur['id']}: shares {ref} with {prev['id']} but has no start_state to check continuity")

    timeline = doc.get("timeline", {})
    for item in timeline.get("tracks", []) + timeline.get("clips", []):
        if not item.get("id"):
            errors.append(f"timeline item without id: {json.dumps(item, ensure_ascii=False)[:80]}")
            item["id"] = "?"
    tracks = {t["id"]: t for t in timeline.get("tracks", [])}
    video_tracks = sorted((t for t in tracks.values() if t.get("type") == "video" and not t.get("hidden")),
                          key=lambda t: str(t.get("order", "")))
    main_track_id = video_tracks[0]["id"] if video_tracks else None
    for t in tracks.values():
        if t.get("type") not in TRACK_TYPES:
            errors.append(f"track {t['id']}: bad type {t.get('type')}")
        if t.get("subtype") not in (None, "vo", "bgm"):
            errors.append(f"track {t['id']}: bad subtype {t.get('subtype')}")
    end_ms = 0
    for c in timeline.get("clips", []):
        cid = c["id"]
        if c.get("track_id") not in tracks:
            errors.append(f"clip {cid}: unknown track {c.get('track_id')}")
        if "timeline_start_ms" not in c:
            errors.append(f"clip {cid}: missing timeline_start_ms")
        elif c["timeline_start_ms"] < 0:
            errors.append(f"clip {cid}: timeline_start_ms < 0")
        track_type = tracks.get(c.get("track_id"), {}).get("type")
        if (c.get("kind") == "text") != (track_type == "text") and track_type:
            errors.append(f"clip {cid}: kind={c.get('kind')} cannot sit on a {track_type} track")
        if c.get("kind") != "text":
            if c.get("source_out_ms", 0) <= c.get("source_in_ms", 0):
                errors.append(f"clip {cid}: source_out_ms must be > source_in_ms")
            if not 0.5 <= c.get("speed", 1) <= 2:
                errors.append(f"clip {cid}: speed must be 0.5–2")
            if not 0 <= c.get("volume", 1) <= 3:
                errors.append(f"clip {cid}: volume must be 0–3")
            if not c.get("media_url"):
                errors.append(f"clip {cid}: missing media_url")
            if c.get("media_kind") not in ("video", "image", "audio"):
                errors.append(f"clip {cid}: media_kind must be video|image|audio")
        else:
            if not c.get("text"):
                errors.append(f"clip {cid}: text clip without text")
            if c.get("duration_ms", 0) <= 0:
                errors.append(f"clip {cid}: text clip needs duration_ms > 0")
        if c.get("kind") == "shot" and c.get("shot_id") not in shot_ids:
            errors.append(f"clip {cid}: unknown shot_id {c.get('shot_id')}")
        tr = c.get("transition_in")
        if tr:
            if tr.get("type") not in TRANSITIONS:
                errors.append(f"clip {cid}: bad transition type {tr.get('type')}")
            if not 0 < tr.get("duration_ms", 0) <= MAX_TRANSITION_MS:
                errors.append(f"clip {cid}: transition duration must be 1–{MAX_TRANSITION_MS}ms")
            if tr.get("direction") and tr["direction"] not in DIRECTIONS:
                errors.append(f"clip {cid}: bad transition direction {tr['direction']}")
        if c.get("track_id") == main_track_id and c.get("enabled", True):
            end_ms = max(end_ms, c.get("timeline_start_ms", 0) + clip_length_ms(c))

    main = sorted((c for c in timeline.get("clips", []) if c.get("track_id") == main_track_id
                   and c.get("enabled", True) and "timeline_start_ms" in c), key=lambda c: c["timeline_start_ms"])
    for prev, cur in zip(main, main[1:]):
        overlap = prev["timeline_start_ms"] + clip_length_ms(prev) - cur["timeline_start_ms"]
        tr = cur.get("transition_in")
        if tr and overlap <= 40:
            warnings.append(f"clip {cur['id']}: has transition_in but does not overlap {prev['id']} "
                            f"(start it at previous end - transition duration); renderer will hard-cut")
        elif not tr and overlap > 40:
            warnings.append(f"clip {cur['id']}: overlaps {prev['id']} by {overlap:.0f}ms without a transition")

    exp = doc.get("export", {})
    if exp:
        if not 1 <= exp.get("fps", 30) <= 60:
            errors.append("export: fps must be 1–60")
        w, h = exp.get("width", 1920), exp.get("height", 1080)
        if not (120 <= w <= 3840 and 120 <= h <= 2160):
            errors.append("export: resolution must be within 120x120–3840x2160")
        if w % 2 or h % 2:
            errors.append("export: width and height must be even (H.264)")
        if not 16000 <= exp.get("sample_rate", 48000) <= 48000:
            errors.append("export: sample_rate must be 16000–48000")
        if exp.get("file_format", "mp4") not in ("mp4", "mov"):
            errors.append("export: file_format must be mp4 or mov")

    if target_ms and end_ms and abs(end_ms - target_ms) > 1000:
        warnings.append(f"timeline video length {end_ms/1000:.1f}s differs from target {target_ms/1000:.1f}s")
    if target_ms and not end_ms:
        # no timeline yet (writer stage): check the planned shot durations instead
        planned = sum(s.get("duration_ms", 0) for s in shots)
        if not shots:
            errors.append("no shots under scenes[].shots — nothing to measure against --target-ms")
        elif abs(planned - target_ms) > target_ms * 0.1:
            errors.append(f"planned shot total {planned/1000:.1f}s is outside ±10% of target {target_ms/1000:.1f}s")
    if "shots" in doc:
        errors.append("top-level 'shots' is ignored; shots must live inside scenes[].shots")
    return errors, warnings, end_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--target-ms", type=int)
    args = ap.parse_args()
    doc = json.loads(Path(args.story).read_text(encoding="utf-8"))
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        errors, warnings, end_ms = validate(doc, args.target_ms)
    except KeyError as e:
        print(f"ERROR required field {e} is missing (every bible entity, scene, shot and version needs an id)")
        sys.exit(1)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"video timeline length: {end_ms/1000:.2f}s | {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
