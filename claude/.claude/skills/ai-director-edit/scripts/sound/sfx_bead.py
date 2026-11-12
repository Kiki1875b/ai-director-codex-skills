"""Bead resonance cues, synthesized (glass-harmonica partials with slow beating, airy noise, glass ticks).

  python sfx_bead.py --story stories/<slug>   # writes <story>/media/audio/sfx/bead/*.wav (48 kHz stereo, peak -6 dBFS)
  python sfx_bead.py --out DIR                # or into DIR

The building blocks (tone, air, tick, env, place) are generic. main() is the cue set of 「마지막 손님」
(stories/male-gumiho/script/07-handoff.md: S1-4, S2-4, S2-7, S4-3 rise / S4-7 reverse / S4-8 shatter / S4-9
silence): copy and edit it for another film's designed cues.
"""
import argparse, os, wave
import numpy as np

SR = 48000
OUT = None                                       # set from --story / --out
rng = np.random.default_rng(7)

# a minor-ish cluster around A2/E3 with glassy inharmonic partials
BASE = 110.0
PARTIALS = [(1.0, 1.0), (2.01, 0.55), (2.98, 0.35), (4.07, 0.22), (5.43, 0.12), (6.9, 0.06)]


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def smooth(x, n):
    k = np.hanning(n); k /= k.sum()
    return np.convolve(x, k, mode="same")


def tone(dur, f0=BASE, bright=1.0, beat=0.35, detune=0.6):
    """Stereo glass tone: each partial is a pair of slightly detuned sines (L/R) -> slow beating and width."""
    t = t_axis(dur)
    L = np.zeros_like(t); R = np.zeros_like(t)
    for i, (ratio, amp) in enumerate(PARTIALS):
        a = amp * (bright ** i)
        f = f0 * ratio
        ph = rng.uniform(0, 2 * np.pi, 2)
        L += a * np.sin(2 * np.pi * (f - detune * 0.5) * t + ph[0])
        R += a * np.sin(2 * np.pi * (f + detune * 0.5) * t + ph[1])
    trem = 1 + 0.18 * np.sin(2 * np.pi * beat * t)
    return np.stack([L * trem, R * trem], 1)


def air(dur, lp=900):
    """Breathy band-limited noise (one-pole lowpass), stereo."""
    n = rng.standard_normal((int(dur * SR), 2))
    a = np.exp(-2 * np.pi * lp / SR)
    y = np.zeros_like(n)
    for c in range(2):
        acc = 0.0
        col = n[:, c]; out = y[:, c]
        for i in range(len(col)):
            acc = (1 - a) * col[i] + a * acc
            out[i] = acc
    return y / (np.abs(y).max() + 1e-9)


def env(dur, pts):
    """Piecewise-linear envelope from [(time_s, gain), ...]."""
    t = t_axis(dur)
    xs, ys = zip(*pts)
    return np.interp(t, xs, ys)[:, None]


