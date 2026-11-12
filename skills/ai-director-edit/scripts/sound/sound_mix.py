"""Render the film's sound from a cue sheet: ambience beds, effects, bead cues and dialogue -> stems + stereo mix.

  python sound_mix.py cues.json [--story stories/<slug>] [--outdir DIR] [--video export/x.mp4 --out export/x_sound.mp4]

--story: the story folder (holds story.json); every relative path (cue/bed src, dialogue media_url, --video, --out)
  is resolved against it. Default: the cue file's parent's parent (cues normally live in <story>/edit/).
--outdir: where the stems and mix go. Default: <story>/edit/mix.

cues.json:
  {"duration": 200.9,
   "beds":  [{"src": "...wav", "stem": "amb", "gain": [[t, dB], ...], "lp": [[t, Hz], ...], "offset": 0}],
   "cues":  [{"src": "...wav", "at": 12.3, "in": 0.0, "dur": 1.2, "db": -6, "pan": 0.0,
              "fade_in": 0.01, "fade_out": 0.1, "stem": "fx", "lp": 0}],
   "duck":  {"stems": ["amb", "fx"], "db": -9, "attack": 0.15, "release": 0.4},   # or a list of such rules
   "limit_db": 3.0}                      # most the final limiter may take off the loudest peak (default 3 dB)
Dialogue clips are read from story.json (track tr_vo) unless "dialogue": false.
Beds loop their source with 2 s crossfades so they can run under many cuts (one continuous bed per location).
Writes <outdir>/<name>_{dx,fx,amb,mus,mix}.wav (48 kHz stereo float) and reports integrated loudness/true peak.
"""
import argparse, json, os, subprocess, sys
import numpy as np

SR = 48000
STORY_DIR = "."                                  # set from --story in main()
STEMS = ["dx", "fx", "amb", "mus"]
_cache = {}


def load(path):
    """Decode any audio file to float32 stereo 48 kHz via ffmpeg."""
    p = path if os.path.isabs(path) else os.path.join(STORY_DIR, path)
    if p in _cache:
        return _cache[p]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    _cache[p] = x
    return x


def curve(points, n, default):
    """Linear interpolation of [[t, v], ...] over n samples."""
    if not points:
        return np.full(n, default, np.float32)
    t = np.arange(n) / SR
    xs, ys = zip(*points)
    return np.interp(t, xs, ys).astype(np.float32)


def lowpass_var(x, hz, block=1024):
    """2nd-order Butterworth lowpass whose cutoff follows hz (per sample), processed in blocks with carried state."""
    from scipy.signal import butter, lfilter, lfilter_zi
    if np.all(hz >= 19000):
        return x
    y = np.empty_like(x)
    zi = None
    for i in range(0, len(x), block):
        f = float(min(np.median(hz[i:i + block]), 19000))
        b, a = butter(2, f / (SR / 2))
        if zi is None:
            zi = np.stack([lfilter_zi(b, a) * x[0, k] for k in range(2)], 1)
        y[i:i + block], zi = lfilter(b, a, x[i:i + block], axis=0, zi=zi)
    return y


