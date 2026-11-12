"""Let effect cues ring out instead of being chopped, and soften bed level steps.

  python cue_tails.py in_cues.json out_cues.json [--story stories/<slug>] [--keep-hard 128.40 ...]

--story: folder the cue "src" paths are relative to. Default: in_cues.json's parent's parent (cues live in
<story>/edit/), the same rule as sound_mix.py.

Effects (stem fx): a cue cut from a longer source with a 50 ms fade stops while the sound is still ringing
(detected as an 18 dB drop in 30 ms). For each such cue the end is moved to where the source has decayed
40 dB below the cue's peak, or to just before the next onset in the source (a rise of 10 dB within 30 ms),
at most +1.5 s, with a fade of at least 0.12 s. A cue that uses its whole file but whose file ends loud gets
a fade of 30 % of its length (max 0.8 s). Cues listed in --keep-hard (start times) stay as they are
(intentional hard cuts, e.g. the S4-8 shatter into S4-9 silence).
Beds: gain steps faster than 0.1 s become 0.3 s ramps, except keep-hard times.
Music: a cue whose source ends while still sounding is shortened by 0.3 s so its fade finishes inside the music.
"""
import argparse, json, os, subprocess, sys
import numpy as np

SR = 48000
STORY_DIR = "."                                  # set from --story in main()
_c = {}


def load(p):
    p = p if os.path.isabs(p) else os.path.join(STORY_DIR, p)
    if p not in _c:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                             capture_output=True, check=True).stdout
        _c[p] = np.frombuffer(raw, np.float32)
    return _c[p]


def env_db(x, hop=480):
    n = len(x) // hop
    r = np.sqrt((x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1))
    return 20 * np.log10(r + 1e-9)


def main():
    global STORY_DIR
    ap = argparse.ArgumentParser(description="Let fx cues ring out and soften bed level steps.")
    ap.add_argument("in_cues"); ap.add_argument("out_cues")
    ap.add_argument("--story", help="story folder (default: in_cues' parent's parent)")
    ap.add_argument("--keep-hard", type=float, nargs="*", default=[], help="cue/bed times (s) that stay hard cuts")
    a = ap.parse_args()
    src, dst = a.in_cues, a.out_cues
    STORY_DIR = a.story or os.path.join(os.path.dirname(os.path.abspath(src)), "..")
    hard = a.keep_hard
    is_hard = lambda t: any(abs(t - h) < 0.05 for h in hard)
    cfg = json.load(open(src, encoding="utf8"))
    for c in cfg["cues"]:
        x = load(c["src"]); db = env_db(x)
        i0 = c.get("in", 0); full = len(x) / SR - i0
        d = c.get("dur") or full
        if c.get("stem") == "mus":
            if is_hard(c["at"]): continue
            act = np.where(db[int(i0 * 100): int((i0 + d) * 100)] > db.max() - 35)[0]
            music_end = (act[-1] + 1) / 100 if len(act) else d       # generated pieces stop before the file ends
            if music_end < d - 0.2:
                print(f"{c['at']:7.2f} music {c['src'].split('/')[-1]} plays to {music_end:.2f} of {d:.2f}: fade inside")
                c["dur"] = round(music_end, 3)
            c["fade_out"] = max(c.get("fade_out", 0), 2.5)
            continue
        if is_hard(c["at"]):
            continue
        seg = db[int(i0 * 100): int((i0 + d) * 100)]
        if not len(seg): continue
        peak = seg.max()
        if d < full - 0.05:                                  # cut from a longer source
            k0 = int((i0 + d) * 100); k = k0; kmax = min(len(db) - 4, k0 + 150)
            while k < kmax:
                if db[k] < peak - 40: break
                if db[k + 3] - db[k] > 10: break             # next event in the source
                k += 1
            new = round((k - int(i0 * 100)) / 100, 3)
            if new > d + 0.02:
                print(f"{c['at']:7.2f} {c['src'].split('/')[-1][:44]:<44} dur {d:.2f} -> {new:.2f}")
                c["dur"] = new
            c["fade_out"] = max(c.get("fade_out", 0.05), min(0.12 + 0.25 * (new - d), 0.5), 0.12)
        else:                                                # whole file; soften a loud ending
            if seg[-10:].mean() > peak - 25:
                f = min(0.3 * d, 0.8)
                if f > c.get("fade_out", 0.05):
                    print(f"{c['at']:7.2f} {c['src'].split('/')[-1][:44]:<44} fade {c.get('fade_out', 0.05):.2f} -> {f:.2f}")
                    c["fade_out"] = round(f, 3)
    for b in cfg.get("beds", []):
        g = b.get("gain") or []
        out = []
        for j, (t, v) in enumerate(g):
            if j and t - g[j - 1][0] < 0.1 and abs(v - g[j - 1][1]) > 6 and not is_hard(t) and not is_hard(g[j - 1][0]):
                t0 = out[-1][0]
                if v < out[-1][1]:                   # outgoing place: let it ring 0.8 s past the cut (L-cut)
                    out[-1] = [round(t0, 3), out[-1][1]]; out.append([round(t0 + 0.8, 3), v])
                else:                                # incoming place: arrive just before the cut
                    out[-1] = [round(t0 - 0.12, 3), out[-1][1]]; out.append([round(t0 + 0.05, 3), v])
                print(f"bed {b['src'].split('/')[-1][:30]} step at {t0:.2f} -> {'0.8 s tail' if v < out[-2][1] else 'lead-in'}")
            else:
                out.append([t, v])
        if g: b["gain"] = out
    json.dump(cfg, open(dst, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("wrote", dst)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
