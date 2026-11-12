"""Run: python tests/test_validate.py  (from scripts/, no pytest needed)."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate_story import validate  # noqa: E402

SAMPLE = json.loads((HERE.parent.parent / "examples" / "sample-story.json").read_text(encoding="utf-8"))


def doc():
    return copy.deepcopy(SAMPLE)


def first_shot(d):
    return d["scenes"][0]["shots"][0]


def main_clips(d):
    return [c for c in d["timeline"]["clips"] if c["track_id"] == "tr_v1"]


def run(d, stage="planning", **kw):
    errors, warnings, _ = validate(d, stage=stage, **kw)
    return errors, warnings


def has(msgs, text):
    return any(text in m for m in msgs)


def test_sample_planning_clean():
    errors, _ = run(doc())
    assert not errors, errors


def test_missing_active_warns_at_generation():
    d = doc()
    first_shot(d)["active_version_id"] = None
    errors, warnings = run(d, "generation")
    assert not errors, errors
    assert has(warnings, "no active_version_id"), warnings
    assert not has(run(d, "planning")[1], "no active_version_id")


def test_failed_active_errors_at_generation():
    d = doc()
    shot = first_shot(d)
    shot["versions"][0]["status"] = "failed"
    shot["active_version_id"] = shot["versions"][0]["id"]
    assert has(run(d, "generation")[0], "status failed")
    assert not has(run(d, "planning")[0], "status failed")


def test_world_id_must_be_world():
    d = doc()
    d["scenes"][0]["world_id"] = d["bible"]["characters"][0]["id"]
    assert has(run(d)[0], "world_id")


def test_self_chain_errors():
    d = doc()
    shot = first_shot(d)
    shot["chain_from"] = shot["id"]
    assert has(run(d)[0], "points to itself")


def test_chain_cycle_errors():
    d = doc()
    a, b = d["scenes"][0]["shots"][:2]
    a["chain_from"], b["chain_from"] = b["id"], a["id"]
    assert has(run(d)[0], "cycle")


def test_overlap_mismatch_errors_and_correct_passes():
    d = doc()
    cl2 = main_clips(d)[1]
    cl2["transition_in"]["duration_ms"] = 200  # real overlap is 500 ms
    assert has(run(d)[0], "does not match transition"), run(d)[0]
    cl2["transition_in"]["duration_ms"] = 500
    assert not has(run(d)[0], "overlap"), run(d)[0]


def test_export_without_review_errors():
    d = doc()
    errors, _ = run(d, "export", base=SAMPLE_BASE)
    assert has(errors, "review is missing"), errors


SAMPLE_BASE = HERE
CRIT = {"start": "a", "complete": "b"}
_TMP = Path(tempfile.mkdtemp(prefix="vstory_"))


def _media(name, data):
    p = _TMP / "media" / name
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(data)
    return hashlib.sha1(data).hexdigest()


def _pass(sha, rng=(0, 4000)):
    return {"status": "pass", "media_sha1": sha, "range_ms": list(rng), "scope": ["frames", "playback"],
            "reviewer": "video-reviewer", "playback_by": "user", "date": "2026-11-08",
            "criteria": {"start": "met", "complete": "met"}}


def _side(cid, vid, sha, i=0, o=3000, speed=1):
    return {"clip_id": cid, "version_id": vid, "media_sha1": sha, "source_in_ms": i, "source_out_ms": o, "speed": speed}


def export_doc():
    """two shots, two main-track clips, full pass records, one matching edit point review"""
    shots, clips, shas = [], [], {}
    for n in (1, 2):
        sha = _media(f"s{n}.mp4", f"clip-{n}".encode() * 10)
        shas[n] = sha
        shots.append({"id": f"S{n}", "order": n, "duration_ms": 3000, "action": "x", "success_criteria": dict(CRIT),
                      "versions": [{"id": f"S{n}-v1", "kind": "video", "media_url": f"media/s{n}.mp4", "status": "done",
                                    "review": _pass(sha)}], "active_version_id": f"S{n}-v1"})
        clips.append({"id": f"cl{n}", "kind": "shot", "track_id": "tr_v1", "shot_id": f"S{n}", "version_id": f"S{n}-v1",
                      "timeline_start_ms": (n - 1) * 3000, "source_in_ms": 0, "source_out_ms": 3000, "speed": 1,
                      "media_url": f"media/s{n}.mp4", "media_kind": "video", "enabled": True})
    d = {"bible": {"style": {"anchor": "s"}}, "scenes": [{"id": "sc1", "order": 1, "shots": shots}],
         "timeline": {"tracks": [{"id": "tr_v1", "type": "video", "order": "a"}], "clips": clips,
                      "edit_point_reviews": [{"a": _side("cl1", "S1-v1", shas[1]), "b": _side("cl2", "S2-v1", shas[2]),
                                              "transition": None, "status": "pass", "reviewer": "video-reviewer",
                                              "playback_by": "user", "date": "2026-11-08"}]}}
    return d


def exp(d):
    return run(d, "export", base=_TMP)[0]


def ver(d, n=1):
    return d["scenes"][0]["shots"][n - 1]["versions"][0]


def test_full_record_passes_export():
    d = export_doc()
    assert not exp(d), exp(d)


def test_pass_only_record_blocked():
    d = export_doc()
    ver(d)["review"] = {"status": "pass"}
    errs = exp(d)
    for f in ("media_sha1", "range_ms", "scope", "reviewer", "playback_by", "date", "criteria"):
        assert has(errs, f"review.{f}"), (f, errs)


def test_missing_success_criteria_blocked_at_export_only():
    d = export_doc()
    del d["scenes"][0]["shots"][0]["success_criteria"]
    assert has(exp(d), "missing success_criteria")
    assert not has(run(d, "generation", base=_TMP)[0], "success_criteria")


def test_criteria_must_be_met():
    for bad in ("unverified", "not_met", None):
        d = export_doc()
        if bad is None:
            del ver(d)["review"]["criteria"]["complete"]
        else:
            ver(d)["review"]["criteria"]["complete"] = bad
        assert has(exp(d), "criteria"), bad


def test_playback_scope_and_actor_required():
    d = export_doc()
    ver(d)["review"]["scope"] = ["frames", "metrics"]
    assert has(exp(d), "review.scope")
    d = export_doc()
    ver(d)["review"]["playback_by"] = "me"
    assert has(exp(d), "review.playback_by")
    ver(d)["review"]["playback_by"] = "model:gemini"
    assert not exp(d), exp(d)


def test_sha_missing_empty_mismatch_blocked():
    for val in (None, "", "0" * 40):
        d = export_doc()
        if val is None:
            del ver(d)["review"]["media_sha1"]
        else:
            ver(d)["review"]["media_sha1"] = val
        assert has(exp(d), "media_sha1"), val


def test_active_version_vs_timeline_media_mismatch_blocked():
    d = export_doc()
    _media("other.mp4", b"other")
    main_clips(d)[0]["media_url"] = "media/other.mp4"
    assert has(exp(d), "not the reviewed version's media"), exp(d)
    d = export_doc()
    main_clips(d)[0]["version_id"] = "S1-v0"
    assert has(exp(d), "not the active version")
    d = export_doc()
    del main_clips(d)[0]["version_id"]
    assert has(exp(d), "no version_id")
    d = export_doc()
    main_clips(d)[0]["media_url"] = "./media/../media/s1.mp4"  # same file, different spelling
    assert not exp(d), exp(d)


def test_missing_output_media_blocked():
    d = export_doc()
    main_clips(d)[0]["media_url"] = "media/unreviewed-missing-video.mp4"
    errs = exp(d)
    assert has(errs, "media file not found: media/unreviewed-missing-video.mp4"), errs


def test_free_resource_clip_needs_own_review():
    d = export_doc()
    sha = _media("free.mp4", b"free")
    free = {"id": "cl_free", "kind": "resource", "track_id": "tr_v1", "timeline_start_ms": 6000, "source_in_ms": 0,
            "source_out_ms": 1000, "media_url": "media/free.mp4", "media_kind": "video"}
    d["timeline"]["clips"].append(free)
    assert has(exp(d), "clip cl_free review is missing"), exp(d)
    free["review"] = _pass(sha)
    assert not has(exp(d), "cl_free review"), exp(d)


def test_second_video_track_is_not_rendered_so_not_checked():
    d = export_doc()
    d["timeline"]["tracks"].append({"id": "tr_x", "type": "video", "order": "b"})
    d["timeline"]["clips"].append({"id": "cl_x", "kind": "resource", "track_id": "tr_x", "timeline_start_ms": 0,
                                   "source_in_ms": 0, "source_out_ms": 1000, "media_url": "media/none.mp4",
                                   "media_kind": "video"})
    assert not exp(d), exp(d)


def test_resource_clip_with_shot_id_cannot_bypass_review():
    d = export_doc()
    clip = d["timeline"]["clips"][1]
    clip["kind"] = "resource"
    v = ver(d, 2)
    v["status"] = "failed"
    v.pop("review")
    errors = exp(d)
    assert has(errors, "S2: active version S2-v1 has status failed"), errors
    assert has(errors, "review is missing"), errors


def test_dropped_shot_in_cut_is_caught_from_generation():
    d = doc()
    shot(d, "S1-1")["status"] = "dropped"
    assert has(run(d, "generation")[0], "S1-1: shot is dropped but an enabled timeline clip still uses it")
    assert not has(run(d, "planning")[0], "dropped")


def test_used_range_outside_reviewed_range_blocked():
    d = export_doc()
    ver(d)["review"]["range_ms"] = [0, 2000]
    errs = exp(d)
    assert has(errs, "outside reviewed range [0, 2000] ms, re-review"), errs


def test_edit_point_invalidated_by_changes():
    d = export_doc()
    del d["timeline"]["edit_point_reviews"]
    assert has(exp(d), "edit point cl1→cl2 not reviewed for the current cut")
    for change in ("trim_a", "trim_b", "speed_b", "transition", "version_b"):
        d = export_doc()
        a, b = main_clips(d)
        if change == "trim_a":
            a["source_out_ms"] = 2500
        elif change == "trim_b":
            b["source_in_ms"] = 500
        elif change == "speed_b":
            b["speed"] = 1.5
        elif change == "transition":
            b["transition_in"] = {"type": "dissolve", "duration_ms": 500}
            b["timeline_start_ms"] = 2500
        else:
            ver(d, 2)["id"] = "S2-v2"
            d["scenes"][0]["shots"][1]["active_version_id"] = "S2-v2"
            b["version_id"] = "S2-v2"
        assert has(exp(d), "not reviewed for the current cut"), (change, exp(d))


def test_edit_point_revise_or_incomplete_blocked():
    d = export_doc()
    d["timeline"]["edit_point_reviews"][0]["status"] = "revise"
    assert has(exp(d), "not reviewed for the current cut")
    d = export_doc()
    del d["timeline"]["edit_point_reviews"][0]["playback_by"]
    assert has(exp(d), "edit_point_reviews.playback_by")


def test_edit_point_follows_reorder():
    d = export_doc()
    a, b = main_clips(d)
    a["timeline_start_ms"], b["timeline_start_ms"] = 3000, 0  # swapped order: cl2 -> cl1 never reviewed
    assert has(exp(d), "edit point cl2→cl1 not reviewed"), exp(d)


def test_seam_uses_prev_range():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        return
    rv = HERE.parent.parent.parent / "ai-director-consistency" / "scripts" / "review_video.py"
    t = Path(tempfile.mkdtemp(prefix="seam_"))

    def ff(*a):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)

    ff("-f", "lavfi", "-i", "color=c=0x282828:s=320x240:r=24:d=1", "-f", "lavfi", "-i", "color=c=0xb4b4b4:s=320x240:r=24:d=1",
       "-filter_complex", "[0][1]concat=n=2:v=1[o]", "-map", "[o]", "-pix_fmt", "yuv420p", str(t / "prev.mp4"))
    ff("-f", "lavfi", "-i", "color=c=0x282828:s=320x240:r=24:d=2", "-pix_fmt", "yuv420p", str(t / "cur.mp4"))

    def seam(*extra):
        out = t / ("o" + str(len(extra)))
        subprocess.run([sys.executable, str(rv), str(t / "cur.mp4"), "--out", str(out), "--prev", str(t / "prev.mp4"), *extra],
                       check=True, capture_output=True)
        return json.loads((out / "metrics.json").read_text(encoding="utf-8"))["flags"]["seam"]["prev_to_this"]

    whole, used = seam(), seam("--prev-range", "0", "1000")
    assert whole["frame_diff"] > 100, whole
    assert used["frame_diff"] < 1, used
    assert used["a"]["used_range_ms"] == [0, 1000] and used["a"]["boundary_ms"] < 1000, used["a"]
    assert used["b"]["boundary_ms"] == 0, used["b"]


def shot(d, sid):
    return next(s for sc in d["scenes"] for s in sc["shots"] if s["id"] == sid)


def test_unused_shot_not_required_at_edit():
    d = doc()
    assert has(run(d, "edit")[0], "S2-2: active version S2-2-key is kind image")
    next(c for c in d["timeline"]["clips"] if c["id"] == "cl_4")["enabled"] = False
    assert not has(run(d, "edit")[0], "S2-2:"), run(d, "edit")[0]


def test_dropped_shot_skipped_unless_still_in_cut():
    d = doc()
    shot(d, "S2-2")["status"] = "dropped"
    assert has(run(d, "edit")[0], "S2-2: shot is dropped but an enabled timeline clip still uses it")
    next(c for c in d["timeline"]["clips"] if c["id"] == "cl_4")["enabled"] = False
    errors = run(d, "edit")[0]
    assert not has(errors, "S2-2:"), errors
    shot(d, "S2-2")["active_version_id"] = "missing"
    assert has(run(d, "planning")[0], "S2-2: active_version_id missing not in versions")


def ref_doc():
    d = doc()
    d["references"] = [
        {"id": "R01", "aspect": ["camera"], "kind": "video",
         "source": {"title": "own test", "path": "refs/board/src/R01.mp4", "in_ms": 1000, "out_ms": 4000},
         "rights": {"download": "yes", "analysis": "yes", "generation_input": "no",
                    "basis": "user's own footage", "checked": "2026-11-11"},
         "derived": ["refs/board/R01/frame_0004.png"],
         "evidence": {"dir": "refs/board/R01"},
         "observed": {"by": "agent", "date": "2026-11-11", "notes": "tilt up feet to face"},
         "status": "approved"},
        {"id": "R02", "aspect": ["mood", "location"], "kind": "link",
         "source": {"url": "https://example.com/clip", "in_ms": 0, "out_ms": 5000},
         "rights": {"download": "no", "analysis": "unknown", "generation_input": "no"},
         "observed": None, "status": "candidate"},
    ]
    first_shot(d)["reference_links"] = [{"ref_id": "R01", "aspect": "camera", "take": "4s tilt up, ends MCU"}]
    return d


def test_references_clean():
    errors, warnings = run(ref_doc())
    assert not errors, errors


def test_reference_bad_link_and_aspect():
    d = ref_doc()
    first_shot(d)["reference_links"] = [{"ref_id": "R09", "aspect": "camera", "take": "x"},
                                        {"ref_id": "R01", "aspect": "mood", "take": "x"},
                                        {"ref_id": "R01", "aspect": "camera", "take": ""}]
    errors = run(d)[0]
    assert has(errors, "R09 is not in references"), errors
    assert has(errors, "aspect mood is not one of"), errors
    assert has(errors, "has no take sentence"), errors


def test_reference_duplicate_and_range():
    d = ref_doc()
    d["references"][1]["id"] = "R01"
    d["references"][0]["source"]["out_ms"] = 500
    errors = run(d)[0]
    assert has(errors, "duplicate id R01"), errors
    assert has(errors, "in_ms must be"), errors


def test_reference_approved_needs_observed():
    d = ref_doc()
    d["references"][1]["status"] = "approved"
    assert has(run(d)[0], "R02: approved without observed"), run(d)[0]


def test_reference_link_only_cannot_have_evidence():
    d = ref_doc()
    d["references"][1]["evidence"] = {"contact_sheet": "x.jpg"}
    assert has(run(d)[0], "link-only refs cannot have evidence")


def test_reference_original_only_local_file_ok():
    d = ref_doc()
    src = d["references"][0]["source"]
    src["path_original"] = "D:/films/scene.mp4"
    del src["path"]
    d["references"][0]["derived"] = []
    d["references"][0]["rights"].update({"download": "no", "analysis": "yes", "generation_input": "no"})
    errors, warnings = run(d)
    assert not errors, errors
    assert not has(warnings, "R01: kind"), warnings


def test_reference_observed_modes():
    d = ref_doc()
    d["references"][0]["observed"]["mode"] = "dense_frames"
    assert has(run(d)[0], "needs interval_s and range_ms")
    d["references"][0]["observed"].update({"interval_s": 0.25, "range_ms": [0, 8000]})
    assert not has(run(d)[0], "observed.mode")
    d["references"][0]["observed"]["mode"] = "user_viewing"
    assert has(run(d)[0], "needs by: user")
    d["references"][0]["observed"]["mode"] = "watched"
    assert has(run(d)[0], "observed.mode must be")


def test_reference_bad_timecode_types():
    d = ref_doc()
    d["references"][0]["source"]["in_ms"] = "00:01"
    assert has(run(d)[0], "must be numbers")
    d = ref_doc()
    del d["references"][0]["source"]["out_ms"]
    assert has(run(d)[0], "must be given together")


def test_reference_files_used_as_generation_input_are_allowed():
    d = ref_doc()
    d["references"][0]["rights"] = {"generation_input": "no"}       # old field: ignored
    d["bible"]["worlds"][0]["ref_images"] = ["refs/board/src/R01.mp4"]
    first_shot(d)["versions"][0]["inputs"] = ["refs/board/R01/frame_0004.png"]
    d["references"][1].pop("rights", None)
    errors = run(d)[0]
    assert not errors, errors


def test_reference_candidate_and_stale_warn():
    d = ref_doc()
    d["bible"]["style"]["reference_links"] = [{"ref_id": "R02", "aspect": "mood", "take": "dark, one lamp", "stale": True}]
    errors, warnings = run(d)
    assert not errors, errors
    assert has(warnings, "still a candidate") and has(warnings, "is stale"), warnings
    d["references"][1]["status"] = "rejected"
    assert has(run(d)[0], "links rejected reference R02")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
