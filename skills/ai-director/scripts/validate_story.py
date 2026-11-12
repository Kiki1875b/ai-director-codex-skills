"""Validate a Director story.json: references, continuity fields, timeline limits.

Usage: python validate_story.py path/to/story.json [--target-ms 60000] [--stage planning|generation|edit|export]
Stages are cumulative: planning < generation < edit < export (default planning).
Exit code 1 when errors are found. Warnings never fail.
"""
import argparse
import hashlib
import json
import posixpath
import shutil
import subprocess
import sys
from pathlib import Path

TRANSITIONS = {"dissolve", "fade", "slide", "wipe", "clock_wipe", "iris", "zoom"}
DIRECTIONS = {"left", "right", "up", "down", "in", "out"}
TRACK_TYPES = {"video", "audio", "text", "other"}
MAX_TRANSITION_MS = 5000
STAGES = ("planning", "generation", "edit", "export")
OVERLAP_TOLERANCE_MS = 1
REF_ASPECTS = {"camera", "location", "mood"}
REF_KINDS = {"video", "image", "link"}
REF_STATUS = {"candidate", "approved", "rejected"}


def clip_length_ms(clip):
    if clip.get("kind") == "text":
        return clip.get("duration_ms", 0)
    return (clip.get("source_out_ms", 0) - clip.get("source_in_ms", 0)) / (clip.get("speed") or 1)


def probe_duration_ms(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out) * 1000
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def local_path(url, base):
    if base is None or url.startswith(("http://", "https://")):
        return None
    p = Path(url)
    return p if p.is_absolute() else Path(base) / p


def norm_url(url):
    url = str(url or "")
    return url if url.startswith(("http://", "https://")) else posixpath.normpath(url.replace("\\", "/"))


def valid_range(r):
    return (isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in r)
            and r[0] < r[1])


def valid_playback_by(by):
    return isinstance(by, str) and (by == "user" or (by.startswith("model:") and bool(by[6:].strip())))


