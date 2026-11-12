"""Automatic checks of a rendered mix against ai-director-edit/references/sound-rubric.md (the measurable items).

  python sound_audit.py --cues edit/sound_cues_vN.json --stems edit/mix/sound_cues_vN --mix edit/mix/sound_cues_vN_mix.wav
                        [--story stories/<slug>] [--sync audit_sync.json] [--events events.json] [--hard 136.44 ...]
                        [--offscreen cl_vo_... ...] [--skip-shots S1- ...]

--story: story folder or its story.json (only item 6 reads it). Default: the cue file's parent's parent.
--skip-shots: shot-id prefixes whose lines item 6 skips (e.g. a voice-over scene; 「마지막 손님」 used S1-).

Rubric items checked:
  1  effect audibility: loudest 0.1 s of each fx cue vs ambience+music under it. Fail if more than 4 dB under its
     target (contact +4, soft foley +2) or a designed effect more than 4 dB over +6.
  1b effect peaks above (dialogue 99.9th percentile peak - 6 dB).
  3  chops: a sound held for 100 ms that drops 18 dB within 30 ms (fx / amb / mus stems), except --hard times.
  4  ambience changes vs on-screen events (--events: [{"t": 148.7, "what": "curtain opens"}]): an ambience rise of
     6 dB+ within 2 s before the event that starts earlier than 0.3 s before it.
  5  dialogue room: interior lines (not dx_fx.dry_ids) with wet level drier than -14 dB, and the spread of wet levels.
  6  dialogue vs visible mouth: from an audit_sync.py --json file (verdict NO-MATCH, or a visible face >= 100 px whose
     mouth does not move while the line plays and corr < 0.45, or the mouth-voice lag outside -6..+10 frames at 30 fps). If the line plays over another shot than its own, the
     face may be the listener: listed as a manual check. Lines with no face found are listed as manual checks.
     --offscreen ids (deliberate voice-over) are skipped here and in item 5.
  8  loudness of the mix (integrated LUFS, true peak).
Item 2 (sound for an action that is not on screen, material) needs frame strips and is listed as manual.
Prints FAIL lines and a summary count per item.
"""
import argparse, json, os, re, subprocess, sys
import numpy as np

SR = 48000
CONTACT = re.compile(r"mug|cup|marble|switch|footstep|splash|drop|bead_set|dishes", re.I)
SOFT = re.compile(r"towel|paper|sheet|cloth|clothing|plastic|flutter|sip|slurp|pour|water|jacket|tape|shake", re.I)
DESIGN = re.compile(r"bead_", re.I)


def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def rms_db(x): return 20 * np.log10(np.sqrt((x.astype(np.float64) ** 2).mean()) + 1e-9)


