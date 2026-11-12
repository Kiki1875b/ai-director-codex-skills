"""Regression tests for review round 2 (IMB-1..4): real multi-process locking, dead jobs, path identity,
terminal ledger events on fetch/copy failures. Offline: no GPU, no network, no Codex.
Run: python tests/test_gates_b.py  (from ai-director-shot-gen/scripts)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
AID = SCRIPTS.parents[1] / "ai-director" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(AID))
import file_lock  # noqa: E402
import ledger  # noqa: E402
import codex_image  # noqa: E402
import ltx_remote  # noqa: E402

WORKER = r'''
import sys, time, os
sys.path.insert(0, sys.argv[1])
import file_lock
file_lock.LOCK_DIR = sys.argv[2]
log, n, hold = sys.argv[3], int(sys.argv[4]), float(sys.argv[5])
for _ in range(n):
    with file_lock.lock("race", timeout=60):
        with open(log, "a") as f: f.write(f"+{os.getpid()}\n")
        time.sleep(hold)
        with open(log, "a") as f: f.write(f"-{os.getpid()}\n")
'''

HOLDER = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
import file_lock
file_lock.LOCK_DIR = sys.argv[2]
with file_lock.lock("race"):
    open(sys.argv[3], "w").write("held")
    time.sleep(60)
'''


def test_lock_mutual_exclusion_across_processes():
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "log.txt")
        worker = os.path.join(tmp, "w.py")
        Path(worker).write_text(WORKER, encoding="utf-8")
        procs = [subprocess.Popen([sys.executable, "-B", worker, str(AID), tmp, log, "15", "0.01"]) for _ in range(4)]
        for p in procs:
            assert p.wait(timeout=120) == 0
        inside, max_inside = 0, 0
        for line in Path(log).read_text().split():
            inside += 1 if line[0] == "+" else -1
            max_inside = max(max_inside, inside)
        assert max_inside == 1, max_inside
        assert len(Path(log).read_text().split()) == 4 * 15 * 2


def test_killed_holder_releases_lock():
    with tempfile.TemporaryDirectory() as tmp:
        holder = os.path.join(tmp, "h.py")
        flag = os.path.join(tmp, "flag")
        Path(holder).write_text(HOLDER, encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-B", holder, str(AID), tmp, flag])
        for _ in range(100):
            if os.path.exists(flag):
                break
            time.sleep(0.1)
        old = file_lock.LOCK_DIR
        file_lock.LOCK_DIR = tmp
        try:
            try:
                with file_lock.lock("race", timeout=0.5):
                    raise AssertionError("got the lock while a live process holds it")
            except TimeoutError:
                pass
            p.kill()
            p.wait(timeout=30)
            t0 = time.time()
            with file_lock.lock("race", timeout=10):
                pass
            assert time.time() - t0 < 10
        finally:
            file_lock.LOCK_DIR = old
            if p.poll() is None:
                p.kill()


class TempJobs:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (codex_image.JOBS_DIR, file_lock.LOCK_DIR)
        codex_image.JOBS_DIR = Path(self.tmp.name) / "jobs"
        file_lock.LOCK_DIR = str(Path(self.tmp.name) / "locks")
        return Path(self.tmp.name)

    def __exit__(self, *a):
        codex_image.JOBS_DIR, file_lock.LOCK_DIR = self.orig
        self.tmp.cleanup()


def _set(path, **kw):
    d = json.loads(path.read_text(encoding="utf-8"))
    d.update(kw)
    path.write_text(json.dumps(d), encoding="utf-8")


def test_job_that_dies_during_my_run_still_overlaps():
    with TempJobs():
        earlier = codex_image.job_open()
        time.sleep(0.01)
        mine = codex_image.job_open()
        t_mine = time.time()
        assert codex_image.others(mine, t_mine - 0.005)[0] is True  # earlier is alive (it is this process)
        _set(earlier, pid=4000001, create_time=1.0)  # earlier crashes after producing a PNG
        src, hold = codex_image.claim(mine, t_mine - 0.005, [Path("C:/gen/earlier_result.png")], None)
        assert src is None and hold, (src, hold)  # never take it
        time.sleep(0.02)
        later = codex_image.job_open()
        assert codex_image.others(later, time.time())[0] is True  # mine is still open and alive
        _set(mine, end=time.time() - 1)
        # earlier died before 'later' started and mine has ended: a job started after the death is not blocked
        assert codex_image.others(later, time.time())[0] is False


def test_live_child_keeps_dead_wrapper_running():
    with TempJobs():
        other = codex_image.job_open()
        pid, ct = file_lock.proc_identity()
        _set(other, pid=4000002, create_time=1.0, child_pid=pid, child_create_time=ct)
        mine = codex_image.job_open()
        assert codex_image.others(mine, time.time())[0] is True


def test_same_png_with_different_case_is_claimed_once():
    with TempJobs():
        j1, j2 = codex_image.job_open(), codex_image.job_open()
        t = time.time()
        new = [Path("C:/gen/face.png")]
        r1 = codex_image.claim(j1, t, new, Path("C:/gen/face.png"))
        r2 = codex_image.claim(j2, t, new, Path("C:/GEN/FACE.PNG"))
        assert sum(1 for s, _ in (r1, r2) if s is not None) == 1, (r1, r2)


def _story(tmp):
    root = Path(tmp) / "stories" / "demo"
    (root / "media" / "video").mkdir(parents=True)
    (root / "story.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    return root


class R:
    def __init__(self, data=None, content=b"", fail=False):
        self.data, self.content, self.fail = data, content, fail

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.fail:
            raise ltx_remote.requests.HTTPError("503")


def test_fetch_failure_keeps_server_time_and_refetch_counts_once():
    with tempfile.TemporaryDirectory() as tmp:
        root = _story(tmp)
        out = str(root / "media" / "video" / "S1-1-ltx-v1.mp4")
        hist = {"J": {"status": {"status_str": "success", "messages": [["execution_start", {"timestamp": 0}],
                                                                         ["execution_success", {"timestamp": 60000}]]},
                      "outputs": {"41": {"videos": [{"filename": "a.mp4"}]}}}}
        orig = ltx_remote.requests.get
        try:
            ltx_remote.requests.get = lambda url, **k: R(hist) if "/history/" in url else R(fail=True)
            ledger.record(out, "gen_submit", tool="ltx_remote", job_id="J")
            try:
                ltx_remote.wait_and_fetch("http://s", "J", out, 60)
                raise AssertionError("expected exit")
            except SystemExit as e:
                assert "--fetch J" in str(e)
            ltx_remote.requests.get = lambda url, **k: R(hist) if "/history/" in url else R(content=b"mp4")
            with redirect_stdout(io.StringIO()):
                ltx_remote.wait_and_fetch("http://s", "J", out, 60)
        finally:
            ltx_remote.requests.get = orig
        kinds = [json.loads(l)["kind"] for l in (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        assert kinds == ["gen_submit", "gen_fetch_fail", "gen_done"], kinds
        buf = io.StringIO()
        with redirect_stdout(buf):
            ledger.summary(str(root))
        c = next(l for l in buf.getvalue().splitlines() if l.startswith("S1-1")).split()
        assert c[1:6] == ["1", "0", "0", "1.0", "0.0"], c  # one job, one minute


def test_codex_copy_error_leaves_terminal_event():
    with tempfile.TemporaryDirectory() as tmp, TempJobs():
        root = _story(tmp)
        out = root / "media" / "S2-1-key-v1.png"
        png = Path(tmp) / "gen" / "x.png"
        png.parent.mkdir()
        png.write_bytes(b"png")

        class FakeProc:
            pid, returncode = os.getpid(), 0

            def __init__(self, cmd, **k):
                Path(cmd[cmd.index("-o") + 1]).write_text(f"OUTPUT={png}", encoding="utf-8")

            def communicate(self, *a, **k):
                return b"", b""
        snaps = iter([set(), {png.resolve()}])
        saved = (codex_image.subprocess.Popen, codex_image.shutil.which, codex_image.snapshot, codex_image.shutil.copyfile,
                 sys.argv)
        try:
            codex_image.subprocess.Popen = FakeProc
            codex_image.shutil.which = lambda n: "codex"
            codex_image.snapshot = lambda: next(snaps)

            def boom(*a, **k):
                raise PermissionError("locked")
            codex_image.shutil.copyfile = boom
            sys.argv = ["codex_image.py", "--prompt", "p", "--out", str(out)]
            try:
                codex_image.main()
                raise AssertionError("expected exit")
            except SystemExit as e:
                assert "PermissionError" in str(e), str(e)
        finally:
            (codex_image.subprocess.Popen, codex_image.shutil.which, codex_image.snapshot, codex_image.shutil.copyfile,
             sys.argv) = saved
        kinds = [json.loads(l)["kind"] for l in (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        assert kinds == ["gen_submit", "gen_fail"], kinds


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