def check_pass_record(label, review, path, url, criteria, errors):
    """Export-stage rule: a pass review must carry the full record. criteria = shot success_criteria
    (None for a free resource clip, which then needs a non-empty all-met criteria object)."""
    review = review or {}
    status = review.get("status")
    if status != "pass":
        errors.append(f"{label} review is {status or 'missing'}, not pass")
        return

    def bad(field, why):
        errors.append(f"{label}: review.{field} {why}")

    sha = review.get("media_sha1")
    if not isinstance(sha, str) or not sha.strip():
        bad("media_sha1", "is missing or empty")
    elif path and sha != sha1_of(path):
        bad("media_sha1", f"does not match {url} (file changed after review)")
    if not valid_range(review.get("range_ms")):
        bad("range_ms", "must be [in_ms, out_ms] integers with in < out")
    scope = review.get("scope")
    if not isinstance(scope, (list, str)) or "playback" not in scope:
        bad("scope", 'must include "playback"')
    for field in ("reviewer", "date"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            bad(field, "is missing or empty")
    if not valid_playback_by(review.get("playback_by")):
        bad("playback_by", 'must be "user" or "model:<name>"')
    crit = review.get("criteria")
    if not isinstance(crit, dict):
        bad("criteria", 'must be an object mapping each success_criteria key to "met"')
        return
    if criteria is None:
        keys = list(crit)
        if not keys:
            bad("criteria", "is empty")
    else:
        keys = [k for k, v in criteria.items() if v]
    for k in keys:
        if crit.get(k) != "met":
            bad(f"criteria.{k}", f'is {crit.get(k, "missing")}, must be "met"')


def check_chains(shots, errors):
    by_id = {s["id"]: s for s in shots}
    for s in shots:
        if s.get("chain_from") == s["id"]:
            errors.append(f"{s['id']}: chain_from points to itself")
    reported = set()
    for s in shots:
        seen, cur = [], s["id"]
        while cur in by_id and by_id[cur].get("chain_from") and by_id[cur]["chain_from"] != cur:
            if cur in seen:
                cycle = seen[seen.index(cur):]
                if frozenset(cycle) not in reported:
                    reported.add(frozenset(cycle))
                    errors.append(f"chain_from cycle: {' -> '.join(cycle + [cur])}")
                break
            seen.append(cur)
            cur = by_id[cur]["chain_from"]


def main_video_track_id(doc):
    """Same rule as render_timeline.py: the first visible video track (by order) is the only one rendered."""
    tracks = doc.get("timeline", {}).get("tracks", [])
    vt = sorted((t for t in tracks if t.get("type") == "video" and not t.get("hidden")), key=lambda t: str(t.get("order", "")))
    return vt[0]["id"] if vt else None


def rendered_clips(doc):
    """Enabled clips on the rendered video track (any kind)."""
    main = main_video_track_id(doc)
    return [c for c in doc.get("timeline", {}).get("clips", []) if c.get("track_id") == main and c.get("enabled", True)]


def used_shot_ids(doc):
    """Shots the render actually reaches (any clip kind that carries shot_id); None when no clip references a shot."""
    if not any(c.get("shot_id") for c in doc.get("timeline", {}).get("clips", [])):
        return None
    return {c["shot_id"] for c in rendered_clips(doc) if c.get("shot_id")}


def check_stage(doc, shots, stage, base, errors, warnings):
    rank = STAGES.index(stage)
    used = used_shot_ids(doc) if rank >= 1 else None
    for shot in shots:
        sid = shot["id"]
        if rank >= 1 and shot.get("status") == "dropped":
            if used is not None and sid in used:
                errors.append(f"{sid}: shot is dropped but an enabled timeline clip still uses it")
            continue  # kept for history; reference integrity is checked in validate(), production checks are not
        if rank >= 2 and used is not None and sid not in used:
            continue  # edit/export: only shots the rendered cut actually uses must be finished
        versions = {v["id"]: v for v in shot.get("versions", [])}
        active = versions.get(shot.get("active_version_id"))
        if rank >= 1:
            if versions and not shot.get("active_version_id"):
                warnings.append(f"{sid}: has versions but no active_version_id")
            if active and active.get("status") == "failed":
                errors.append(f"{sid}: active version {active['id']} has status failed")
            if not shot.get("success_criteria"):
                (errors if rank >= 3 else warnings).append(f"{sid}: missing success_criteria")
        if rank >= 2 and active:
            path = None
            if active.get("kind") != "video":
                errors.append(f"{sid}: active version {active['id']} is kind {active.get('kind')}, not video")
            else:
                if not active.get("media_url"):
                    errors.append(f"{sid}: active version {active['id']} has no media_url")
                else:
                    path = local_path(active["media_url"], base)
                    if path and not path.is_file():
                        errors.append(f"{sid}: media file not found: {active['media_url']}")
                        path = None
                label = f"{sid}: active video version {active['id']}"
                if rank >= 3:
                    check_pass_record(label, active.get("review"), path, active["media_url"], shot.get("success_criteria"), errors)
                elif (active.get("review") or {}).get("status") != "pass":
                    warnings.append(f"{label} review is {(active.get('review') or {}).get('status', 'missing')}, not pass")
        elif rank >= 3 and not active:
            errors.append(f"{sid}: no active version to export")


def check_export_timeline(doc, shots, main_track_id, base, errors, warnings):
    """Export only: render target linked to the reviewed version, used range inside the reviewed range,
    every main-track edit point reviewed for the current cut."""
    by_id = {s["id"]: s for s in shots}
    timeline = doc.get("timeline", {})
    durations, shas = {}, {}
    ffprobe_missing = not shutil.which("ffprobe")

    def sha_of(path):
        if path not in shas:
            shas[path] = sha1_of(path)
        return shas[path]

    info = {}  # clip id -> (version_id, sha1 of the file, else the reviewed sha1)
    for c in rendered_clips(doc):
        if c.get("media_kind") != "video":
            continue
        cid, url = c["id"], c.get("media_url", "")
        path = local_path(url, base) if url else None
        file_ok = bool(path and path.is_file())
        if path and not file_ok:
            errors.append(f"clip {cid}: media file not found: {url}")
        review, vid = None, c.get("version_id")
        if c.get("shot_id"):
            shot = by_id.get(c["shot_id"])
            if not shot:
                errors.append(f"clip {cid}: unknown shot_id {c['shot_id']}")
            elif not vid:
                errors.append(f"clip {cid}: has shot_id {c['shot_id']} but no version_id")
            elif vid != shot.get("active_version_id"):
                errors.append(f"clip {cid}: version_id {vid} is not the active version {shot.get('active_version_id')} of {shot['id']}")
            else:
                ver = next((v for v in shot.get("versions", []) if v["id"] == vid), {})
                review = ver.get("review")
                if norm_url(url) != norm_url(ver.get("media_url")):
                    errors.append(f"clip {cid}: media_url {url} is not the reviewed version's media {ver.get('media_url')}")
        else:
            review = c.get("review")
            check_pass_record(f"clip {cid}", review, path if file_ok else None, url, None, errors)
        if isinstance(review, dict) and review.get("status") == "pass" and valid_range(review.get("range_ms")):
            lo, hi = review["range_ms"]
            used_in, used_out = c.get("source_in_ms", 0), c.get("source_out_ms", 0)
            if used_in < lo or used_out > hi:
                errors.append(f"clip {cid}: used range [{used_in}, {used_out}] ms outside reviewed range [{lo}, {hi}] ms, re-review")
        info[cid] = (vid, sha_of(path) if file_ok else (review or {}).get("media_sha1") if isinstance(review, dict) else None)
        if file_ok and not ffprobe_missing:
            if path not in durations:
                durations[path] = probe_duration_ms(path)
            dur = durations[path]
            if dur is not None and c.get("source_out_ms", 0) > dur + 1:
                errors.append(f"clip {cid}: source_out_ms {c['source_out_ms']} exceeds media duration {dur:.0f}ms")
    if ffprobe_missing:
        warnings.append("ffprobe not found: clip source_in/out vs media duration not checked")

    def side(c):
        return {"clip_id": c["id"], "version_id": info[c["id"]][0], "media_sha1": info[c["id"]][1],
                "source_in_ms": c.get("source_in_ms"), "source_out_ms": c.get("source_out_ms"), "speed": c.get("speed", 1) or 1}

    def trans(t):
        return {"type": t.get("type"), "duration_ms": t.get("duration_ms")} if isinstance(t, dict) and t else None

    main = sorted((c for c in timeline.get("clips", []) if c.get("track_id") == main_track_id and c.get("enabled", True)
                   and c.get("media_kind") == "video" and "timeline_start_ms" in c), key=lambda c: c["timeline_start_ms"])
    records = [r for r in timeline.get("edit_point_reviews", []) if isinstance(r, dict)]
    for prev, cur in zip(main, main[1:]):
        want_a, want_b, want_t = side(prev), side(cur), trans(cur.get("transition_in"))
        match = [r for r in records if r.get("a") == want_a and r.get("b") == want_b and trans(r.get("transition")) == want_t]
        name = f"edit point {prev['id']}→{cur['id']}"
        ok = [r for r in match if r.get("status") == "pass"]
        if not ok:
            extra = f" (matching record is {match[0].get('status')})" if match else ""
            errors.append(f"{name} not reviewed for the current cut{extra}")
            continue
        r = ok[0]
        for field in ("reviewer", "date"):
            if not isinstance(r.get(field), str) or not r[field].strip():
                errors.append(f"{name}: edit_point_reviews.{field} is missing or empty")
        if not valid_playback_by(r.get("playback_by")):
            errors.append(f'{name}: edit_point_reviews.playback_by must be "user" or "model:<name>"')


def check_overlaps(doc, tracks, errors, warnings):
    for tid, t in tracks.items():
        if t.get("type") != "video":
            continue
        clips = sorted((c for c in doc["timeline"].get("clips", []) if c.get("track_id") == tid
                        and c.get("enabled", True) and "timeline_start_ms" in c), key=lambda c: c["timeline_start_ms"])
        for prev, cur in zip(clips, clips[1:]):
            overlap = prev["timeline_start_ms"] + clip_length_ms(prev) - cur["timeline_start_ms"]
            tdur = (cur.get("transition_in") or {}).get("duration_ms", 0)
            if overlap > OVERLAP_TOLERANCE_MS:
                if abs(overlap - tdur) > OVERLAP_TOLERANCE_MS:
                    errors.append(f"clip {cur['id']}: overlap {overlap:.0f} ms does not match transition {tdur} ms "
                                  f"(after {prev['id']}; start it at previous end - transition duration)")
            elif overlap < -OVERLAP_TOLERANCE_MS:
                warnings.append(f"clip {cur['id']}: gap of {-overlap:.0f}ms after {prev['id']} (renders black)")
            if tdur and overlap <= OVERLAP_TOLERANCE_MS:
                warnings.append(f"clip {cur['id']}: has transition_in but does not overlap {prev['id']}; renderer will hard-cut")


def check_references(doc, errors, warnings):
    """references[] ledger (ai-director-reference) and reference_links[] in bible/scenes/shots.
    Licences / usage rights are not checked (user decision 2026-11-11); an old `rights` field is ignored."""
    refs = doc.get("references", [])
    if not isinstance(refs, list):
        errors.append("references must be a list")
        return
    by_id = {}
    for r in refs:
        rid = r.get("id")
        if not rid:
            errors.append("references: item without id")
            continue
        if rid in by_id:
            errors.append(f"references: duplicate id {rid}")
        by_id[rid] = r
        asp = r.get("aspect") or []
        if isinstance(asp, str):
            asp = [asp]
        if not asp or any(a not in REF_ASPECTS for a in asp):
            errors.append(f"references {rid}: aspect must be a non-empty list of camera|location|mood")
        if r.get("kind") not in REF_KINDS:
            errors.append(f"references {rid}: kind must be video|image|link")
        if r.get("status") not in REF_STATUS:
            errors.append(f"references {rid}: status must be candidate|approved|rejected")
        src = r.get("source") or {}
        local = src.get("path") or src.get("path_original")
        if not (src.get("url") or local):
            errors.append(f"references {rid}: source needs url, path or path_original")
        if r.get("kind") == "link" and local:
            warnings.append(f"references {rid}: kind link but a local file is set (use video|image)")
        if r.get("kind") in ("video", "image") and not local:
            warnings.append(f"references {rid}: kind {r.get('kind')} without a local file (path or path_original; use kind link)")
        a, b = src.get("in_ms"), src.get("out_ms")
        if (a is None) != (b is None):
            errors.append(f"references {rid}: source.in_ms and out_ms must be given together")
        elif a is not None:
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (a, b)):
                errors.append(f"references {rid}: source.in_ms/out_ms must be numbers (ms)")
            elif not 0 <= a < b:
                errors.append(f"references {rid}: source.in_ms must be >= 0 and < out_ms")
        if r.get("evidence") and not (src.get("path") or src.get("path_original")):
            errors.append(f"references {rid}: evidence without a local file (source.path or path_original; "
                          "link-only refs cannot have evidence)")
        obs = r.get("observed")
        if obs is not None and (not isinstance(obs, dict) or obs.get("by") not in ("agent", "user") or not obs.get("notes")):
            errors.append(f"references {rid}: observed must be null or {{by: agent|user, date, notes}}")
        if isinstance(obs, dict):
            mode = obs.get("mode")
            if mode not in (None, "contact_sheet", "dense_frames", "playback", "user_viewing"):
                errors.append(f"references {rid}: observed.mode must be contact_sheet|dense_frames|playback|user_viewing")
            if mode == "dense_frames" and not (obs.get("interval_s") and obs.get("range_ms")):
                errors.append(f"references {rid}: observed.mode dense_frames needs interval_s and range_ms")
            if mode == "user_viewing" and obs.get("by") != "user":
                errors.append(f"references {rid}: observed.mode user_viewing needs by: user")
        if r.get("status") == "approved" and not obs:
            errors.append(f"references {rid}: approved without observed (nobody has looked at it)")

    bible = doc.get("bible", {})
    holders = [("bible.style", bible.get("style") or {})]
    holders += [(f"bible.worlds.{w.get('id')}", w) for w in bible.get("worlds", [])]
    for sc in doc.get("scenes", []):
        holders.append((sc.get("id", "?"), sc))
        holders += [(sh.get("id", "?"), sh) for sh in sc.get("shots", [])]
    for where, h in holders:
        for ln in h.get("reference_links") or []:
            rid = ln.get("ref_id")
            r = by_id.get(rid)
            if r is None:
                errors.append(f"{where}: reference_links ref_id {rid} is not in references[]")
                continue
            asp = r.get("aspect") or []
            asp = [asp] if isinstance(asp, str) else asp
            if ln.get("aspect") not in asp:
                errors.append(f"{where}: reference_links {rid} aspect {ln.get('aspect')} is not one of {asp}")
            if not ln.get("take"):
                errors.append(f"{where}: reference_links {rid} has no take sentence")
            if r.get("status") == "rejected":
                errors.append(f"{where}: links rejected reference {rid}")
            elif r.get("status") == "candidate":
                warnings.append(f"{where}: links reference {rid} that is still a candidate")
            if ln.get("stale"):
                warnings.append(f"{where}: reference_links {rid} is stale (reference changed, re-check this plan)")


