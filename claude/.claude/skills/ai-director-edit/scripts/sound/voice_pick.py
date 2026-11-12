"""Rank TTS retakes of one line by how calm and clean the delivery is, and build a listening file.

  python voice_pick.py --dir takes/ --current final_dir/ --out export/pick.wav [--keep 2] [--post] [--speaker yeon]

Takes are named <line id>[_<variant>]_<speaker>_<cond>_t<k>.wav; the line key is everything up to and including the
first "_<speaker>" (--speaker, default "yeon" from 「마지막 손님」; set it to the speaking character's id).
The current final for a line is <current>/<line key>.wav (scored as the baseline).
Per take (pyworld F0, voiced frames only):
  spread  pitch standard deviation in semitones (lower = flatter; the user found the up-and-down awkward)
  range   5-95 percentile pitch range in semitones
  rise    pitch of the last 25% of voiced frames minus the median (positive = ends going up, sounds like a question)
  jump    largest frame-to-frame pitch jump in semitones (wobble/crack)
  dur     seconds of audio between the first and last frame above -40 dB
  gap     longest silence inside the line (s); very long = model stalled
Score = spread + 0.5*|rise| + 0.15*jump + penalty when dur is far from the median take of that line (garbled or
cut-off takes) or a gap is longer than 0.9 s. Lower is better. The ranking is a pre-filter; the user listens.
Listening file: for each line, current final, then the kept takes (and with --post the voice_post.py texture pass of
each), separated by 0.8 s of silence, a short 1 kHz tick between lines.
"""
import argparse, glob, os, re, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import voice_post as vp

SR = vp.SR


def stats(x):
    import pyworld as pw
    f0, t = pw.harvest(x, SR, f0_floor=60, f0_ceil=500, frame_period=5.0)
    v = f0 > 0
    db = 20 * np.log10(np.convolve(np.abs(x), np.ones(480) / 480, "same") + 1e-9)
    on = np.where(db > db.max() - 40)[0]
    dur = (on[-1] - on[0]) / SR if len(on) else 0
    quiet = db[on[0]:on[-1]] < db.max() - 40 if len(on) else np.array([])
    gap, run = 0, 0
    for q in quiet:
        run = run + 1 if q else 0; gap = max(gap, run)
    if v.sum() < 10:
        return dict(spread=9, range=9, rise=0, jump=9, dur=dur, gap=gap / SR)
    st = 12 * np.log2(f0[v]); m = np.median(st)
    tail = st[int(len(st) * 0.75):]
    d = np.abs(np.diff(st))
    return dict(spread=float(st.std()), range=float(np.percentile(st, 95) - np.percentile(st, 5)),
                rise=float(np.median(tail) - m), jump=float(np.percentile(d, 99)), dur=dur, gap=gap / SR)


def score(s, med_dur):
    pen = 3 * max(0, abs(s["dur"] - med_dur) / med_dur - 0.35) + (3 if s["gap"] > 0.9 else 0)
    return s["spread"] + 0.5 * abs(s["rise"]) + 0.15 * s["jump"] + pen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--current"); ap.add_argument("--out", required=True)
    ap.add_argument("--keep", type=int, default=2); ap.add_argument("--post", action="store_true")
    ap.add_argument("--speaker", default="yeon", help="speaker tag in the take file names (line key ends with _<speaker>)")
    a = ap.parse_args()
    groups = {}
    for p in sorted(glob.glob(os.path.join(a.dir, "*.wav"))):
        n = os.path.basename(p)
        m = re.match(r"(.+?_" + re.escape(a.speaker) + ")", n)
        if not m or n.startswith("ref_"): continue
        groups.setdefault(m.group(1), []).append(p)
    sil = np.zeros(int(0.8 * SR)); tt = np.arange(int(0.12 * SR)) / SR
    tick = 0.2 * np.sin(2 * np.pi * 1000 * tt) * np.hanning(len(tt))
    seq, report = [], []
    for key, takes in groups.items():
        S = {p: stats(vp.read(p)) for p in takes}
        med = float(np.median([s["dur"] for s in S.values()]))
        ranked = sorted(takes, key=lambda p: score(S[p], med))
        cur = os.path.join(a.current, key + ".wav") if a.current else None
        print(f"\n== {key}")
        if cur and os.path.exists(cur):
            c = stats(vp.read(cur))
            print(f"  current            spread {c['spread']:.2f} range {c['range']:.1f} rise {c['rise']:+.1f} "
                  f"jump {c['jump']:.1f} dur {c['dur']:.2f} score {score(c, med):.2f}")
        for p in ranked:
            s = S[p]
            print(f"  {os.path.basename(p):<34} spread {s['spread']:.2f} range {s['range']:.1f} rise {s['rise']:+.1f} "
                  f"jump {s['jump']:.1f} dur {s['dur']:.2f} gap {s['gap']:.2f} score {score(s, med):.2f}")
        seq += [tick, sil]
        if cur and os.path.exists(cur): seq += [vp.read(cur), sil]; report.append(f"{key}: current")
        for p in ranked[:a.keep]:
            seq += [vp.read(p), sil]; report.append(f"{key}: {os.path.basename(p)}")
            if a.post:
                q = os.path.splitext(p)[0] + "_post.wav"
                subprocess.run([sys.executable, os.path.join(HERE, "voice_post.py"), p, q], check=True,
                               capture_output=True)
                seq += [vp.read(q), sil]; report.append(f"{key}: {os.path.basename(q)}")
    y = np.concatenate(seq); y = y / (np.abs(y).max() + 1e-9) * 10 ** (-3 / 20)
    vp.write(a.out, y)
    with open(os.path.splitext(a.out)[0] + "_order.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\nwrote", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
