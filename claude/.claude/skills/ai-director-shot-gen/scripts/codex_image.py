"""Generate or edit one image with the local Codex CLI (built-in image_gen tool).

Usage:
  python codex_image.py --prompt-file p.txt --out media/S1-1-key-v1.png \
      [--ref character_image1=refs/ch_mina_front.png --ref env_image1=refs/wd_alley.png] \
      [--transparent] [--timeout 600] [--dry-run]

- Refs are passed to image_gen as referenced_image_paths, in order. A legend line
  ("Reference images: image 1 = character_image1, ...") is prepended so the prompt can
  refer to each image by its label.
- Codex only calls the tool; this script copies the result to --out itself.
- The result must be a PNG that appeared under Codex's generated_images during this run.
  If Codex reports an error, or the result cannot be identified unambiguously, the script
  fails instead of guessing (safe for parallel runs).
- image_gen has no seed or size option. Aspect/framing must be stated in the prompt.
- Uses the user's Codex (ChatGPT) quota. Run only after the approval gate.
Exit code 0 and a JSON line with the output path on success.
"""
import argparse
import atexit
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def gen_dirs():
    homes = [os.environ.get("CODEX_HOME"), str(Path.home() / ".codex")]
    if os.environ.get("APPDATA"):  # orca wraps Codex with its own home
        homes.append(os.path.join(os.environ["APPDATA"], "orca", "codex-runtime-home", "home"))
    seen, out = set(), []
    for h in filter(None, homes):
        d = (Path(h) / "generated_images").resolve()
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


GEN_DIRS = gen_dirs()


def build_instruction(job):
    return (
        "You are a thin wrapper around the image generation tool. Do exactly this and nothing else:\n"
        "1. Call tools.image_gen__imagegen ONCE with the arguments in the JSON below, verbatim. "
        "Do not rewrite, translate, shorten or add to the prompt. "
        "If referenced_image_paths is null, omit it. Do not view, inspect or edit any file.\n"
        "2. Reply with one line: OUTPUT=<absolute path of the generated PNG>. "
        "If the tool fails or refuses, reply with one line: ERROR=<reason>.\n\n"
        "~~~~json\n" + json.dumps(job, ensure_ascii=False, indent=1) + "\n~~~~\n"
    )


def snapshot():
    return {p.resolve() for d in GEN_DIRS if d.exists() for p in d.rglob("*.png")}


def parse_ref(r):
    """'label=path' or a bare path. A bare path that itself contains '=' stays whole."""
    label, sep, path = r.partition("=")
    if not sep or Path(r).exists() or not re.fullmatch(r"[\w-]+", label):
        return "", r
    return label, path


JOBS_DIR = Path(tempfile.gettempdir()) / "codex_image_jobs"


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai-director" / "scripts"))
import file_lock  # noqa: E402
import ledger  # noqa: E402

REG_LOCK = "codex_image_registry"


def job_open():
    """Register this job (pid + process start time) so parallel jobs know their windows overlap."""
    JOBS_DIR.mkdir(exist_ok=True)
    now = time.time()
    pid, ct = file_lock.proc_identity()
    path = JOBS_DIR / f"{pid}_{int(now * 1000)}.json"
    with file_lock.lock(REG_LOCK):
        for f in JOBS_DIR.glob("*.json"):  # forget closed jobs older than a day
            try:
                if now - f.stat().st_mtime > 86400:
                    f.unlink()
            except OSError:
                pass
        _scan(path, now)  # marks jobs that are already dead (dead_at <= our start) so they do not overlap us
        now = time.time()
        file_lock.atomic_write_json(str(path), {"start": now, "end": None, "pid": pid, "create_time": ct})
    return path


def job_close(path, src=None):
    try:
        with file_lock.lock(REG_LOCK):
            d = json.loads(path.read_text(encoding="utf-8"))
            if d.get("end") is None:
                d["end"] = time.time()
            if src and not d.get("claimed"):
                d["claimed"] = str(src)
            file_lock.atomic_write_json(str(path), d)
    except (OSError, ValueError, TimeoutError):
        pass


def path_key(p):
    """One identity per file on Windows: absolute, case- and separator-normalised."""
    return os.path.normcase(os.path.abspath(str(p)))


def _running(d):
    return file_lock.alive(d.get("pid"), d.get("create_time")) or \
        file_lock.alive(d.get("child_pid"), d.get("child_create_time"))


def _scan(path, start):
    """(overlap, claimed keys). Call with REG_LOCK held.
    - unreadable entry -> overlap (never read as 'no other job')
    - open entry whose wrapper and Codex child are both gone -> it is marked dead_at=<first time seen dead>; its
      window counts as open until then, so a job that started before the death was noticed still overlaps it."""
    overlap, claimed = False, set()
    now = time.time()
    for f in JOBS_DIR.glob("*.json"):
        if f == path:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            overlap = True
            continue
        if d.get("claimed"):
            claimed.add(path_key(d["claimed"]))
        end = d.get("end")
        if end is None:
            if _running(d):
                overlap = True
                continue
            if d.get("dead_at") is None:
                d["dead_at"] = now
                with contextlib.suppress(OSError):
                    file_lock.atomic_write_json(str(f), d)
            end = d["dead_at"]
        if end > start:
            overlap = True
    return overlap, claimed


def set_child(path, proc):
    """Record the Codex child so a dead wrapper with a live child still counts as running."""
    pid, ct = file_lock.proc_identity(proc.pid)
    with contextlib.suppress(OSError, ValueError, TimeoutError):
        with file_lock.lock(REG_LOCK):
            d = json.loads(path.read_text(encoding="utf-8"))
            d["child_pid"], d["child_create_time"] = pid, ct
            file_lock.atomic_write_json(str(path), d)