def dx_process(x, room=True, hp=90, lp=8500, rt=0.35, wet_db=-13, predelay=0.012, mono=True, early_db=None):
    """Dialogue as if recorded in the location: high/low-pass like a boom mic, a small synthetic room
    (exponentially decaying stereo noise impulse, RT60 = rt) mixed in at wet_db, centred in mono."""
    from scipy.signal import butter, sosfilt, fftconvolve
    if mono:
        x = np.repeat(x.mean(1, keepdims=True), 2, 1)
    x = sosfilt(butter(2, hp / (SR / 2), "highpass", output="sos"), x, axis=0)
    x = sosfilt(butter(2, lp / (SR / 2), "lowpass", output="sos"), x, axis=0)
    if room:
        n = int(rt * SR); t = np.arange(n) / SR
        rng = np.random.default_rng(11)
        ir = rng.standard_normal((n, 2)) * np.exp(-6.9 * t / rt)[:, None]
        ir = sosfilt(butter(2, 5000 / (SR / 2), "lowpass", output="sos"), ir, axis=0)
        ir = np.concatenate([np.zeros((int(predelay * SR), 2)), ir])
        ir /= np.sqrt((ir ** 2).sum(0, keepdims=True))
        if early_db is not None:                 # a few early reflections off the counter / plastic walls
            for k, (ms, side) in enumerate([(4.5, 0), (7.0, 1), (11.0, 0), (14.5, 1), (19.0, 0)]):
                i = int(ms / 1000 * SR)
                if i < len(ir):
                    ir[i, side] += 10 ** ((early_db - 2 * k) / 20) * 6
        wet = np.stack([fftconvolve(x[:, k], ir[:, k])[: len(x) + len(ir) - 1] for k in range(2)], 1)
        dry = np.concatenate([x, np.zeros((len(ir) - 1, 2))])
        x = dry + wet * 10 ** (wet_db / 20)
    return x.astype(np.float32)


def tame(x, thr):
    """Smooth peak limiter for beds: thunder claps or big drips above thr are pulled down (5 ms look, 80 ms release)."""
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    env = maximum_filter1d(np.abs(x).max(1), size=int(0.005 * SR))
    g = np.minimum(1.0, thr / (env + 1e-9))
    g = np.minimum(g, uniform_filter1d(g, size=int(0.08 * SR)))   # do not release faster than ~80 ms
    return x * g[:, None]


def loop_to(src, n, offset=0.0, xf=2.0):
    """Repeat src to n samples with equal-power crossfades so the loop seam is not heard."""
    k = int(xf * SR)
    src = np.roll(src, -int(offset * SR), axis=0)
    fin = np.sin(np.linspace(0, np.pi / 2, k))[:, None].astype(np.float32)
    fout = np.cos(np.linspace(0, np.pi / 2, k))[:, None].astype(np.float32)
    out = np.zeros((n, 2), np.float32)
    step, pos = len(src) - k, 0
    while pos < n:
        seg = src.copy()
        if pos > 0:
            seg[:k] *= fin
        if pos + len(seg) < n:
            seg[-k:] *= fout
        end = min(n, pos + len(seg))
        out[pos:end] += seg[: end - pos]
        pos += step
    return out


def pan_gain(pan):
    a = (pan + 1) * np.pi / 4
    return np.array([np.cos(a), np.sin(a)], np.float32) * np.sqrt(2)


def place(buf, x, at):
    i = int(round(at * SR))
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    if j > i:
        buf[i:j] += x[: j - i]


