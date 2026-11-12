"""Cost ledger for AI film work: one append-only JSONL file per story (stories/<slug>/ledger.jsonl).

Generation scripts call record() automatically (ltx_remote.py, wan_remote.py, codex_image.py), so nobody fills
fields by hand. Review counts come from the review files the reviewer agents already write.

Usage:
  python ledger.py summary stories/<slug> [--shot S1-3] [--since 2026-11-10]
  python ledger.py tail stories/<slug> [-n 20]
  python ledger.py user stories/<slug> --shot S1-3 --verdict reject|taste|change|accept [--target <version or file>] [--note ...]
  python ledger.py pass stories/<slug> --shot S1-3 [--version <vid>] [--range IN_MS OUT_MS] [--activate] [--note ...]
  python ledger.py cut-pass stories/<slug> (--all | --pair cl_A cl_B ...) [--note ...]

pass / cut-pass: the user watched it and passed it. They write the export review record that validate_story.py
--stage export checks (version.review with media_sha1, range_ms, scope playback, reviewer/playback_by user, criteria;
timeline.edit_point_reviews for the current cut) and log an accept. A later change of the file, the used range, speed
or transition makes the validator ask for a new pass. Use them only after the user's own playback verdict.

User verdicts are recorded by the agent right after the user judges a shot, so the user types nothing extra:
  reject = a defect the user had to point out, taste = the user chose between acceptable options,
  change = the user changed the requirement (not a defect), accept = the user accepted the shot.

Event fields (all optional except ts/kind): ts, kind (gen_submit|gen_done|gen_fail|gen_timeout|gen_hold|gen_interrupted|user_verdict|render|render_blocked), tool, out, shot, seed,
job_id, wall_s (client wait incl. queue), exec_s (server execution from ComfyUI history), inputs [{path, sha256}],
prompt_sha256, settings {...}.
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

SHOT_RE = re.compile(r"(S\d+-\d+[A-Za-z]*)")


def _story_root(path):
    """Walk up from an output path to the folder holding story.json (stories/<slug>)."""
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(8):
        if os.path.isfile(os.path.join(d, "story.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def shot_from(path):
    m = SHOT_RE.search(os.path.basename(path or ""))
    return m.group(1) if m else None


def record(out, kind, **fields):
    """Append one event for the story that contains `out`. Never raises: a ledger problem must not stop a job."""
    try:
        root = _story_root(out)
        if not root:
            return
        ev = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "kind": kind,
              "out": os.path.relpath(os.path.abspath(out), root).replace(os.sep, "/"),
              "shot": fields.pop("shot", None) or shot_from(out)}
        if "inputs" in fields:
            ev["inputs"] = [{"path": p, "sha256": sha256_file(p)} for p in fields.pop("inputs") if p]
        if "prompt" in fields:
            pr = fields.pop("prompt") or ""
            ev["prompt_sha256"] = hashlib.sha256(pr.encode("utf-8")).hexdigest()
        ev.update({k: v for k, v in fields.items() if v is not None})
        with open(os.path.join(root, "ledger.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[ledger] not recorded: {e}", file=sys.stderr)


def exec_seconds(history_entry):
    """Server-side execution time from ComfyUI history status messages (execution_start -> success/error)."""
    try:
        msgs = history_entry.get("status", {}).get("messages", [])
        start = next(m[1]["timestamp"] for m in msgs if m[0] == "execution_start")
        end = next(m[1]["timestamp"] for m in msgs if m[0] in ("execution_success", "execution_error", "execution_interrupted"))
        return round((end - start) / 1000.0, 1)
    except Exception:  # noqa: BLE001
        return None


def _load(root):
    p = os.path.join(root, "ledger.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


VERDICTS = ("reject", "taste", "change", "accept")


def user_verdict(root, shot, verdict, target=None, note=None):
    if verdict not in VERDICTS:
        sys.exit(f"verdict must be one of {VERDICTS}")
    if not os.path.isfile(os.path.join(root, "story.json")):
        sys.exit(f"{root} has no story.json")
    ev = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "kind": "user_verdict", "shot": shot,
          "verdict": verdict}
    if target:
        ev["target"] = target
    if note:
        ev["note"] = note
    with open(os.path.join(root, "ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(json.dumps(ev, ensure_ascii=False))


def _reviews(root, since):
    """Count review files per shot (reviewer agents write reviews/*.md or media/*review*.md)."""
    files = glob.glob(os.path.join(root, "reviews", "*.md")) + glob.glob(os.path.join(root, "media", "**", "*review*.md"), recursive=True)
    per = {}
    for f in files:
        mt = dt.datetime.fromtimestamp(os.path.getmtime(f))
        if since and mt < since:
            continue
        s = shot_from(f) or "?"
        per[s] = per.get(s, 0) + 1
    return per


def _accepted(root):
    try:
        s = json.load(open(os.path.join(root, "story.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    acc = {}
    for sc in s.get("scenes", []):
        for sh in sc.get("shots", []):
            act = sh.get("active_version_id")
            v = next((v for v in sh.get("versions", []) if v.get("id") == act), None)
            r = (v or {}).get("review") or {}
            acc[sh.get("id")] = {"active": act, "review": r.get("status"), "by": r.get("by")}
    return acc


TERMINAL_FAIL = ("gen_fail", "gen_timeout", "gen_hold", "gen_interrupted", "gen_fetch_fail")
# gen_start_fail = the tool never started (nothing generated or billed): not counted as a job


def _jobs(evs):
    """Fold events into one record per job (job_id, else out+ts), so re-fetching a job never counts twice."""
    jobs = {}
    for e in evs:
        if not e["kind"].startswith("gen_"):
            continue
        key = e.get("job_id") or f"{e.get('out')}@{e['ts']}"
        j = jobs.setdefault(key, {"shot": e.get("shot") or "?", "tool": e.get("tool"), "first": e["ts"],
                                  "state": "open", "exec_s": None, "wall_s": None})
        if e["kind"] == "gen_submit" and e.get("tool"):
            j["tool"] = e["tool"]  # the submitter, not the shared fetch helper, owns the job
        j["first"] = min(j["first"], e["ts"])
        if e["kind"] == "gen_done":
            j["state"] = "done"
        elif e["kind"] in TERMINAL_FAIL and j["state"] != "done":
            j["state"] = e["kind"][4:]
        elif e["kind"] == "gen_start_fail" and j["state"] == "open":
            j["state"] = "start_fail"
        for k in ("exec_s", "wall_s"):
            if e.get(k) is not None:
                j[k] = max(j[k] or 0, e[k])
    return jobs


def summary(root, shot=None, since=None):
    evs = [e for e in _load(root) if (not since or dt.datetime.fromisoformat(e["ts"]) >= since)]
    rev = _reviews(root, since)
    acc = _accepted(root)
    rows = {}

    def row(s):
        return rows.setdefault(s, {"done": 0, "fail": 0, "open": 0, "gpu_ok": 0.0, "gpu_fail": 0.0, "wait": 0.0,
                                   "unmeasured": 0, "reject": 0, "taste": 0, "change": 0, "first": None, "accepted": None})

    for j in _jobs(evs).values():
        if j["state"] == "start_fail":
            continue
        r = row(j["shot"])
        ts = dt.datetime.fromisoformat(j["first"])
        r["first"] = ts if r["first"] is None else min(r["first"], ts)
        if j["state"] == "done":
            r["done"] += 1
        elif j["state"] == "open":
            r["open"] += 1
        else:
            r["fail"] += 1
        if j["exec_s"] is not None:
            r["gpu_ok" if j["state"] == "done" else "gpu_fail"] += j["exec_s"]
        elif j["tool"] != "codex_image" and j["state"] != "open":
            r["unmeasured"] += 1  # a ComfyUI job without server timing: unknown, not zero
        r["wait"] += j["wall_s"] or 0
    for e in evs:
        if e["kind"] == "user_verdict":
            r = row(e.get("shot") or "?")
            v = e.get("verdict")
            if v in ("reject", "taste", "change"):
                r[v] += 1
            elif v == "accept":
                r["accepted"] = dt.datetime.fromisoformat(e["ts"])
    shots = sorted(set(rows) | set(rev))
    if shot:
        shots = [s for s in shots if s == shot]
    hdr = (f"{'shot':<9}{'ok':>4}{'fail':>5}{'open':>5}{'GPU ok':>8}{'GPU fail':>9}{'wait':>7}{'n/m':>4}{'rev files':>10}"
           f"{'reject':>7}{'taste':>6}{'change':>7}{'to accept h':>12}  active / review")
    print(hdr)
    keys = ("done", "fail", "open", "gpu_ok", "gpu_fail", "wait", "unmeasured", "reject", "taste", "change")
    tot = dict.fromkeys(keys, 0)
    tot["rev"] = 0
    hours = []
    for s in shots:
        r = rows.get(s) or row(s)
        a = acc.get(s, {})
        h = "-"
        if r["first"] and r["accepted"] and r["accepted"] >= r["first"]:
            hv = (r["accepted"] - r["first"]).total_seconds() / 3600
            hours.append(hv)
            h = f"{hv:.1f}"
        print(f"{s:<9}{r['done']:>4}{r['fail']:>5}{r['open']:>5}{r['gpu_ok']/60:>8.1f}{r['gpu_fail']/60:>9.1f}"
              f"{r['wait']/60:>7.1f}{r['unmeasured']:>4}{rev.get(s, 0):>10}{r['reject']:>7}{r['taste']:>6}{r['change']:>7}{h:>12}  "
              f"{a.get('active') or '-'} / {a.get('review') or '-'}{'(' + a['by'] + ')' if a.get('by') else ''}")
        for k in keys:
            tot[k] += r[k]
        tot["rev"] += rev.get(s, 0)
    med = f"{sorted(hours)[len(hours) // 2]:.1f}" if hours else "-"
    print(f"{'TOTAL':<9}{tot['done']:>4}{tot['fail']:>5}{tot['open']:>5}{tot['gpu_ok']/60:>8.1f}{tot['gpu_fail']/60:>9.1f}"
          f"{tot['wait']/60:>7.1f}{tot['unmeasured']:>4}{tot['rev']:>10}{tot['reject']:>7}{tot['taste']:>6}{tot['change']:>7}"
          f"{'med ' + med:>12}")
    print("ok/fail/open = jobs (one per server job; re-fetches are not new jobs). fail includes timeout, hold, interrupted and")
    print("  fetch_fail (server finished but the download/encode failed; a later --fetch turns it into ok, counted once).")
    print("GPU ok / GPU fail = server execution minutes (ComfyUI history) of successful / failed jobs; n/m = ComfyUI jobs")
    print("  without server timing (unknown, not zero). wait = client minutes incl. queue; codex_image time is only here.")
    print("reject = defects the user had to point out (drive this down); change = requirement changes, not defects.")
    print("to accept h = first generation of the shot -> last user accept, wall-clock hours incl. waiting for the user;")
    print("  a later requirement change is not split out yet. rev files = review files on disk, not reviewer calls.")
    print("Events before this ledger existed are not included; pass --since to limit review files to the same period.")


# ---- the user's playback verdict as the official review record (export gate) ----------------------------------
# The user is the final reviewer at every stage. These commands write the record validate_story.py --stage export
# checks, computed with the validator's own helpers so the stored values match what it compares.

def _story(root):
    p = os.path.join(root, "story.json")
    if not os.path.isfile(p):
        sys.exit(f"{root} has no story.json")
    return p, json.load(open(p, encoding="utf-8"))


def _save_story(path, doc):
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(os.path.dirname(path), f"story.bak_{stamp}_review.json")
    with open(path, encoding="utf-8") as f, open(bak, "w", encoding="utf-8") as g:
        g.write(f.read())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("story.json saved (backup", os.path.basename(bak) + ")")


def _vs():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import validate_story
    return validate_story


def _find_shot(doc, shot_id):
    for sc in doc.get("scenes", []):
        for sh in sc.get("shots", []):
            if sh.get("id") == shot_id:
                return sh
    sys.exit(f"shot {shot_id} not found")


def user_pass(root, shot_id, version=None, rng=None, activate=False, note=None):
    """Record the user's playback pass of one shot version: ledger accept + version.review (export record)."""
    vs = _vs()
    path, doc = _story(root)
    shot = _find_shot(doc, shot_id)
    vid = version or shot.get("active_version_id")
    ver = next((v for v in shot.get("versions", []) if v.get("id") == vid), None)
    if not ver or not ver.get("media_url"):
        sys.exit(f"{shot_id}: version {vid} not found or has no media_url")
    media = vs.local_path(ver["media_url"], root)
    if not media or not media.is_file():
        sys.exit(f"{shot_id}: media file not found: {ver['media_url']}")
    clips = [c for c in doc.get("timeline", {}).get("clips", []) if c.get("shot_id") == shot_id and c.get("enabled", True)]
    if rng:
        rng = [int(rng[0]), int(rng[1])]
    elif clips:
        rng = [min(int(c.get("source_in_ms", 0)) for c in clips), max(int(c.get("source_out_ms", 0)) for c in clips)]
    else:
        dur = vs.probe_duration_ms(media)
        rng = [0, int(dur)] if dur else None
    if not rng or rng[0] >= rng[1]:
        sys.exit(f"{shot_id}: give --range IN OUT (ms)")
    crit = {k: "met" for k, v in (shot.get("success_criteria") or {}).items() if v} or {"user_playback": "met"}
    old = ver.get("review")
    if old:
        ver.setdefault("review_history", []).append(old)
    ver["review"] = {"status": "pass", "media_sha1": vs.sha1_of(media), "range_ms": rng, "scope": ["playback"],
                     "reviewer": "user", "playback_by": "user", "date": dt.date.today().isoformat(),
                     "criteria": crit, **({"note": note} if note else {})}
    if activate:
        shot["active_version_id"] = vid
        for c in clips:
            c["version_id"], c["media_url"] = vid, ver["media_url"]
    _save_story(path, doc)
    user_verdict(root, shot_id, "accept", vid, note or "user playback pass (export record)")
    print(f"{shot_id} {vid}: pass, range {rng} ms, criteria {list(crit)}" + (" (activated)" if activate else ""))


def user_cut_pass(root, pairs=None, note=None):
    """Record the user's playback pass of edit points on the current cut. pairs = [(clip_a, clip_b)] or None = all."""
    vs = _vs()
    path, doc = _story(root)
    main_id = vs.main_video_track_id(doc)
    tl = doc.setdefault("timeline", {})
    main = sorted((c for c in tl.get("clips", []) if c.get("track_id") == main_id and c.get("enabled", True)
                   and c.get("media_kind") == "video" and "timeline_start_ms" in c), key=lambda c: c["timeline_start_ms"])
    shas = {}

    def side(c):
        p = vs.local_path(c.get("media_url", ""), root)
        if not p or not p.is_file():
            sys.exit(f"clip {c['id']}: media file not found: {c.get('media_url')}")
        if p not in shas:
            shas[p] = vs.sha1_of(p)
        return {"clip_id": c["id"], "version_id": c.get("version_id"), "media_sha1": shas[p],
                "source_in_ms": c.get("source_in_ms"), "source_out_ms": c.get("source_out_ms"), "speed": c.get("speed", 1) or 1}

    def trans(t):
        return {"type": t.get("type"), "duration_ms": t.get("duration_ms")} if isinstance(t, dict) and t else None

    want = set(map(tuple, pairs)) if pairs else None
    recs = [r for r in tl.get("edit_point_reviews", []) if isinstance(r, dict)]
    done = []
    for prev, cur in zip(main, main[1:]):
        if want is not None and (prev["id"], cur["id"]) not in want:
            continue
        recs = [r for r in recs if not ((r.get("a") or {}).get("clip_id") == prev["id"] and (r.get("b") or {}).get("clip_id") == cur["id"])]
        recs.append({"a": side(prev), "b": side(cur), "transition": trans(cur.get("transition_in")), "status": "pass",
                     "reviewer": "user", "playback_by": "user", "date": dt.date.today().isoformat(),
                     **({"note": note} if note else {})})
        done.append(f"{prev['id']}→{cur['id']}")
    if want is not None and len(done) != len(want):
        sys.exit(f"not adjacent on the main track: {sorted(want - {tuple(d.split('→')) for d in done})}")
    tl["edit_point_reviews"] = recs
    _save_story(path, doc)
    user_verdict(root, "cut", "accept", ", ".join(done), note or "user playback pass of edit points (export record)")
    print("edit points passed:", ", ".join(done))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary"); s.add_argument("story"); s.add_argument("--shot"); s.add_argument("--since")
    t = sub.add_parser("tail"); t.add_argument("story"); t.add_argument("-n", type=int, default=20)
    u = sub.add_parser("user"); u.add_argument("story"); u.add_argument("--shot", required=True)
    u.add_argument("--verdict", required=True, choices=VERDICTS); u.add_argument("--target"); u.add_argument("--note")
    p = sub.add_parser("pass", help="user's playback pass of a shot version -> ledger accept + export review record")
    p.add_argument("story"); p.add_argument("--shot", required=True); p.add_argument("--version")
    p.add_argument("--range", nargs=2, type=int, metavar=("IN_MS", "OUT_MS")); p.add_argument("--activate", action="store_true")
    p.add_argument("--note")
    cp = sub.add_parser("cut-pass", help="user's playback pass of edit points on the current cut")
    cp.add_argument("story"); cp.add_argument("--pair", nargs=2, action="append", metavar=("CLIP_A", "CLIP_B"))
    cp.add_argument("--all", action="store_true"); cp.add_argument("--note")
    a = ap.parse_args()
    if a.cmd == "pass":
        user_pass(a.story, a.shot, a.version, a.range, a.activate, a.note)
    elif a.cmd == "cut-pass":
        if not (a.all or a.pair):
            sys.exit("give --all or --pair CLIP_A CLIP_B")
        user_cut_pass(a.story, None if a.all else a.pair, a.note)
    elif a.cmd == "user":
        user_verdict(a.story, a.shot, a.verdict, a.target, a.note)
    elif a.cmd == "summary":
        since = dt.datetime.fromisoformat(a.since) if a.since else None
        summary(a.story, a.shot, since)
    else:
        for e in _load(a.story)[-a.n:]:
            print(json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()
