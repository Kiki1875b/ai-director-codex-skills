#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""review_video.py - 영상 검수 증거 도구 (자동 후보 탐지, 판정 아님).

사용법:
  python review_video.py <video.mp4> --out <dir> [--prev <prev.mp4>] [--next <next.mp4>]
         [--range IN_MS OUT_MS] [--prev-range IN_MS OUT_MS] [--next-range IN_MS OUT_MS] [--face-box x0,y0,x1,y1] [--hand-box x0,y0,x1,y1]
         [--ref-face <img>] [--interval 0.5]

  박스 좌표는 원본 해상도 픽셀. --range 는 사용 구간(ms)으로 먼저 자른다(시간은 구간 시작=0).
  --prev/--next 는 이음매 검사용: prev 의 마지막 프레임 -> 이 클립 첫 프레임,
  이 클립 마지막 -> next 첫 프레임의 프레임 차이/밝기 차 + 이음매 +-6프레임 박스 움직임.
  --prev-range/--next-range 는 타임라인 클립의 source_in/out(ms). 주면 prev 는 그 사용 구간의 끝,
  next 는 그 사용 구간의 시작 프레임을 경계로 쓴다(없으면 원본 파일 전체의 끝/처음 - 실제 편집점과 다를 수 있다).
  현재 클립은 --range 의 시작/끝을 쓴다. 각 이음매의 원본 파일, 사용 구간, 분석한 경계 시각(ms)을
  metrics.json flags.seam.<이음매>.a / .b 에 기록한다. 재생 속도(speed) 보정은 하지 않는다(범위 밖).

출력(<dir>): contact.jpg, faces.jpg(--face-box), metrics.json, metrics.png, report.md
플래그는 모두 "후보"다. 동작의 자연스러움은 반드시 영상을 직접 보고 판단한다.
의존성: ffmpeg/ffprobe(PATH), PIL, numpy (scipy 불필요). 분석은 가로 320px 회색조로 축소해 수행하며
중심 좌표/진폭 px 는 이 축소 좌표(원본 환산값도 같이 기록).
"""
import argparse, json, subprocess, sys, os
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/malgun.ttf"
AW = 320  # analysis width


def font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def run(cmd):
    return subprocess.run(cmd, capture_output=True)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate", "-of", "json", str(path)])
    s = json.loads(r.stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(n) / float(d), r.stderr.decode("utf8", "replace").strip()


def trim_args(rng):
    if not rng:
        return []
    return ["-ss", f"{rng[0]/1000:.3f}", "-t", f"{(rng[1]-rng[0])/1000:.3f}"]


def decode_gray(path, w, h, rng=None):
    """returns (frames[N,h,w] float32, stderr)"""
    r = run(["ffmpeg", "-v", "error", *trim_args(rng), "-i", str(path), "-vf", f"scale={w}:{h}",
             "-pix_fmt", "gray", "-f", "rawvideo", "-"])
    a = np.frombuffer(r.stdout, np.uint8)
    n = a.size // (w * h)
    return a[:n * w * h].reshape(n, h, w).astype(np.float32), r.stderr.decode("utf8", "replace").strip()


def extract(path, rng, idxs, vf, w, h):
    """full-colour frames at given frame indexes (relative to range start), filtered by vf -> list of HxWx3"""
    idxs = sorted(set(int(i) for i in idxs))
    sel = "+".join(f"eq(n\\,{i})" for i in idxs)
    r = run(["ffmpeg", "-v", "error", *trim_args(rng), "-i", str(path), "-vf", f"select='{sel}',{vf}",
             "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    a = np.frombuffer(r.stdout, np.uint8)
    n = a.size // (w * h * 3)
    fr = a[:n * w * h * 3].reshape(n, h, w, 3)
    return dict(zip(idxs[:n], [Image.fromarray(f) for f in fr]))


def ts(t):
    m = int(t // 60)
    return f"{m:02d}:{t - 60*m:05.2f}"


def parse_box(s):
    if not s:
        return None
    b = [int(float(v)) for v in s.split(",")]
    assert len(b) == 4
    return b


def runs(mask, min_len=1):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def box_motion(frames, box):
    """mean abs diff of crop between consecutive frames; len N-1; index k = frame k -> k+1"""
    x0, y0, x1, y1 = box
    c = frames[:, y0:y1, x0:x1]
    return np.abs(np.diff(c, axis=0)).mean(axis=(1, 2))


def smooth(x, k):
    if len(x) < k:
        return np.asarray(x, float)
    p = np.pad(x, (k // 2, k // 2), mode="edge")
    return np.convolve(p, np.ones(k) / k, mode="valid")[:len(x)]


def centroid_track(frames, box):
    x0, y0, x1, y1 = box
    xs, ys = [], []
    gx, gy = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1))
    for f in frames:
        c = f[y0:y1, x0:x1]
        m = c >= np.percentile(c, 70)
        w = m.sum() or 1
        xs.append((gx * m).sum() / w)
        ys.append((gy * m).sum() / w)
    return np.array(xs), np.array(ys)


def reversals(v, amp):
    """zigzag with hysteresis. A direction change = a confirmed extreme that is followed by a
    swing > amp back the other way, after an earlier swing > amp. Returns (count, frame idx list)."""
    v = smooth(v, 5)
    d, hi, lo, hi_i, lo_i = 0, v[0], v[0], 0, 0
    ext = []  # confirmed extremes (index)
    for i, x in enumerate(v):
        if x > hi: hi, hi_i = x, i
        if x < lo: lo, lo_i = x, i
        if d <= 0 and x - lo > amp:      # rising enough from lo
            if d == -1: ext.append(lo_i)  # lo was a turning point after a fall
            d, hi, hi_i = 1, x, i
        elif d >= 0 and hi - x > amp:    # falling enough from hi
            if d == 1: ext.append(hi_i)
            d, lo, lo_i = -1, x, i
    return len(ext), ext


def phase_shift(a, b):
    """(dy, dx) that moves a onto b."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A, B = np.fft.fft2((a - a.mean()) * win), np.fft.fft2((b - b.mean()) * win)
    R = B * np.conj(A); R /= np.abs(R) + 1e-9
    c = np.fft.ifft2(R).real
    py, px = np.unravel_index(c.argmax(), c.shape)
    h, w = a.shape
    return (py if py < h / 2 else py - h), (px if px < w / 2 else px - w)