def others(path, start):
    with file_lock.lock(REG_LOCK):
        return _scan(path, start)


def claim(path, start, new, cand):
    """Pick and claim this job's PNG under the registry lock. Returns (src or None, hold_reason or None)."""
    with file_lock.lock(REG_LOCK):
        overlap, claimed = _scan(path, start)
        free = [p for p in new if path_key(p) not in claimed]
        src = None
        if cand is not None:
            if path_key(cand) in claimed:
                return None, f"the returned path {cand} was already claimed by another job"
            match = [p for p in new if path_key(p) == path_key(cand)]
            if match:
                src = match[0]
        if src is None:
            if overlap:
                return None, ("its path was not returned and another codex_image job ran at the same time, so the file "
                              "cannot be attributed safely. Candidates: " + ", ".join(str(p) for p in free[-6:]))
            if len(free) != 1:
                return None, f"cannot identify the generated image ({len(free)} new unclaimed PNGs)"
            src = free[0]
        d = json.loads(path.read_text(encoding="utf-8"))
        d["claimed"], d["end"] = str(src), time.time()
        file_lock.atomic_write_json(str(path), d)
        return src, None


def check_labels(args_ref):
    """Two different images must not share one label (the prompt could not tell them apart)."""
    seen = {}
    for r in args_ref:
        label, path = parse_ref(r)
        if not label:
            continue
        p = str(Path(path).resolve())
        if label in seen and seen[label] != p:
            sys.exit(f"label '{label}' is used for two different images: {seen[label]} and {p}")
        seen[label] = p


def kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt")
    g.add_argument("--prompt-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", action="append", default=[], help="label=path or path (repeatable, max 5 recommended)")
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--dry-run", action="store_true", help="print the Codex instruction only")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    prompt = args.prompt if args.prompt is not None else Path(args.prompt_file).read_text(encoding="utf-8-sig")
    check_labels(args.ref)
    refs, legend = [], []
    for i, r in enumerate(args.ref, 1):
        label, path = parse_ref(r)
        p = Path(path).resolve()
        if not p.exists():
            sys.exit(f"reference not found: {p}")
        refs.append(str(p))
        legend.append(f"image {i} = {label or p.stem}")
    if legend:
        prompt = "Reference images: " + "; ".join(legend) + ".\n" + prompt.strip()

    job = {"prompt": prompt.strip(), "referenced_image_paths": refs or None,
           "transparent_background": bool(args.transparent)}
    instruction = build_instruction(job)
    if args.dry_run:
        print(instruction)
        return

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    codex = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        sys.exit("codex CLI not found on PATH")

    before = snapshot()
    t0 = time.time()
    job = job_open()
    run_id = job.stem
    atexit.register(job_close, job)  # normal exits close the window; crashes are detected by _scan via the pid
    ledger.record(str(out), "gen_submit", tool="codex_image", job_id=run_id, prompt=prompt, inputs=refs)

    def fail(kind, reason):
        job_close(job)
        ledger.record(str(out), kind, tool="codex_image", job_id=run_id, wall_s=round(time.time() - t0, 1), reason=reason[:300])
        sys.exit(reason)

    try:
        run_job(args, codex, instruction, refs, out, job, t0, before, fail, run_id)
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:  # noqa: BLE001 - any other failure must still leave a terminal ledger event
        fail("gen_fail", f"codex_image crashed: {type(e).__name__}: {e}")


def run_job(args, codex, instruction, refs, out, job, t0, before, fail, run_id):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        last = Path(tmp) / "last.txt"
        cmd = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
               "-C", tmp, "-o", str(last), "-"]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, creationflags=flags)
        except OSError as e:
            fail("gen_start_fail", f"could not start codex: {e}")  # nothing was generated or billed
        set_child(job, proc)
        try:
            _, err = proc.communicate(instruction.encode("utf-8"), timeout=args.timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                pass
            fail("gen_timeout", f"codex timed out after {args.timeout}s (process tree killed)")
        except KeyboardInterrupt:
            kill_tree(proc)  # Codex runs in its own process group and would keep spending quota
            job_close(job)
            ledger.record(str(out), "gen_interrupted", tool="codex_image", job_id=run_id, wall_s=round(time.time() - t0, 1))
            raise
        err = (err or b"").decode("utf-8", errors="replace")
        msg = last.read_text(encoding="utf-8", errors="replace").strip() if last.exists() else ""
        if proc.returncode:
            fail("gen_fail", f"codex exited {proc.returncode}: {(err or msg)[-800:]}")

    if "ERROR=" in msg:
        fail("gen_fail", f"image_gen failed: {msg[:500]}")
    new = sorted((p for p in snapshot() - before if str(p) not in refs), key=lambda p: p.stat().st_mtime)
    m = re.search(r"OUTPUT=[`\"']?(.+?\.png)", msg, re.IGNORECASE)
    cand = Path(m.group(1).strip()).resolve() if m else None
    src, hold = claim(job, t0, new, cand)
    if src is None:
        fail("gen_hold", f"HOLD: image generated but {hold}. Do NOT regenerate: open the candidates and copy the right "
                         f"one to {out}. codex said: {msg[:300]}")
    shutil.copyfile(src, out)
    ledger.record(str(out), "gen_done", tool="codex_image", job_id=run_id, wall_s=round(time.time() - t0, 1))
    print(json.dumps({"out": str(out), "source": str(src), "seconds": round(time.time() - t0, 1),
                      "refs": refs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
