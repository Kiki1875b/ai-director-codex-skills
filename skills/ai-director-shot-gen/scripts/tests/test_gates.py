"""Offline tests for the entry-point gates (no GPU, no network, no Codex).
Run: python tests/test_gates.py  (from ai-director-shot-gen/scripts)."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILLS = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILLS / "ai-director-edit" / "scripts"))
import comfy_guard  # noqa: E402
import codex_image  # noqa: E402
import render_timeline  # noqa: E402

SAMPLE = json.loads((SKILLS / "ai-director" / "examples" / "sample-story.json").read_text(encoding="utf-8"))


class FakeResp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def expect_exit(fn, *a, contains=""):
    try:
        fn(*a)
    except SystemExit as e:
        assert contains in str(e), str(e)
        return str(e)
    raise AssertionError("expected SystemExit")


def test_gpu_guard_blocks_busy_server():
    orig = comfy_guard.requests.get
    try:
        comfy_guard.requests.get = lambda *a, **k: FakeResp({"queue_running": [["x"]], "queue_pending": []})
        expect_exit(comfy_guard.require_free, "http://s", contains="GPU busy (1 running, 0 pending)")
        comfy_guard.require_free("http://s", allow_queue=True)  # explicit batch request passes
        comfy_guard.requests.get = lambda *a, **k: FakeResp({"queue_running": [], "queue_pending": []})
        comfy_guard.require_free("http://s")
    finally:
        comfy_guard.requests.get = orig


def test_gpu_guard_unreachable_server_stops():
    orig = comfy_guard.requests.get

    def boom(*a, **k):
        raise comfy_guard.requests.ConnectionError("down")
    try:
        comfy_guard.requests.get = boom
        expect_exit(comfy_guard.require_free, "http://s", contains="not reachable")
    finally:
        comfy_guard.requests.get = orig


def test_duplicate_label_for_two_images_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.png", Path(tmp) / "b.png"
        a.write_bytes(b"1"); b.write_bytes(b"2")
        expect_exit(codex_image.check_labels, [f"character_image1={a}", f"character_image1={b}"], contains="used for two")
        codex_image.check_labels([f"character_image1={a}", f"env_image1={b}"])
        codex_image.check_labels([f"character_image1={a}", f"character_image1={a}"])  # same file twice is not a clash


class TempJobs:
    """Point codex_image's registry and the lock dir at a temp folder."""
    def __enter__(self):
        import file_lock
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (codex_image.JOBS_DIR, file_lock.LOCK_DIR)
        codex_image.JOBS_DIR = Path(self.tmp.name) / "jobs"
        file_lock.LOCK_DIR = str(Path(self.tmp.name) / "locks")
        self.fl = file_lock
        return Path(self.tmp.name)

    def __exit__(self, *a):
        codex_image.JOBS_DIR, self.fl.LOCK_DIR = self.orig
        self.tmp.cleanup()


def test_attribution_overlap_and_claims():
    with TempJobs():
        mine = codex_image.job_open()
        start = time.time()
        assert codex_image.others(mine, start) == (False, set())
        me = os.getpid()
        other = codex_image.JOBS_DIR / "999_1.json"
        other.write_text(json.dumps({"start": start, "end": None, "pid": me, "create_time": None}), encoding="utf-8")
        assert codex_image.others(mine, start)[0] is True  # a live job still running -> overlap
        other.write_text(json.dumps({"start": start - 100, "end": start - 50, "claimed": "C:/x.png"}), encoding="utf-8")
        assert codex_image.others(mine, start) == (False, {codex_image.path_key("C:/x.png")})  # ended before us; PNG taken
        other.write_text("{", encoding="utf-8")  # half-written by another process
        assert codex_image.others(mine, start)[0] is True  # unreadable is never 'no other job'


def test_dead_job_does_not_block_new_jobs():
    with TempJobs():
        dead = codex_image.JOBS_DIR
        dead.mkdir(parents=True, exist_ok=True)
        stale = dead / "4000000_1.json"
        stale.write_text(json.dumps({"start": time.time() - 3600, "end": None, "pid": 4000000, "create_time": 1.0}),
                         encoding="utf-8")
        os.utime(stale, (time.time() - 3600, time.time() - 3600))
        mine = codex_image.job_open()
        assert codex_image.others(mine, time.time())[0] is False


def test_claim_hold_and_no_double_claim():
    with TempJobs():
        a, b = Path("C:/gen/a.png"), Path("C:/gen/b.png")
        j1 = codex_image.job_open()
        t = time.time()
        j2 = codex_image.job_open()  # overlapping, still open
        src, hold = codex_image.claim(j1, t, [a, b], None)
        assert src is None and "cannot be attributed" in hold  # no path + overlap -> HOLD, never a guess
        src, hold = codex_image.claim(j1, t, [a, b], a)
        assert src == a and hold is None  # explicit path is fine
        src, hold = codex_image.claim(j2, t, [a, b], a)
        assert src is None and "already claimed" in hold  # the same PNG cannot be claimed twice


def test_parallel_claims_never_share_a_png():
    import threading
    with TempJobs():
        pngs = [Path(f"C:/gen/{i}.png") for i in range(3)]
        jobs = [codex_image.job_open() for _ in range(3)]
        t = time.time()
        got, barrier = [], threading.Barrier(3)

        def run(j, p):
            barrier.wait()
            got.append(codex_image.claim(j, t, pngs, p)[0])
        threads = [threading.Thread(target=run, args=(jobs[i], pngs[0])) for i in range(3)]  # all report the same path
        [th.start() for th in threads]
        [th.join() for th in threads]
        assert sum(1 for g in got if g is not None) == 1, got


def test_submit_is_atomic_across_parallel_callers():
    import threading
    with TempJobs():
        state = {"queued": 0}
        lock = threading.Lock()
        orig_get, orig_post = comfy_guard.requests.get, comfy_guard.requests.post

        def fake_get(*a, **k):
            time.sleep(0.05)
            return FakeResp({"queue_running": [1] * state["queued"], "queue_pending": []})

        def fake_post(*a, **k):
            with lock:
                state["queued"] += 1
            return FakeResp({"prompt_id": "x"})
        comfy_guard.requests.get, comfy_guard.requests.post = fake_get, fake_post
        results, barrier = [], threading.Barrier(3)

        def run():
            barrier.wait()
            try:
                comfy_guard.submit("http://s", {"prompt": {}})
                results.append("queued")
            except SystemExit:
                results.append("busy")
        try:
            threads = [threading.Thread(target=run) for _ in range(3)]
            [th.start() for th in threads]
            [th.join() for th in threads]
        finally:
            comfy_guard.requests.get, comfy_guard.requests.post = orig_get, orig_post
        assert results.count("queued") == 1 and state["queued"] == 1, results


def test_render_gate():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        doc = copy.deepcopy(SAMPLE)
        assert render_timeline.export_gate(doc, base, preview=True, allow_reason=None) is False  # preview only warns
        expect_exit(render_timeline.export_gate, doc, base, False, None, contains="export validation failed")
        assert render_timeline.export_gate(doc, base, False, "user asked for a rough cut") is False
        story = base / "story.json"
        story.write_text(json.dumps(doc), encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", str(SKILLS / "ai-director-edit" / "scripts" / "render_timeline.py"), str(story)],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0 and "export validation failed" in r.stderr, r.stderr[-500:]
        assert not (base / "export" / "final.mp4").exists()  # nothing rendered


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