def camera_motion(frames, step):
    """Translation and zoom of the picture vs frame 0, from the four quadrants."""
    N, h, w = frames.shape
    h2, w2 = h // 2, w // 2
    q = {"tl": (slice(0, h2), slice(0, w2)), "tr": (slice(0, h2), slice(w2, w)),
         "bl": (slice(h2, h), slice(0, w2)), "br": (slice(h2, h), slice(w2, w))}
    out = {"t": [], "tx": [], "ty": [], "zoom": []}
    f0 = frames[0].astype(float)
    for i in list(range(0, N, step)) + ([N - 1] if (N - 1) % step else []):
        fi = frames[i].astype(float)
        s = {k: phase_shift(f0[v], fi[v]) for k, v in q.items()}
        dxl, dxr = (s["tl"][1] + s["bl"][1]) / 2, (s["tr"][1] + s["br"][1]) / 2
        dyt, dyb = (s["tl"][0] + s["tr"][0]) / 2, (s["bl"][0] + s["br"][0]) / 2
        out["t"].append(i); out["tx"].append((dxl + dxr) / 2); out["ty"].append((dyt + dyb) / 2)
        out["zoom"].append(((dxr - dxl) / w2 + (dyb - dyt) / h2) / 2)
    return out


def fmt_rng(a, b, fps):
    return [round(a / fps, 3), round((b + 1) / fps, 3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prev")
    ap.add_argument("--next")
    ap.add_argument("--range", nargs=2, type=int, metavar=("IN_MS", "OUT_MS"))
    ap.add_argument("--prev-range", nargs=2, type=int, metavar=("IN_MS", "OUT_MS"))
    ap.add_argument("--next-range", nargs=2, type=int, metavar=("IN_MS", "OUT_MS"))
    ap.add_argument("--face-box")
    ap.add_argument("--hand-box")
    ap.add_argument("--ref-face")
    ap.add_argument("--interval", type=float, default=0.5)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = a.range
    W, H, fps, perr = probe(a.video)
    aw, ah = AW, int(round(AW * H / W / 2) * 2)
    sx, sy = aw / W, ah / H
    fb, hb = parse_box(a.face_box), parse_box(a.hand_box)

    def sbox(b):
        return None if not b else [max(0, int(b[0] * sx)), max(0, int(b[1] * sy)),
                                   min(aw, int(round(b[2] * sx))), min(ah, int(round(b[3] * sy)))]

    fbs, hbs = sbox(fb), sbox(hb)

    frames, derr = decode_gray(a.video, aw, ah, rng)
    N = len(frames)
    if N < 3:
        sys.exit("too few frames decoded: " + derr)
    # full decode error scan (no scaling, null muxer)
    ferr = run(["ffmpeg", "-v", "error", *trim_args(rng), "-i", a.video, "-f", "null", "-"]).stderr.decode("utf8", "replace").strip()
    errs = [e for e in (perr, derr, ferr) if e]
    errs = sorted(set("\n".join(errs).splitlines()))

    luma = frames.mean(axis=(1, 2))
    fdiff = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))  # len N-1
    hand_m = box_motion(frames, hbs) if hbs else None
    face_m = box_motion(frames, fbs) if fbs else None
    cx = cy = None
    if fbs:
        cx, cy = centroid_track(frames, fbs)

    flags = {}
    t_of = lambda i: i / fps

    # freeze (stutter): motion -> near stop -> restart
    freeze = []
    series = []
    if hand_m is not None: series.append(("hand_box", hand_m))
    if face_m is not None: series.append(("face_box", face_m))
    if not series: series.append(("frame", fdiff))
    for name, m in series:
        ms = smooth(m, 3)
        scale = np.percentile(ms, 90)
        if scale < 0.3:
            continue
        low = ms < 0.5 * scale
        for i, j in runs(low, 1):
            dur = (j - i + 1) / fps
            before = ms[:i].max() if i > 0 else 0
            after = ms[j + 1:].max() if j + 1 < len(ms) else 0
            if dur >= 0.4 and before > 0.6 * scale and after > 0.6 * scale:
                freeze.append({"where": name, "t": fmt_rng(i, j, fps), "duration_s": round(dur, 2),
                               "motion_in_run": round(float(ms[i:j + 1].mean()), 3),
                               "p90_motion": round(float(scale), 3)})
    flags["freeze"] = freeze

    # direction reversal
    rev = []
    if cx is not None:
        for ax, v in (("x", cx), ("y", cy)):
            cnt, idx = reversals(v, 4.0 * (sx if ax == 'x' else sy))  # 4 px in original resolution
            if cnt >= 2:
                rev.append({"axis": ax, "count": cnt, "turn_times_s": [round(t_of(i), 2) for i in idx],
                            "swing_px_analysis": round(float(smooth(v, 5).max() - smooth(v, 5).min()), 1),
                            "swing_px_original": round(float((smooth(v, 5).max() - smooth(v, 5).min()) / (sx if ax == 'x' else sy)), 1)})
    flags["direction_reversal"] = rev

    # brightness drift
    k = min(4, N // 4 or 1)
    total = float(luma[-k:].mean() - luma[:k].mean())
    tail = float(luma[-1] - luma[max(0, N - 16)])
    drift = []
    if abs(total) > 2.0:
        drift.append({"kind": "total", "delta": round(total, 2), "start": round(float(luma[:k].mean()), 2), "end": round(float(luma[-k:].mean()), 2)})
    if abs(tail) > 1.0:
        drift.append({"kind": "last16", "delta": round(tail, 2), "t": [round(t_of(max(0, N - 16)), 2), round(t_of(N - 1), 2)], "note": "threshold 1.0"})
    flags["brightness_drift"] = drift

    # spike
    med = float(np.median(fdiff)) or 1e-6
    sp = [{"t": round(t_of(i + 1), 3), "diff": round(float(fdiff[i]), 3), "ratio": round(float(fdiff[i] / med), 1)}
          for i in range(len(fdiff)) if fdiff[i] > 3 * med]
    flags["spike"] = sp

    # black / frozen frames
    bf = [{"kind": "black", "t": fmt_rng(i, j, fps), "luma": round(float(luma[i:j + 1].mean()), 2)}
          for i, j in runs(luma < 8)]
    bf += [{"kind": "identical_frames", "t": fmt_rng(i, j + 1, fps), "diff": round(float(fdiff[i:j + 1].mean()), 4)}
           for i, j in runs(fdiff < 0.05, 3)]
    flags["black_or_frozen_frames"] = bf
    flags["decode_errors"] = errs

    # camera drift / zoom: phase correlation of each quadrant against frame 0.
    # Contact sheets at 0.5 s steps hide slow drift and push-ins (S1 2026-11-08: missed 4 of 5).
    cam = camera_motion(frames, max(1, N // 24))
    drift_px = max(abs(cam["tx"][-1]), abs(cam["ty"][-1])) / sx
    cam_flags = []
    if drift_px > 6 or abs(cam["zoom"][-1]) > 0.03:
        cam_flags.append({"t": fmt_rng(0, N - 1, fps), "shift_px_original": [round(float(cam["tx"][-1] / sx), 1), round(float(cam["ty"][-1] / sy), 1)],
                          "zoom": round(float(cam["zoom"][-1]), 3),
                          "note": "zoom sign is unreliable when a person moves across quadrants; check first_last.jpg"})
    flags["camera_drift"] = cam_flags

    # seams
    seams = {}

    def side(src, r, n, f, which):
        """source, used range and the exact source timestamp (ms) of the boundary frame analysed"""
        t0 = r[0] if r else 0
        return {"source": str(src), "used_range_ms": r, "boundary": which,
                "boundary_ms": round(t0 + ((n - 1) if which == "last" else 0) / f * 1000, 1)}

    def seam(label, seqA, seqB, boxes, ma, mb):
        seq = np.concatenate([seqA[-7:], seqB[:7]])
        s = len(seqA[-7:]) - 1  # index of last frame of A in seq
        d = float(np.abs(seqB[0] - seqA[-1]).mean())
        res = {"frame_diff": round(d, 3), "typical_diff_median": round(med, 3), "ratio": round(d / med, 1),
               "luma_a_last": round(float(seqA[-1].mean()), 2), "luma_b_first": round(float(seqB[0].mean()), 2),
               "luma_delta": round(float(seqB[0].mean() - seqA[-1].mean()), 2), "box_motion": {}}
        res["a"], res["b"] = ma, mb
        res["box_motion"]["frame"] = [round(float(x), 3) for x in np.abs(np.diff(seq, axis=0)).mean(axis=(1, 2))]
        for nm, bx in boxes:
            if bx:
                res["box_motion"][nm] = [round(float(x), 3) for x in box_motion(seq, bx)]
        res["box_motion_note"] = f"index {s} is the seam step (prev last -> next first); 6 steps before/after"
        seams[label] = res

    if a.prev:
        pf, pe = decode_gray(a.prev, aw, ah, a.prev_range)
        if pe: flags["decode_errors"] = sorted(set(flags["decode_errors"] + ["[prev] " + x for x in pe.splitlines()]))
        pfps = probe(a.prev)[2]
        seam("prev_to_this", pf, frames, [("hand_box", hbs), ("face_box", fbs)],
             side(a.prev, a.prev_range, len(pf), pfps, "last"), side(a.video, rng, N, fps, "first"))
    if a.next:
        nf, ne = decode_gray(a.next, aw, ah, a.next_range)
        if ne: flags["decode_errors"] = sorted(set(flags["decode_errors"] + ["[next] " + x for x in ne.splitlines()]))
        nfps = probe(a.next)[2]
        seam("this_to_next", frames, nf, [("hand_box", hbs), ("face_box", fbs)],
             side(a.video, rng, N, fps, "last"), side(a.next, a.next_range, len(nf), nfps, "first"))
    flags["seam"] = seams

    # ---- images ----
    # contact sheet
    cw = 320
    ch = int(round(cw * H / W / 2) * 2)
    tt = [i * a.interval for i in range(int((N - 1) / fps / a.interval) + 1)]
    ci = [min(N - 1, int(round(t * fps))) for t in tt] + [N - 1]
    ci = sorted(set(ci))
    ims = extract(a.video, rng, ci, f"scale={cw}:{ch}", cw, ch)
    cols = 4
    rows = (len(ci) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    f = font(18)
    for n, i in enumerate(ci):
        if i not in ims: continue
        x, y = (n % cols) * cw, (n // cols) * ch
        sheet.paste(ims[i], (x, y))
        lab = f"{ts(i/fps)}  #{i}"
        d.rectangle([x, y, x + 150, y + 24], fill=(0, 0, 0))
        d.text((x + 4, y + 1), lab, font=f, fill=(255, 255, 0))
    sheet.save(out / "contact.jpg", quality=90)

    # first/last overlay at full size: red = first frame, cyan = last frame (grey where they agree)
    fl = extract(a.video, rng, [0, N - 1], f"scale={W}:{H}", W, H)
    if 0 in fl and (N - 1) in fl:
        g0, g1 = np.asarray(fl[0].convert("L")), np.asarray(fl[N - 1].convert("L"))
        Image.fromarray(np.stack([g0, g1, g1], -1)).save(out / "first_last.jpg", quality=90)

    # faces
    if fb:
        bw, bh = fb[2] - fb[0], fb[3] - fb[1]
        fi = [0, int((N - 1) * .25), int((N - 1) * .5), int((N - 1) * .75), N - 1]
        fl = ["시작", "25%", "50%", "75%", "끝"]
        crops = extract(a.video, rng, fi, f"crop={bw}:{bh}:{fb[0]}:{fb[1]}", bw, bh)
        tw = 300
        th = int(tw * bh / bw)
        items = [(crops[i].resize((tw, th)), f"{l} {ts(i/fps)}") for i, l in zip(fi, fl) if i in crops]
        if a.ref_face and os.path.exists(a.ref_face):
            r = Image.open(a.ref_face).convert("RGB")
            r = r.resize((tw, int(tw * r.height / r.width)))
            items.append((r, "기준 얼굴(ref)"))
        mh = max(im.height for im, _ in items)
        fs = Image.new("RGB", (tw * len(items), mh + 28), (20, 20, 20))
        d = ImageDraw.Draw(fs)
        for n, (im, lab) in enumerate(items):
            fs.paste(im, (n * tw, 28))
            d.text((n * tw + 6, 3), lab, font=font(18), fill=(255, 255, 0))
        fs.save(out / "faces.jpg", quality=92)

    # metrics.json
    def L(x, r=3): return [round(float(v), r) for v in x]
    metrics = {
        "video": str(a.video), "range_ms": rng, "fps": round(fps, 3), "frames": N,
        "duration_s": round(N / fps, 3), "size": [W, H], "analysis_size": [aw, ah],
        "boxes_original": {"face": fb, "hand": hb}, "boxes_analysis": {"face": fbs, "hand": hbs},
        "series": {
            "luma": L(luma, 2), "frame_diff": L(fdiff),
            "hand_motion": L(hand_m) if hand_m is not None else None,
            "face_motion": L(face_m) if face_m is not None else None,
            "face_centroid_x": L(cx, 2) if cx is not None else None,
            "face_centroid_y": L(cy, 2) if cy is not None else None,
        },
        "series_note": "diff/motion 배열의 k번째 값은 프레임 k -> k+1 (시간 (k+1)/fps)",
        "flags": flags,
        "note": "자동 후보이며 판정이 아님",
    }
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf8")

    # metrics.png
    panels = [("평균 밝기(luma)", luma, 0), ("프레임 차이(전체)", fdiff, 1)]
    if hand_m is not None: panels.append(("손 박스 움직임", hand_m, 1))
    if face_m is not None: panels.append(("얼굴 박스 움직임", face_m, 1))
    if cx is not None:
        panels.append(("얼굴 박스 밝은 픽셀 중심 x (축소 px)", cx, 0))
        panels.append(("얼굴 박스 밝은 픽셀 중심 y (축소 px)", cy, 0))
    PW, PH, M = 1000, 150, 40
    img = Image.new("RGB", (PW + 2 * M, len(panels) * (PH + 30) + 10), (255, 255, 255))
    d = ImageDraw.Draw(img)
    fo = font(14)
    spans = [(f_["t"][0], f_["t"][1], (255, 200, 200)) for f_ in flags["freeze"]]
    for p, (title, v, off) in enumerate(panels):
        y0 = 10 + p * (PH + 30) + 20
        d.text((M, y0 - 20), title, font=fo, fill=(0, 0, 0))
        d.rectangle([M, y0, M + PW, y0 + PH], outline=(150, 150, 150))
        v = np.asarray(v, float)
        tn = len(v)
        # time axis: diff series are shifted by one frame
        t0 = off / fps
        T = N / fps
        for s0, s1, col in spans:
            d.rectangle([M + s0 / T * PW, y0 + 1, M + s1 / T * PW, y0 + PH - 1], fill=col)
        lo, hi = float(v.min()), float(v.max())
        if hi - lo < 1e-6: hi = lo + 1
        pts = [(M + (t0 + k / fps) / T * PW, y0 + PH - (x - lo) / (hi - lo) * (PH - 4) - 2) for k, x in enumerate(v)]
        d.line(pts, fill=(30, 70, 200), width=2)
        d.text((M - 38, y0), f"{hi:.1f}", font=fo, fill=(80, 80, 80))
        d.text((M - 38, y0 + PH - 14), f"{lo:.1f}", font=fo, fill=(80, 80, 80))
        for s in range(int(T) + 1):
            xx = M + s / T * PW
            d.line([xx, y0 + PH, xx, y0 + PH + 4], fill=(0, 0, 0))
            d.text((xx - 6, y0 + PH + 6), f"{s}s", font=fo, fill=(0, 0, 0))
    img.save(out / "metrics.png")

    # report.md
    R = [f"# 영상 검수 자동 증거: {Path(a.video).name}", "",
         "> **이 표의 항목은 모두 자동 탐지 후보이며 판정이 아니다.** 동작의 자연스러움(멈칫, 방향 바뀜, 얼굴 변화 등)은 반드시 영상을 직접 재생해서 판단한다.",
         "", f"- 길이 {N/fps:.2f}s, {N}프레임, {fps:.2f}fps, {W}x{H}" + (f", 사용 구간 {rng[0]}-{rng[1]}ms (시간은 구간 시작=0)" if rng else ""),
         f"- 얼굴 박스 {fb}, 손 박스 {hb}", f"- 파일: contact.jpg, first_last.jpg(빨강=첫 프레임, 청록=끝 프레임)" + (", faces.jpg" if fb else "") + ", metrics.png, metrics.json", "",
         "| 플래그 | 시간(s) | 수치 |", "|---|---|---|"]
    rows_ = []
    for x in flags["freeze"]:
        rows_.append(("freeze(멈칫)", f"{x['t'][0]}-{x['t'][1]}", f"{x['where']} 움직임 {x['motion_in_run']} (p90 {x['p90_motion']}), {x['duration_s']}s"))
    for x in flags["direction_reversal"]:
        rows_.append(("direction_reversal", ", ".join(map(str, x["turn_times_s"])), f"{x['axis']}축 방향 전환 {x['count']}회, 진폭 {x['swing_px_analysis']}px(원본 {x['swing_px_original']}px)"))
    for x in flags["brightness_drift"]:
        rows_.append(("brightness_drift", str(x.get("t", "전체")), f"{x['kind']} 변화 {x['delta']}" + (f" ({x['start']}->{x['end']})" if 'start' in x else "")))
    for x in flags["spike"]:
        rows_.append(("spike", str(x["t"]), f"프레임 차이 {x['diff']} (중앙값의 {x['ratio']}배)"))
    for x in flags["black_or_frozen_frames"]:
        rows_.append((x["kind"], f"{x['t'][0]}-{x['t'][1]}", str(x.get("luma", x.get("diff")))))
    for x in flags["camera_drift"]:
        rows_.append(("camera_drift", f"{x['t'][0]}-{x['t'][1]}", f"화면 이동 {x['shift_px_original']}px(원본), 확대 {x['zoom']:+.3f} — first_last.jpg 확인"))
    for k_, s_ in seams.items():
        rows_.append((f"seam {k_}", "-", f"프레임 차이 {s_['frame_diff']} (평소 중앙값 {s_['typical_diff_median']}의 {s_['ratio']}배), 밝기 {s_['luma_a_last']}->{s_['luma_b_first']} (차 {s_['luma_delta']})"))
    if flags["decode_errors"]:
        rows_.append(("decode_errors", "-", "; ".join(flags["decode_errors"])[:300]))
    if not rows_:
        rows_.append(("(후보 없음)", "-", "자동 탐지된 후보 없음 - 그래도 영상을 직접 봐야 한다"))
    R += [f"| {p} | {q} | {r} |" for p, q, r in rows_]
    R += ["", "## 기준값", f"- 평균 밝기 {luma.mean():.2f} (처음 {luma[:k].mean():.2f} -> 끝 {luma[-k:].mean():.2f}), 프레임 차이 중앙값 {med:.3f}",
          "- 임계값: freeze = 박스 움직임 < 0.5*p90 이 0.4s 이상 + 앞뒤로 0.6*p90 초과 움직임; reversal = 진폭 원본 4px 초과 방향 전환 2회 이상; drift = 전체 2.0 초과(마지막 16프레임은 1.0 초과); spike = 중앙값 3배 초과; camera_drift = 첫 프레임 대비 사분면 위상 상관으로 이동 6px 또는 확대 3% 초과",
          "- 카메라 이동, 번개, 의도적 정지는 지표를 흔들 수 있다. 위 값으로 자동 탈락시키지 않는다."]
    (out / "report.md").write_text("\n".join(R) + "\n", encoding="utf8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else list(v) if isinstance(v, dict) else v) for k, v in flags.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