def tick(f=2400, dur=0.9, decay=7.0):
    """Small glass tick with a short ring."""
    t = t_axis(dur)
    s = sum(a * np.sin(2 * np.pi * f * r * t) for r, a in [(1, 1), (2.76, .5), (5.4, .25), (8.9, .1)])
    s = s * np.exp(-decay * t)
    s[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    pan = rng.uniform(0.35, 0.65)
    return np.stack([s * (1 - pan), s * pan], 1)


def place(dst, src, at):
    i = int(at * SR); j = min(len(dst), i + len(src))
    dst[i:j] += src[: j - i]


def norm(x, peak_db=-6):
    return x / (np.abs(x).max() + 1e-9) * 10 ** (peak_db / 20)


def write(name, x):
    os.makedirs(OUT, exist_ok=True)
    fade = int(0.02 * SR)
    x[:fade] *= np.linspace(0, 1, fade)[:, None]; x[-fade:] *= np.linspace(1, 0, fade)[:, None]
    pcm = np.rint(np.clip(norm(x), -1, 1) * 32767).astype("<i2")
    with wave.open(os.path.join(OUT, name), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print("wrote", name, round(len(x) / SR, 2), "s")


def main():
    # S1-4 (4.04 s): low hum swells with the vision (in 0.6, full 1.2, break 2.2, out 3.0 — matches s14_bead_composite)
    d = 4.04
    x = tone(d, bright=0.8) * env(d, [(0, 0), (0.6, .5), (1.2, 1), (2.2, .9), (3.0, .25), (d, 0)])
    x += 0.25 * air(d, 700) * env(d, [(0, 0), (2.0, .2), (2.6, 1), (3.4, 0), (d, 0)])   # scatter breath
    place(x, 0.25 * tick(3100, 1.2), 2.25)
    write("S1-4_bead_vision.wav", x)

    # S2-4 (3.5 s): pulse under the coat, light blinks through wool -> slow throb, muffled (dark)
    d = 3.5
    t = t_axis(d)
    pulse = (0.55 + 0.45 * np.sin(2 * np.pi * 0.9 * t - np.pi / 2)) ** 2
    x = tone(d, f0=BASE, bright=0.45) * pulse[:, None] * env(d, [(0, 0), (0.4, 1), (d - 0.4, 1), (d, 0)])
    write("S2-4_bead_pulse.wav", x)

    # S2-7 (4.0 s): rise, amber eyes
    d = 4.0
    x = tone(d, f0=BASE, bright=0.9, beat=0.6) * env(d, [(0, 0), (1.0, .3), (3.4, 1), (d, .6)])
    x += 0.5 * tone(d, f0=BASE * 1.5, bright=0.8) * env(d, [(0, 0), (2.0, 0), (3.6, .6), (d, .4)])
    write("S2-7_bead_rise.wav", x)

    # S4-3..S4-4 (7.1 s): resonance grows, then wind-like low as blue light floods the tent
    d = 7.1
    x = tone(d, f0=BASE, bright=1.0, beat=0.5) * env(d, [(0, .2), (3.5, 1), (4.2, .7), (d, .35)])
    x += 0.8 * tone(d, f0=BASE / 2, bright=0.6, beat=0.2) * env(d, [(0, 0), (3.6, .1), (4.4, .8), (d, .6)])
    x += 0.6 * air(d, 300) * env(d, [(0, 0), (4.0, 0), (5.0, 1), (d, .8)])
    write("S4-3_bead_grow.wav", x)

    # S4-7 (12.0 s): reverse rotation — reversed swells that suck in toward the line "네가... 날 기억해 줘" (VO at +7.5 s)
    d = 12.0
    one = tone(3.0, f0=BASE, bright=0.9) * env(3.0, [(0, 1), (0.05, 1), (3.0, 0)])
    x = np.zeros((int(d * SR), 2))
    for at, g in [(0.5, .5), (3.2, .7), (5.6, .9)]:
        place(x, g * one[::-1], at)          # reversed: grows then cuts
    x += 0.35 * tone(d, f0=BASE / 2, bright=.5, beat=.15) * env(d, [(0, 0), (2, .4), (7.3, .6), (8.6, .15), (d, .1)])
    write("S4-7_bead_reverse.wav", x)

    # S4-8 (8.0 s): eight small beads shatter into blue sparks, then the flame fills the bead (bloom)
    d = 8.0
    x = np.zeros((int(d * SR), 2))
    for k, at in enumerate(np.linspace(0.6, 4.2, 8) + rng.uniform(-0.12, 0.12, 8)):
        place(x, 0.5 * tick(rng.uniform(2200, 4200), 1.6, decay=4.0), at)
        place(x, 0.15 * air(0.5, 5000) * env(0.5, [(0, 1), (0.5, 0)]), at)
    x += tone(d, f0=BASE, bright=1.0, beat=0.8) * env(d, [(0, .15), (4.5, .3), (6.6, 1), (7.6, .9), (d, 0)])
    x += 0.5 * tone(d, f0=BASE * 2, bright=0.7) * env(d, [(0, 0), (5.0, 0), (6.8, .6), (d, 0)])
    write("S4-8_bead_shatter_bloom.wav", x)

    # small glass touches (bead on palm / on the bar)
    write("bead_touch_palm.wav", 0.6 * tick(2600, 0.9, decay=9) + 0.2 * tone(0.9, bright=.5) * env(0.9, [(0, 1), (0.9, 0)]))
    write("bead_set_on_bar.wav", tick(1900, 1.4, decay=5) + 0.3 * tone(1.4, bright=.6) * env(1.4, [(0, 1), (1.4, 0)]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Synthesize designed bead resonance cues.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--story", help="story folder: writes <story>/media/audio/sfx/bead/")
    g.add_argument("--out", help="output folder")
    a = ap.parse_args()
    OUT = a.out or os.path.join(a.story, "media", "audio", "sfx", "bead")
    main()
