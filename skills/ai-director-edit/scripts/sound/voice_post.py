"""Post-process a TTS dialogue line so it sounds less synthetic (no regeneration).

  python voice_post.py in.wav out.wav [--intonation 0.75] [--no-world] [--deess 4] [--air -3] [--prox 2] [--comp 3]

Steps (research notes: stories/male-gumiho/edit/voice-post-research-20261109.md):
 1. Intonation range (WORLD vocoder, pyworld MIT): pitch deviations around the line's mean (in semitones) are scaled by
    --intonation (<1 = flatter, the user asked for less up-and-down on Yeon). Spectral envelope and aperiodicity stay,
    so the voice timbre does not change. 1.0 = untouched (WORLD is then skipped).
 2. Mic texture: gentle high-shelf cut above 7 kHz (--air dB, the "digital bite"), dynamic de-esser 5-9 kHz (--deess dB
    max reduction), low-shelf boost below 180 Hz (--prox dB, close-mic proximity), slow 3:1 compression (--comp dB of
    gain reduction target), very light tape-style saturation.
Output: 48 kHz mono, peak -3 dBFS (levels are set later in sound_mix.py).
"""
import argparse, subprocess, sys
import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt

SR = 48000


def read(p, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "f64le", "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float64).copy()


def write(p, x, sr=SR):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", p],
                   input=x.astype(np.float32).tobytes(), check=True)


def intonation(x, k, sr=SR):
    import pyworld as pw
    f0, t = pw.harvest(x, sr, f0_floor=60, f0_ceil=600, frame_period=5.0)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr); ap = pw.d4c(x, f0, t, sr)
    v = f0 > 0
    if v.sum() < 5: return x, 0, 0
    st = 12 * np.log2(f0[v]); m = np.median(st)
    before = st.std()
    f0n = f0.copy(); f0n[v] = 2 ** ((m + (st - m) * k) / 12)
    y = pw.synthesize(f0n, sp, ap, sr, frame_period=5.0)[:len(x)]
    return y, before, (12 * np.log2(f0n[v])).std()


def shelf(x, f, db, kind):
    """Shelf by blending a filtered copy (simple, phase-safe with filtfilt)."""
    sos = butter(2, f / (SR / 2), "highpass" if kind == "high" else "lowpass", output="sos")
    band = sosfiltfilt(sos, x)
    return x + band * (10 ** (db / 20) - 1)


def env_follow(x, att_ms, rel_ms):
    a = np.exp(-1 / (att_ms / 1000 * SR)); r = np.exp(-1 / (rel_ms / 1000 * SR))
    e = np.zeros_like(x); s = 0.0; ax = np.abs(x)
    for i, v in enumerate(ax):
        s = a * s + (1 - a) * v if v > s else r * s + (1 - r) * v
        e[i] = s
    return e


def deess(x, max_db):
    band = sosfilt(butter(2, [5000 / (SR / 2), 9000 / (SR / 2)], "bandpass", output="sos"), x)
    eb = env_follow(band, 1, 40); ef = env_follow(x, 5, 80) + 1e-9
    ratio = eb / ef                                   # sibilant energy relative to the whole signal
    thr = np.percentile(ratio[ef > ef.max() * 0.05], 80)
    red = np.clip((ratio - thr) / (thr + 1e-9), 0, 1) * (1 - 10 ** (-max_db / 20))
    return x - band * red


def compress(x, target_db):
    e = env_follow(x, 8, 150) + 1e-9
    thr = np.percentile(e[e > e.max() * 0.05], 60)
    gain = np.where(e > thr, (thr / e) ** (2 / 3), 1.0)          # 3:1
    floor = 10 ** (-target_db / 20)
    gain = np.maximum(gain, floor)
    return x * gain


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--intonation", type=float, default=1.0)
    ap.add_argument("--deess", type=float, default=4); ap.add_argument("--air", type=float, default=-3)
    ap.add_argument("--prox", type=float, default=2); ap.add_argument("--comp", type=float, default=3)
    a = ap.parse_args()
    x = read(a.inp)
    if a.intonation != 1.0:
        x, s0, s1 = intonation(x, a.intonation)
        print(f"intonation: pitch spread {s0:.2f} -> {s1:.2f} semitones")
    x = shelf(x, 7000, a.air, "high")
    x = deess(x, a.deess)
    x = shelf(x, 180, a.prox, "low")
    x = compress(x, a.comp)
    x = np.tanh(x * 1.2 / (np.abs(x).max() + 1e-9)) / np.tanh(1.2)          # very light saturation
    x = x / (np.abs(x).max() + 1e-9) * 10 ** (-3 / 20)
    write(a.out, x)
    print("wrote", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