def render(cfg, story):
    n = int(cfg["duration"] * SR)
    stems = {s: np.zeros((n, 2), np.float32) for s in STEMS}

    for b in cfg.get("beds", []):
        src = load(b["src"])
        rms = np.sqrt((src.astype(np.float64) ** 2).mean()) + 1e-9
        src = src * (10 ** (b.get("ref_db", -35) / 20) / rms)      # every bed at the same reference RMS
        src = tame(src, 10 ** ((b.get("ref_db", -35) + b.get("crest_db", 15)) / 20))
        x = loop_to(src.astype(np.float32), n, b.get("offset", 0))
        g = 10 ** (curve(b.get("gain"), n, 0) / 20)
        if b.get("lp"):
            x = lowpass_var(x, curve(b["lp"], n, 20000)).astype(np.float32)
        if b.get("hp", 120):                     # cut rumble / mains hum under the rain
            from scipy.signal import butter, sosfilt
            x = sosfilt(butter(4, b.get("hp", 120) / (SR / 2), "highpass", output="sos"), x, axis=0).astype(np.float32)
        stems[b.get("stem", "amb")] += x * g[:, None]

    for c in cfg.get("cues", []):
        x = load(c["src"])
        i0 = int(c.get("in", 0) * SR)
        i1 = len(x) if c.get("dur") is None else i0 + int(c["dur"] * SR)
        x = x[i0:i1].copy()
        if c.get("rate"):                       # crude pitch/speed change by resampling
            idx = np.arange(0, len(x) - 1, c["rate"])
            x = np.stack([np.interp(idx, np.arange(len(x)), x[:, k]) for k in range(2)], 1).astype(np.float32)
        fi, fo = int(c.get("fade_in", 0.005) * SR), int(c.get("fade_out", 0.05) * SR)
        if fi: x[:fi] *= np.linspace(0, 1, fi)[:, None]
        if fo: x[-fo:] *= np.linspace(1, 0, fo)[:, None]
        if c.get("lp"):
            x = lowpass_var(x, np.full(len(x), c["lp"], np.float32)).astype(np.float32)
        mono = c.get("mono", False)
        if mono:
            x = np.repeat(x.mean(1, keepdims=True), 2, 1)
        x = x * pan_gain(c.get("pan", 0.0)) * 10 ** (c.get("db", 0) / 20)
        place(stems[c.get("stem", "fx")], x, c["at"])

    if True:                                     # always rendered: it sets the mix level even when left out
        for c in story["timeline"]["clips"]:
            if c["track_id"] != "tr_vo" or not c.get("enabled", True):
                continue
            x = load(c["media_url"])
            x = x[int(c["source_in_ms"] / 1000 * SR): int(c["source_out_ms"] / 1000 * SR)]
            x = x * 10 ** (cfg.get("dx_db", {}).get(c["id"], 0) / 20) * c.get("volume", 1)
            fx = cfg.get("dx_fx")
            if fx:                                   # seat the line in the scene: band-limit + room + distance + pan
                prm = dict(fx.get("params", {}))
                prm.update(fx.get("lines", {}).get(c["id"], {}))
                pan, gain_db = prm.pop("pan", 0.0), prm.pop("gain_db", 0.0)
                x = dx_process(x, room=c["id"] not in fx.get("dry_ids", []), **prm)
                x = x * pan_gain(pan) * 10 ** (gain_db / 20)
            place(stems["dx"], x, c["timeline_start_ms"] / 1000)

    dc = cfg.get("dx_comp")
    if dc:                                       # dialogue bus compressor: evens out lines so peaks don't hold the mix down
        from scipy.ndimage import uniform_filter1d
        x = stems["dx"]; mono = np.abs(x).max(1)
        env = np.sqrt(uniform_filter1d(mono ** 2, size=int(dc.get("window", 0.01) * SR))) + 1e-9
        a = np.exp(-1 / (dc.get("attack", 0.005) * SR)); r = np.exp(-1 / (dc.get("release", 0.15) * SR))
        from scipy.signal import lfilter
        sm = lfilter([1 - r], [1, -r], env)          # release-smoothed; then fast attack via max with lightly smoothed env
        sm = np.maximum(sm, lfilter([1 - a], [1, -a], env))
        act = sm > 10 ** (-40 / 20)
        thr = np.percentile(sm[act], dc.get("thr_pct", 70)) if act.any() else 1.0
        gain = np.where(sm > thr, (thr / sm) ** (1 - 1 / dc.get("ratio", 3.0)), 1.0)
        stems["dx"] = (x * gain[:, None] * 10 ** (dc.get("makeup_db", 0) / 20)).astype(np.float32)
        print(f"dx_comp: threshold {20 * np.log10(thr):.1f} dBFS, max reduction {-20 * np.log10(gain.min()):.1f} dB")
        if dc.get("peak_cut_db"):                # transient peaks (plosives, TTS clicks) shaved by a short look-around limiter
            pk = np.abs(stems["dx"]).max()
            stems["dx"] = tame(stems["dx"], pk * 10 ** (-dc["peak_cut_db"] / 20)).astype(np.float32)
            print(f"dx peaks: -{dc['peak_cut_db']} dB")

    ducks = cfg.get("duck") or []
    if isinstance(ducks, dict):                           # one rule or a list of rules (e.g. music ducked deeper, slower)
        ducks = [ducks]
    for d in (ducks if cfg.get("dialogue", True) else []):
        hop = SR // 100                                   # 10 ms frames
        nf = n // hop + 1
        env = np.array([np.abs(stems["dx"][i * hop:(i + 1) * hop]).max(initial=0) for i in range(nf)])
        key = (env > 10 ** (-40 / 20)).astype(np.float32)
        up, down = hop / (d.get("attack", .15) * SR), hop / (d.get("release", .4) * SR)
        sm = np.empty(nf, np.float32); acc = 0.0
        for i, k in enumerate(key):                       # attack/release follower at frame rate
            acc = min(acc + up, 1.0) if k > acc else max(acc - down, k)
            sm[i] = acc
        sm = np.interp(np.arange(n) / hop, np.arange(nf), sm).astype(np.float32)
        g = 10 ** (d["db"] * sm / 20)
        for s in d["stems"]:
            stems[s] *= g[:, None]

    ref = sum(stems.values())                    # level reference always includes dialogue
    mix = ref if cfg.get("dialogue", True) else ref - stems["dx"]
    return stems, mix, ref


