"""Replace the end of a shot with a regenerated tail and grade the head/mouth motion of the result.

  python tail_splice.py --head head.mp4 --cut 28 --tails t1.mp4 t2.mp4 --frames 73 --out-prefix out/S6-3_tail
    [--audio voice.wav]

Result = head frames 0..cut + tail frames 1..(frames-cut-1) (tail frame 0 is the start key = head frame `cut`).
Per candidate it reports, for the tail part: nose x range (px), direction changes of the head (x velocity sign flips
above 0.7 px/frame), yaw range, max lip gap / face height (mouth must stay closed after the line), the seam frame
difference vs the median, and writes <prefix>_<i>.mp4. PASS = direction changes <= 1, x range <= 15 px, yaw range <= 0.05.
"""
import argparse, subprocess, sys
import numpy as np, cv2, mediapipe as mp


def load(p):
    c = cv2.VideoCapture(p); F = []
    while True:
        ok, f = c.read()
        if not ok: break
        F.append(f)
    return F


def grade(frames, cut):
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=.3)
    L = []
    for f in frames:
        r = fm.process(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        L.append([[q.x * f.shape[1], q.y * f.shape[0]] for q in r.multi_face_landmarks[0].landmark] if r.multi_face_landmarks else L[-1])
    L = np.array(L); fh = np.linalg.norm(L[:, 10] - L[:, 152], axis=-1)
    nose = L[cut:, 1]; yaw = (L[cut:, 1, 0] - L[cut:, 234, 0]) / (L[cut:, 454, 0] - L[cut:, 234, 0])
    vx = np.diff(nose[:, 0]); big = vx[np.abs(vx) > 0.7]
    turns = int(np.sum(np.diff(np.sign(big)) != 0)) if len(big) > 1 else 0
    gap = (np.linalg.norm(L[:, 13] - L[:, 14], axis=-1) / fh)[cut + 3:]
    d = [np.abs(frames[i].astype(int) - frames[i - 1].astype(int)).mean() for i in range(1, len(frames))]
    return dict(x_range=float(np.ptp(nose[:, 0])), turns=turns, yaw_range=float(np.ptp(yaw)), gap_max=float(gap.max()),
                seam=float(max(d[cut - 1:cut + 2])), diff_med=float(np.median(d)), L=L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", required=True); ap.add_argument("--cut", type=int, required=True)
    ap.add_argument("--tails", nargs="+", required=True); ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--out-prefix", required=True); ap.add_argument("--audio")
    a = ap.parse_args()
    H = load(a.head)
    for i, t in enumerate(a.tails):
        T = load(t); need = a.frames - a.cut - 1
        if len(T) - 1 < need: print(t, "too short"); continue
        out = H[:a.cut + 1] + T[1:need + 1]
        g = grade(out, a.cut)
        ok = g["turns"] <= 1 and g["x_range"] <= 15 and g["yaw_range"] <= 0.05
        print(f"{t}: x range {g['x_range']:.0f}px, head direction changes {g['turns']}, yaw range {g['yaw_range']:.3f}, "
              f"lip gap max {g['gap_max'] * 100:.1f}, seam {g['seam']:.2f} (median {g['diff_med']:.2f}) -> {'PASS' if ok else 'fail'}")
        h, w = out[0].shape[:2]; p = f"{a.out_prefix}_{i}.mp4"
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", "24", "-i", "-"]
        if a.audio: cmd += ["-i", a.audio, "-af", "apad", "-shortest", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", p]
        pr = subprocess.Popen(cmd, stdin=subprocess.PIPE); pr.stdin.write(np.stack(out).tobytes()); pr.stdin.close(); pr.wait()
        print("  wrote", p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
