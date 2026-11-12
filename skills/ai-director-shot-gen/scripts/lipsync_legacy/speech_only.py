"""Use the lip-synced frames only while the line is spoken; elsewhere go back to the original frames.

  python speech_only.py --orig shot.mp4 --synced shot_ls16_post.mp4 --audio voice.wav --out out.mp4 [--pad 0.12 --ramp 4]

Why: LatentSync redraws the mouth on every frame, so between and after lines the mouth keeps a slightly different,
sometimes pursed shape (S4-5: the original closes the mouth and smiles at the end; the synced version does not).
Speech windows come from the voice track (louder than -35 dB of its peak, gaps under 0.25 s merged), padded by
--pad seconds; the switch is a linear blend over --ramp frames. The two videos differ only around the mouth
(lipsync_post.py already restricted the change), so a full-frame blend leaves no seam.
"""
import argparse, subprocess, sys
import numpy as np, cv2


def load(p):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok: break
        F.append(f)
    return np.stack(F), c.get(cv2.CAP_PROP_FPS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True); ap.add_argument("--synced", required=True)
    ap.add_argument("--audio", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=float, default=0.12); ap.add_argument("--ramp", type=int, default=4)
    a = ap.parse_args()
    O, fps = load(a.orig); S, _ = load(a.synced); n = min(len(O), len(S)); O, S = O[:n], S[:n]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.audio, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32); hop = 160
    db = 20 * np.log10(np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, len(x) - hop, hop)]) + 1e-9)
    on = db > db.max() - 35
    t = np.arange(len(on)) * 0.01
    w = np.zeros(n)
    for i in range(n):
        tt = i / fps
        w[i] = 1.0 if on[(t >= tt - a.pad) & (t <= tt + a.pad)].any() else 0.0
    # merge short gaps (< 0.25 s) and ramp
    g = int(0.25 * fps); i = 0
    while i < n:
        if w[i] == 0:
            j = i
            while j < n and w[j] == 0: j += 1
            if 0 < i and j < n and j - i < g: w[i:j] = 1
            i = j
        else: i += 1
    k = np.ones(a.ramp) / a.ramp
    ws = np.clip(np.convolve(w, k, mode="same"), 0, 1)
    segs = []; cur = None
    for i, v in enumerate(w):
        if v and cur is None: cur = i
        if not v and cur is not None: segs.append((cur / fps, i / fps)); cur = None
    if cur is not None: segs.append((cur / fps, n / fps))
    print("lip-sync frames used in", [(round(s, 2), round(e, 2)) for s, e in segs])
    out = (O * (1 - ws[:, None, None, None]) + S * ws[:, None, None, None]).astype(np.uint8)
    h, wd = out.shape[1:3]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{wd}x{h}", "-r", f"{fps:.6f}", "-i", "-",
           "-i", a.audio, "-af", "apad", "-shortest", "-c:a", "aac", "-b:a", "192k",
           "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE); p.stdin.write(out.tobytes()); p.stdin.close(); p.wait()
    print("wrote", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