def write_wav(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-",
                    "-c:a", "pcm_f32le", path], input=x.astype(np.float32).tobytes(), check=True)


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    tail = r[r.rfind("Summary:"):]
    I = next((l.split()[1] for l in tail.splitlines() if l.strip().startswith("I:")), "?")
    P = next((l.split()[1] for l in tail.splitlines() if l.strip().startswith("Peak:")), "?")
    return I, P


def main():
    global STORY_DIR
    ap = argparse.ArgumentParser(description="Render stems + stereo mix from a sound cue sheet.")
    ap.add_argument("cues", help="cue sheet JSON")
    ap.add_argument("--story", help="story folder (default: the cue file's parent's parent)")
    ap.add_argument("--outdir", help="output folder for stems and mix (default: <story>/edit/mix)")
    ap.add_argument("--video", help="picture to mux the mix onto (relative to the story folder)")
    ap.add_argument("--out", help="muxed video output (relative to the story folder)")
    a = ap.parse_args()
    if a.video and not a.out:
        ap.error("--video needs --out")
    cfg_path = a.cues
    STORY_DIR = a.story or os.path.join(os.path.dirname(os.path.abspath(cfg_path)), "..")
    cfg = json.load(open(cfg_path, encoding="utf8"))
    story = json.load(open(os.path.join(STORY_DIR, "story.json"), encoding="utf8"))
    stems, mix, ref = render(cfg, story)
    # loudness: normalize the mix to -14 LUFS with a -1 dBTP ceiling (two-pass loudnorm), stems keep the same gain
    name = os.path.splitext(os.path.basename(cfg_path))[0]
    out_dir = a.outdir or os.path.join(STORY_DIR, "edit", "mix")
    raw = os.path.join(out_dir, f"{name}_mix_raw.wav")
    write_wav(raw, ref)
    I, P = loudness(raw)
    gain_db = -14.0 - float(I) if I != "?" else 0.0
    peak_db = 20 * np.log10(np.abs(ref).max() + 1e-9)
    gain_db = min(gain_db, -1.5 + cfg.get("limit_db", 3.0) - peak_db)    # the limiter may take at most limit_db (default 3 dB) off the loudest peak
    g = 10 ** (gain_db / 20)
    for s, x in stems.items():
        write_wav(os.path.join(out_dir, f"{name}_{s}.wav"), x * g)
    # gain to -14 LUFS, then a peak limiter (ceiling -1.5 dBFS sample peak ~ -1 dBTP) for stray transients
    final = os.path.join(out_dir, f"{name}_mix.wav")
    write_wav(raw, mix * g)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af",
                    "alimiter=limit=0.74:attack=3:release=60:level=false", "-c:a", "pcm_f32le", final], check=True)
    os.remove(raw)
    I2, P2 = loudness(final)
    print(f"mix: integrated {I2} LUFS, true peak {P2} dBTP (gain {gain_db:+.1f} dB)")
    if a.video:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(STORY_DIR, a.video), "-i", final, "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest",
                        os.path.join(STORY_DIR, a.out)], check=True)
        print("video:", a.out)


if __name__ == "__main__":
    main()