def validate(doc, target_ms=None, stage="planning", base=None):
    """base = folder of story.json; media files are only checked when it is given."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage}")
    errors, warnings = [], []
    bible = doc.get("bible", {})
    entity_ids, world_ids = set(), set()
    for group in ("characters", "objects", "worlds"):
        for ent in bible.get(group, []):
            if ent["id"] in entity_ids:
                errors.append(f"bible: duplicate id {ent['id']}")
            entity_ids.add(ent["id"])
            if group == "worlds":
                world_ids.add(ent["id"])
            if not ent.get("anchor"):
                errors.append(f"bible: {ent['id']} has no anchor sentence")
            if not ent.get("ref_images"):
                warnings.append(f"bible: {ent['id']} has no reference images yet")
    if not bible.get("style", {}).get("anchor"):
        warnings.append("bible: style.anchor is empty")

    shots, shot_ids = [], set()
    for scene in sorted(doc.get("scenes", []), key=lambda s: s.get("order", 0)):
        if scene.get("world_id") and scene["world_id"] not in world_ids:
            errors.append(f"{scene['id']}: world_id {scene['world_id']} is not a bible.worlds id")
        for shot in sorted(scene.get("shots", []), key=lambda s: s.get("order", 0)):
            sid = shot["id"]
            if sid in shot_ids:
                errors.append(f"duplicate shot id {sid}")
            shot_ids.add(sid)
            shots.append(shot)
            for ref in shot.get("characters", []) + shot.get("objects", []):
                if ref not in entity_ids:
                    errors.append(f"{sid}: unknown bible entity {ref}")
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

    check_chains(shots, errors)
    check_references(doc, errors, warnings)
    check_overlaps(doc, tracks, errors, warnings)
    check_stage(doc, shots, stage, base, errors, warnings)
    if STAGES.index(stage) >= 3:
        check_export_timeline(doc, shots, main_track_id, base, errors, warnings)

    exp = doc.get("export", {})
    if exp:
        if not 1 <= exp.get("fps", 30) <= 60:
            errors.append("export: fps must be 1–60")
        w, h = exp.get("width", 1920), exp.get("height", 1080)
        if not (120 <= w <= 3840 and 120 <= h <= 2160):
            errors.append("export: resolution must be within 120x120–3840x2160")
        if w % 2 or h % 2:
            errors.append("export: width and height must be even (H.264)")
        if exp.get("fit", "pad") not in ("pad", "crop"):
            errors.append("export: fit must be pad or crop")
    ar = doc.get("story", {}).get("format", {}).get("aspect_ratio")
    if ar and exp:
        want = {"9:16": 9 / 16, "16:9": 16 / 9, "2.39:1": 2.39}.get(ar)
        w, h = exp.get("width", 1920), exp.get("height", 1080)
        if want is None:
            warnings.append(f"story.format.aspect_ratio {ar!r} is not one of 9:16, 16:9, 2.39:1 (references/aspect-ratios.md)")
        elif abs(w / h - want) / want > 0.02:
            errors.append(f"export {w}x{h} does not match story.format.aspect_ratio {ar}")
        if not 16000 <= exp.get("sample_rate", 48000) <= 48000:
            errors.append("export: sample_rate must be 16000–48000")
        if exp.get("file_format", "mp4") not in ("mp4", "mov"):
            errors.append("export: file_format must be mp4 or mov")

    if target_ms and end_ms and stage == "export" and abs(end_ms - target_ms) > target_ms * 0.1:
        errors.append(f"timeline video length {end_ms/1000:.1f}s is outside ±10% of target {target_ms/1000:.1f}s")
    elif target_ms and end_ms and abs(end_ms - target_ms) > 1000:
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
    ap.add_argument("--stage", choices=STAGES, default="planning")
    args = ap.parse_args()
    doc = json.loads(Path(args.story).read_text(encoding="utf-8"))
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        errors, warnings, end_ms = validate(doc, args.target_ms, args.stage, Path(args.story).resolve().parent)
    except KeyError as e:
        print(f"ERROR required field {e} is missing (every bible entity, scene, shot and version needs an id)")
        sys.exit(1)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"stage: {args.stage} | video timeline length: {end_ms/1000:.2f}s | {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
