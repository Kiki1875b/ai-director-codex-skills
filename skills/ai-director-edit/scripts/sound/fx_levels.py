"""Set every effect cue's level relative to what is under it (ambience + music) so foley is heard but does not jump.

  python fx_levels.py cues_in.json rendered_prefix cues_out.json [--taper T0 T1 D0 D1 ...]
  (rendered_prefix = <story>/edit/mix/<name>, i.e. the stems <name>_fx/_amb/_mus/_dx.wav of a sound_mix.py render
   of cues_in.json)

For each fx cue: cue level = RMS of the fx stem over the cue's first min(dur, 0.6) s (only this cue sounding),
bed level = RMS of amb + mus over the same window; cue level = its loudest 0.1 s inside the window.
The cue is never raised above (dialogue 99.9th-percentile peak - 6 dB). --taper T0 T1 D0 D1: cues starting between
T0 and T1 s get a target sliding from D0 to D1 dB (distance perspective, e.g. 「마지막 손님」 S5-6 steps walking away:
--taper 163 171 2 -6); repeatable, none by default. Target (cue - bed): contact sounds (cup, marble, switch, step,
splash, drop) +4 dB, soft foley (towel, paper, cloth, tarp, sip, pour, jacket, dishes, tape) +2 dB, designed bead
sounds at most +6 dB (only pulled down). Cues inside an intended silence (no bed under them) keep their level. Change is clamped to
+-20 dB. Overlapping cues are measured together, so their correction is shared.
"""
import argparse, json, os, re, subprocess, sys
import numpy as np

SR = 48000
CONTACT = re.compile(r"mug|cup|marble|switch|footstep|splash|drop|bead_set|dishes", re.I)
SOFT = re.compile(r"towel|paper|sheet|cloth|clothing|plastic|flutter|sip|slurp|pour|water|jacket|tape|shake", re.I)
DESIGN = re.compile(r"bead_", re.I)
TAPER = []                                   # (t0, t1, d0, d1) from --taper


def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def rms_db(x):
    return 20 * np.log10(np.sqrt((x.astype(np.float64) ** 2).mean()) + 1e-9)


def main():
    ap = argparse.ArgumentParser(description="Set fx cue levels relative to the bed under them.")
    ap.add_argument("cues_in"); ap.add_argument("rendered_prefix"); ap.add_argument("cues_out")
    ap.add_argument("--taper", type=float, nargs=4, action="append", default=[], metavar=("T0", "T1", "D0", "D1"),
                    help="target slides from D0 to D1 dB for cues between T0 and T1 s (repeatable)")
    a = ap.parse_args()
    cin, pre, cout = a.cues_in, a.rendered_prefix, a.cues_out
    TAPER[:] = [tuple(t) for t in a.taper]
    cfg = json.load(open(cin, encoding="utf8"))
    fx = load(pre + "_fx.wav"); bed = load(pre + "_amb.wav") + load(pre + "_mus.wav")
    global DX_PEAK
    dx = np.abs(load(pre + "_dx.wav")); DX_PEAK = 20 * np.log10(np.percentile(dx[dx > 1e-4], 99.9) + 1e-9)
    print(f"dialogue peak (99.9 pct) {DX_PEAK:.1f} dBFS")
    for c in sorted(cfg["cues"], key=lambda c: c["at"]):
        if c.get("stem", "fx") != "fx": continue
        name = os.path.basename(c["src"])
        if DESIGN.search(name) and not CONTACT.search(name): target, only_down = 6.0, True
        elif CONTACT.search(name): target, only_down = 4.0, False
        elif SOFT.search(name): target, only_down = 2.0, False
        else: target, only_down = 3.0, False
        w = min(c.get("dur") or 0.6, 0.6)
        a, b = int(c["at"] * SR), int((c["at"] + w) * SR)
        seg = fx[a:b]; k = int(0.1 * SR)
        cue = max(rms_db(seg[i:i + k]) for i in range(0, max(1, len(seg) - k + 1), k // 2))   # loudest 0.1 s = the event
        under = rms_db(bed[a:b])
        for t0, t1, d0, d1 in TAPER:                                  # distance perspective (walking away)
            if t0 <= c["at"] <= t1: target = d0 + (d1 - d0) * (c["at"] - t0) / (t1 - t0)
        if under < -70 or cue < -90: continue                        # inside the intended silence / nothing rendered
        delta = target - (cue - under)
        if only_down: delta = min(0.0, delta)
        delta = float(np.clip(delta, -20, 20))
        pk = 20 * np.log10(np.abs(seg).max() + 1e-9)
        delta = float(min(delta, DX_PEAK - 6 - pk))                  # never peak above dialogue peaks - 6 dB
        if abs(delta) >= 1.0:
            c["db"] = round(c.get("db", 0) + delta, 1)
            print(f"{c['at']:7.2f} {name[:44]:<44} cue-bed {cue - under:+6.1f} dB -> {target:+.0f}  ({delta:+.1f} dB, now {c['db']:+.1f})")
    json.dump(cfg, open(cout, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("wrote", cout)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