def env_db(x, hop=480):
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1)) + 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True); ap.add_argument("--stems", required=True); ap.add_argument("--mix", required=True)
    ap.add_argument("--sync"); ap.add_argument("--events"); ap.add_argument("--hard", type=float, nargs="*", default=[])
    ap.add_argument("--offscreen", nargs="*", default=[], help="dialogue clip ids that are deliberate voice-over (no room, no mouth)")
    ap.add_argument("--story", help="story folder or story.json (default: the cue file's parent's parent)")
    ap.add_argument("--skip-shots", nargs="*", default=[], help="shot-id prefixes whose lines item 6 skips")
    a = ap.parse_args()
    a.story = a.story or os.path.join(os.path.dirname(os.path.abspath(a.cues)), "..")
    if os.path.isdir(a.story): a.story = os.path.join(a.story, "story.json")
    cfg = json.load(open(a.cues, encoding="utf8"))
    fx, amb, mus, dx = (load(f"{a.stems}_{s}.wav") for s in ("fx", "amb", "mus", "dx"))
    bed = amb + mus
    fails = {k: [] for k in ("1", "1b", "3", "4", "5", "6", "8")}; manual6 = []
    dxa = np.abs(dx); dx_pk = 20 * np.log10(np.percentile(dxa[dxa > 1e-4], 99.9) + 1e-9)
    hard = lambda t: any(abs(t - h) < 0.3 for h in a.hard)

    # 1 / 1b
    for c in sorted(cfg["cues"], key=lambda c: c["at"]):
        if c.get("stem", "fx") != "fx": continue
        name = os.path.basename(c["src"])
        if DESIGN.search(name) and not CONTACT.search(name): target, kind = 6.0, "design"
        elif CONTACT.search(name): target, kind = 4.0, "contact"
        elif SOFT.search(name): target, kind = 2.0, "soft"
        else: target, kind = 3.0, "other"
        w = min(c.get("dur") or 1.2, 1.2)
        s0, s1 = int(c["at"] * SR), int((c["at"] + w) * SR); seg = fx[s0:s1]; k = int(0.1 * SR)
        if len(seg) < k: continue
        ev = max(rms_db(seg[i:i + k]) for i in range(0, len(seg) - k + 1, k // 2)); under = rms_db(bed[s0:s1])
        if under < -70: continue
        d = ev - under
        if (kind != "design" and d < target - 4) or (kind == "design" and d > target + 4):
            fails["1"].append(f"{c['at']:7.2f} {name[:40]:<40} {kind:7} event-over-bed {d:+6.1f} dB (target {target:+.0f})")
        pk = 20 * np.log10(np.abs(seg).max() + 1e-9)
        if pk > dx_pk - 6 + 1:
            fails["1b"].append(f"{c['at']:7.2f} {name[:40]:<40} peak {pk:+.1f} dBFS > dialogue peak {dx_pk:+.1f} - 6")

    # 3 chops
    for nm, x in (("fx", fx), ("amb", amb), ("mus", mus)):
        db = env_db(x); last = -9
        for i in range(10, len(db) - 3):
            pre = db[i - 10:i]
            if pre.mean() > -50 and pre.std() < 3 and pre.mean() - db[i + 3] >= 18 and i / 100 - last > 0.5:
                last = i / 100
                if not hard(i / 100): fails["3"].append(f"{i / 100:7.2f} {nm} held {pre.mean():.0f} dB -> {db[i + 3]:.0f} dB in 30 ms")

    # 4 ambience vs events
    if a.events:
        adb = env_db(amb, 4800)                                    # 0.1 s frames
        for e in json.load(open(a.events, encoding="utf8")):
            t = e["t"]; i0 = int((t - 2.0) * 10); i1 = int(t * 10)
            win = adb[i0:i1 + 1]; base = adb[max(0, i0 - 10):i0].mean()
            rise = np.where(win > base + 6)[0]
            if len(rise) and (i0 + rise[0]) / 10 < t - 0.3:
                fails["4"].append(f"{t:7.2f} {e['what']}: ambience already +6 dB at {(i0 + rise[0]) / 10:.2f} s ({t - (i0 + rise[0]) / 10:.1f} s early)")

    # 5 dialogue room
    fxcfg = cfg.get("dx_fx") or {}; dry = set(fxcfg.get("dry_ids", [])); base = fxcfg.get("params", {})
    wets = {}
    for cid, p in fxcfg.get("lines", {}).items():
        if cid in dry or cid in a.offscreen: continue
        wets[cid] = p.get("wet_db", base.get("wet_db", -13))
        if wets[cid] < -14: fails["5"].append(f"{cid:<16} wet {wets[cid]} dB: drier than -14 (sounds like a booth, apart from the room)")
    if wets:
        spread = max(wets.values()) - min(wets.values())
        print(f"[5] interior dialogue wet levels {min(wets.values())}..{max(wets.values())} dB (spread {spread})")

    # 6 mouth
    if a.sync:
        story = json.load(open(a.story, encoding="utf8"))
        shots = [(c["shot_id"], c["timeline_start_ms"] / 1000, (c["timeline_start_ms"] + c["source_out_ms"] - c["source_in_ms"]) / 1000)
                 for c in story["timeline"]["clips"] if c["kind"] == "shot" and c.get("enabled", True)]
        for r in json.load(open(a.sync, encoding="utf8")):
            own = r["id"].replace("cl_vo_", "").rsplit("_", 1)[0]          # the shot the line was written for
            mid = (r["start"] + r["end"]) / 2
            under = [sid for sid, s0, s1 in shots if s0 <= mid < s1]
            if any(own.startswith(p) for p in a.skip_shots) or r["id"] in fxcfg.get("dry_ids", []) or r["id"] in a.offscreen: continue
            if "corr" not in r:
                manual6.append(f"{r['id']:<16} {r['start']:.1f}-{r['end']:.1f}: no face found over {under} - check by eye"); continue
            closed = r.get("width", 0) >= 100 and r.get("act_speak", 1) < 0.004 and r["corr"] < 0.45
            late = r.get("width", 0) >= 100 and r["corr"] >= 0.45 and not (-6 <= r.get("lag", 0) <= 10)   # mouth and voice apart (S6-3 -5 judged right by the user)
            if r["verdict"] == "NO-MATCH" or closed or late:
                line = (f"{r['id']:<16} {r['start']:.1f}-{r['end']:.1f} over {under}: face {r.get('width')} px, mouth "
                        f"sd {r.get('act_speak')} speaking / {r.get('act_quiet')} silent, corr {r.get('corr')}")
                if under and under[0] != own: manual6.append(line + " - line belongs to " + own + "; is the visible face the listener?")
                else: fails["6"].append(line)

    # 8 loudness
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", a.mix, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    tail = out[out.rfind("Summary:"):]
    I = float(next(l.split()[1] for l in tail.splitlines() if l.strip().startswith("I:")))
    P = float(next(l.split()[1] for l in tail.splitlines() if l.strip().startswith("Peak:")))
    if I < -16 or I > -12 or P > -1: fails["8"].append(f"integrated {I} LUFS, true peak {P} dBTP (target -14 / <= -1)")
    print(f"[8] {I} LUFS, {P} dBTP")

    names = {"1": "effects audible", "1b": "effect peaks", "3": "chops", "4": "ambience vs events", "5": "dialogue room",
             "6": "dialogue vs mouth", "8": "loudness"}
    for k, v in fails.items():
        print(f"\n[{k}] {names[k]}: {'PASS' if not v else f'{len(v)} FAIL'}")
        for l in v: print("   ", l)
    print("\n[6] manual checks:")
    for l in manual6: print("   ", l)
    print("\n[2] sound for actions not on screen / material: manual (frame strips)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
