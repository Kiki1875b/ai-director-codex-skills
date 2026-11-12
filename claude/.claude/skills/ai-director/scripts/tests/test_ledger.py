"""Offline tests for ledger.py (no GPU, no network)."""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ledger  # noqa: E402


def make_story(tmp):
    root = Path(tmp) / "stories" / "demo"
    (root / "media" / "video").mkdir(parents=True)
    (root / "reviews").mkdir()
    story = {"scenes": [{"id": "S1", "shots": [
        {"id": "S1-3", "active_version_id": "S1-3-v2",
         "versions": [{"id": "S1-3-v2", "review": {"status": "pass", "by": "user"}}]}]}]}
    (root / "story.json").write_text(json.dumps(story), encoding="utf-8")
    return root


def test_record_and_summary():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_story(tmp)
        key = root / "media" / "S1-3-key-v1.png"
        key.write_bytes(b"png")
        out = root / "media" / "video" / "S1-3-ltx-v2.mp4"
        ledger.record(str(out), "gen_submit", tool="ltx_remote", job_id="j1", seed=5, prompt="p", inputs=[str(key), None])
        hist = {"status": {"messages": [["execution_start", {"timestamp": 1000}],
                                        ["execution_success", {"timestamp": 361000}]]}}
        assert ledger.exec_seconds(hist) == 360.0
        ledger.record(str(out), "gen_done", tool="ltx_remote", job_id="j1", wall_s=400.0, exec_s=ledger.exec_seconds(hist))
        ledger.record(str(out), "gen_fail", tool="ltx_remote", job_id="j2")
        (root / "reviews" / "vid_S1-3_v2.md").write_text("x", encoding="utf-8")
        evs = [json.loads(l) for l in (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [e["kind"] for e in evs] == ["gen_submit", "gen_done", "gen_fail"]
        assert evs[0]["shot"] == "S1-3" and evs[0]["out"] == "media/video/S1-3-ltx-v2.mp4"
        assert len(evs[0]["inputs"]) == 1 and evs[0]["inputs"][0]["sha256"]
        assert "prompt" not in evs[0] and len(evs[0]["prompt_sha256"]) == 64
        buf = io.StringIO()
        with redirect_stdout(buf):
            ledger.summary(str(root))
        txt = buf.getvalue()
        line = next(l for l in txt.splitlines() if l.startswith("S1-3"))
        cols = line.split()
        # ok fail open GPUok GPUfail wait n/m rev reject taste change to-accept
        assert cols[1:9] == ["1", "1", "0", "6.0", "0.0", "6.7", "1", "1"], line  # j2 failed without timing -> n/m 1
        assert "S1-3-v2 / pass(user)" in line
        assert cols[9:13] == ["0", "0", "0", "-"], line  # no user verdicts yet
        with redirect_stdout(io.StringIO()):
            ledger.user_verdict(str(root), "S1-3", "reject", "S1-3-v1", "face changed")
            ledger.user_verdict(str(root), "S1-3", "change", note="new palette")
            ledger.user_verdict(str(root), "S1-3", "accept", "S1-3-v2")
        buf = io.StringIO()
        with redirect_stdout(buf):
            ledger.summary(str(root))
        line = next(l for l in buf.getvalue().splitlines() if l.startswith("S1-3"))
        cols = line.split()
        assert cols[9:12] == ["1", "0", "1"], line
        assert float(cols[12]) >= 0.0, line
        try:
            ledger.user_verdict(str(root), "S1-3", "maybe")
            raise AssertionError("bad verdict accepted")
        except SystemExit:
            pass


def _row(root, shot):
    buf = io.StringIO()
    with redirect_stdout(buf):
        ledger.summary(str(root))
    return next(l for l in buf.getvalue().splitlines() if l.startswith(shot)).split()


def test_refetch_counts_once_and_failures_cost_time():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_story(tmp)
        out = str(root / "media" / "video" / "S2-1-x.mp4")
        ledger.record(out, "gen_submit", tool="rerun_workflow", job_id="J")
        ledger.record(out, "gen_done", tool="rerun_workflow", job_id="J", exec_s=60, wall_s=70)
        ledger.record(out, "gen_done", tool="ltx_remote", job_id="J", exec_s=60, wall_s=5)  # --fetch again
        ledger.record(out, "gen_submit", tool="ltx_remote", job_id="F")
        ledger.record(out, "gen_fail", tool="ltx_remote", job_id="F", exec_s=120, wall_s=130)
        ledger.record(out, "gen_submit", tool="ltx_remote", job_id="T")
        ledger.record(out, "gen_timeout", tool="ltx_remote", job_id="T", wall_s=600)
        ledger.record(out, "gen_submit", tool="ltx_remote", job_id="O")  # still running
        c = _row(root, "S2-1")
        assert c[1:8] == ["1", "2", "1", "1.0", "2.0", "13.3", "1"], c  # T has no server time -> n/m


def test_codex_image_runs_are_not_comfy_unmeasured():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_story(tmp)
        out = str(root / "media" / "S3-1-key-v1.png")
        ledger.record(out, "gen_submit", tool="codex_image", job_id="r1")
        ledger.record(out, "gen_hold", tool="codex_image", job_id="r1", wall_s=50)
        c = _row(root, "S3-1")
        assert c[1:8] == ["0", "1", "0", "0.0", "0.0", "0.8", "0"], c


def test_outside_story_is_ignored_and_never_raises():
    with tempfile.TemporaryDirectory() as tmp:
        ledger.record(os.path.join(tmp, "x.mp4"), "gen_done")
        assert not os.path.exists(os.path.join(tmp, "ledger.jsonl"))
    assert ledger.exec_seconds({}) is None


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name); n += 1
    print(f"{n}/{n} passed")
