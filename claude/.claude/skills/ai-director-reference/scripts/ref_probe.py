#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ref_probe.py - 레퍼런스 영상/이미지 분석 증거 도구 (판정 아님).

사용법:
  python ref_probe.py <video|image> --out <dir> [--range IN_MS OUT_MS]
         [--crop x0,y0,x1,y1 | --no-crop] [--fps 12] [--step-s 0.5] [--frames 12] [--colors 5]
         [--compare <video|image> [--compare-range IN_MS OUT_MS] [--compare-crop x0,y0,x1,y1]]

출력(<dir>): contact.jpg(타임코드 접촉 시트, 분석 영역 표시), palette.png, probe.json, report.md
  --compare 를 주면 compare/ 아래 같은 출력과 report.md 의 나란히 비교 표(실험 기능, 판정 없음).

측정하는 것
  - 분위기: Rec.709 Y 휘도(평균, p5/p50/p95, 대비 p95-p5), HSV 채도 평균, 지배색 k개(비율).
  - 화면 움직임(영상만, 실험): 인접 샘플 프레임 사이 사분면 위상상관 → 화면 내용의 이동(px, 화면 대비 %)과
    확대 근사 지표(scale_change). 촬영 기법 이름(틸트업 등)은 "후보"로만 쓰고 사람이 확인한다.
    상관 피크 약함 / 사분면 불일치(이동+확대 모델 잔차 큼) / 컷 전환 → 해당 구간 unknown.
측정 조건(사용 구간, 원본·분석 해상도, 크롭, 색공간 가정, 재생 속도)은 probe.json conditions 에 모두 남긴다.
레터박스는 자동 감지하되(어두운 장면을 띠로 오인할 수 있음) 검출 영역을 기록하고 --crop/--no-crop 으로 고칠 수 있다.
의존성: ffmpeg/ffprobe(PATH), numpy, PIL. 공통 함수는 ai-director-consistency/scripts/review_video.py 에서 가져온다.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai-director-consistency" / "scripts"))
from review_video import font, probe, run, trim_args, ts  # noqa: E402

AW = 320                 # 분석 가로 폭(px)
PEAK_MIN = 0.06          # 위상상관 피크가 이보다 낮으면 그 쌍은 신뢰하지 않는다
RESID_MIN_PX = 1.0       # 사분면 잔차 허용(분석 px). max(이 값, 0.5*이동량) 넘으면 불일치
CUT_RATIO, CUT_ABS = 5.0, 25.0   # 인접 프레임 차가 중앙값의 5배 이상이면서 25 이상이면 컷
VALID_MIN = 0.6          # 구간의 신뢰 쌍 비율이 이보다 낮으면 구간 움직임 unknown
MOVE_MIN_FRAC = 0.03     # 누적 이동이 화면의 3% 미만이면 "이동 없음 수준"
SCALE_MIN = 0.03         # 누적 확대 근사가 ±3% 미만이면 "확대 변화 없음 수준"
STEP_NOTE = "측정 간격보다 짧은 흔들림은 못 잡음: --step-s 를 줄여 다시 잰다"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# ---------- 입력 ----------

def is_image(path):
    return Path(path).suffix.lower() in IMG_EXT


def load_media(path, rng, fps):
    """returns dict(kind, src_w, src_h, src_fps, frames[N,H,W,3] uint8 at AW width, times_s)"""
    if is_image(path):
        im = Image.open(path).convert("RGB")
        w, h = im.size
        ah = max(2, round(h * AW / w / 2) * 2)
        arr = np.asarray(im.resize((AW, ah), Image.BILINEAR))[None]
        return {"kind": "image", "src_w": w, "src_h": h, "src_fps": None, "frames": arr, "times_s": [0.0]}
    w, h, src_fps, err = probe(path)
    ah = max(2, round(h * AW / w / 2) * 2)
    r = run(["ffmpeg", "-v", "error", *trim_args(rng), "-i", str(path), "-vf", f"fps={fps},scale={AW}:{ah}",
             "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    a = np.frombuffer(r.stdout, np.uint8)
    n = a.size // (AW * ah * 3)
    if n == 0:
        sys.exit(f"no frames decoded from {path}: {r.stderr.decode('utf8', 'replace')[:300]}")
    frames = a[:n * AW * ah * 3].reshape(n, ah, AW, 3)
    return {"kind": "video", "src_w": w, "src_h": h, "src_fps": round(src_fps, 3), "frames": frames,
            "times_s": [i / fps for i in range(n)]}


def luma(rgb):
    rgb = rgb.astype(np.float32)
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def detect_letterbox(frames, dark=18.0, still=10.0):
    """top/bottom/left/right bars that stay dark and flat in EVERY sampled frame. returns [x0,y0,x1,y1]."""
    y = luma(frames)                      # N,H,W
    rows_max = y.max(axis=(0, 2))         # brightest value each row reaches across frames
    rows_std = y.std(axis=2).max(axis=0)
    cols_max = y.max(axis=(0, 1))
    cols_std = y.std(axis=1).max(axis=0)
    H, W = y.shape[1:]

    def edge(vals, stds, n):
        k = 0
        while k < n // 3 and vals[k] < dark and stds[k] < still:
            k += 1
        return k
    t = edge(rows_max, rows_std, H)
    b = edge(rows_max[::-1], rows_std[::-1], H)
    l = edge(cols_max, cols_std, W)
    r = edge(cols_max[::-1], cols_std[::-1], W)
    return [l, t, W - r, H - b]


# ---------- 분위기 ----------

def kmeans_colors(pix, k, iters=12, seed=0):
    rng = np.random.default_rng(seed)
    pix = pix.astype(np.float32)
    if len(pix) > 20000:
        pix = pix[rng.choice(len(pix), 20000, replace=False)]
    # k-means++ 초기화
    cent = [pix[rng.integers(len(pix))]]
    for _ in range(1, k):
        d = np.min(((pix[:, None] - np.array(cent)[None]) ** 2).sum(-1), axis=1)
        p = d / d.sum() if d.sum() > 0 else None
        cent.append(pix[rng.choice(len(pix), p=p)])
    cent = np.array(cent)
    for _ in range(iters):
        lab = ((pix[:, None] - cent[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            if (lab == j).any():
                cent[j] = pix[lab == j].mean(0)
    lab = ((pix[:, None] - cent[None]) ** 2).sum(-1).argmin(1)
    share = np.bincount(lab, minlength=k) / len(lab)
    order = np.argsort(-share)
    return [{"hex": "#%02x%02x%02x" % tuple(int(round(v)) for v in cent[j]), "share": round(float(share[j]), 3)}
            for j in order]


def mood_stats(frames, k):
    y = luma(frames)
    rgb = frames.astype(np.float32) / 255.0
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    p5, p50, p95 = np.percentile(y, [5, 50, 95])
    return {"luma_mean": round(float(y.mean()), 1), "luma_p5": round(float(p5), 1), "luma_p50": round(float(p50), 1),
            "luma_p95": round(float(p95), 1), "contrast_p95_p5": round(float(p95 - p5), 1),
            "saturation_mean": round(float(sat.mean()), 3),
            "dominant_colors": kmeans_colors(frames.reshape(-1, 3), k)}


# ---------- 화면 움직임 ----------

def phase_corr(a, b):
    """(dy, dx, peak): b ≈ a shifted by (dy, dx). peak = 정규화 위상상관 최대값(0~1)."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A, B = np.fft.fft2((a - a.mean()) * win), np.fft.fft2((b - b.mean()) * win)
    R = B * np.conj(A)
    R /= np.abs(R) + 1e-9
    c = np.fft.ifft2(R).real
    py, px = np.unravel_index(c.argmax(), c.shape)
    h, w = a.shape

    def sub(cm, c0, cp):  # 포물선 보간으로 1px 미만 이동까지 잡는다(느린 푸시인·틸트)
        den = cm - 2 * c0 + cp
        return 0.0 if abs(den) < 1e-12 else float(np.clip(0.5 * (cm - cp) / den, -0.5, 0.5))
    fy = py + sub(c[(py - 1) % h, px], c[py, px], c[(py + 1) % h, px])
    fx = px + sub(c[py, (px - 1) % w], c[py, px], c[py, (px + 1) % w])
    return (fy if fy < h / 2 else fy - h), (fx if fx < w / 2 else fx - w), float(c.max())


def pair_motion(a, b):
    """이동(tx,ty)+확대(s) 모델을 사분면 변위 4개에 맞춘다. s: 화면 중심 기준 상대 확대(+면 확대)."""
    h, w = a.shape
    h2, w2 = h // 2, w // 2
    quads = {"tl": (0, h2, 0, w2), "tr": (0, h2, w2, w), "bl": (h2, h, 0, w2), "br": (h2, h, w2, w)}
    rows, rhs, peaks = [], [], []
    for (y0, y1, x0, x1) in quads.values():
        dy, dx, pk = phase_corr(a[y0:y1, x0:x1], b[y0:y1, x0:x1])
        cx, cy = (x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - h / 2
        rows += [[1, 0, cx], [0, 1, cy]]
        rhs += [dx, dy]
        peaks.append(pk)
    M, v = np.array(rows, float), np.array(rhs, float)
    sol, *_ = np.linalg.lstsq(M, v, rcond=None)
    resid = float(np.sqrt(np.mean((M @ sol - v) ** 2)))
    tx, ty, s = (float(x) for x in sol)
    return {"tx": tx, "ty": ty, "s": s, "resid": resid, "peak_min": min(peaks)}


def motion_analysis(frames, fps, step_s=0.5):
    """컷은 인접 프레임 차로 찾고, 움직임은 컷 사이 구간에서 step_s 간격 프레임 쌍을 이어 누적한다
    (인접 프레임끼리는 느린 무빙이 1px 미만이라 묻힌다)."""
    g = luma(frames)
    N, H, W = g.shape
    if N < 2:
        return None
    diff = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))
    med = float(np.median(diff)) if len(diff) else 0.0
    cuts = [i for i, d in enumerate(diff) if d >= CUT_ABS and d >= CUT_RATIO * max(med, 1e-6)]
    K = max(1, int(round(fps * step_s)))
    bounds = [-1] + cuts + [N - 1]
    segments, all_pairs = [], []
    for a, b in zip(bounds, bounds[1:]):
        lo, hi = a + 1, b              # 구간 프레임 lo..hi
        if hi <= lo:
            continue
        idx = list(range(lo, hi + 1, K))
        if idx[-1] != hi:
            idx.append(hi)
        seg = []
        for i, j in zip(idx, idx[1:]):
            m = pair_motion(g[i], g[j])
            move = float(np.hypot(m["tx"], m["ty"]))
            reason = None
            if m["peak_min"] < PEAK_MIN:
                reason = "weak_peak"
            elif m["resid"] > max(RESID_MIN_PX, 0.5 * move):
                reason = "quadrant_disagree"
            m.update({"i": i, "j": j, "t_s": round(i / fps, 3), "dt_s": round((j - i) / fps, 3),
                      "valid": reason is None, "reason": reason})
            seg.append(m)
        all_pairs += seg
        valid = [p for p in seg if p["valid"]]
        frac = len(valid) / len(seg)
        dur = (hi - lo) / fps
        out = {"start_s": round(lo / fps, 3), "end_s": round(hi / fps, 3),
               "pairs": len(seg), "valid_fraction": round(frac, 2),
               "unknown_reasons": {r: sum(1 for p in seg if p["reason"] == r)
                                   for r in ("weak_peak", "quadrant_disagree") if any(p["reason"] == r for p in seg)}}
        if frac < VALID_MIN or not valid:
            out.update({"status": "unknown", "candidates": []})
        else:
            # 관측값: 유효 쌍만 더한 값. 추정값: 무효 쌍을 유효 쌍의 초당 평균으로 채운 값(구간 길이 왜곡 보정).
            vdt = sum(p["dt_s"] for p in valid)
            otx, oty = sum(p["tx"] for p in valid), sum(p["ty"] for p in valid)
            ols = sum(np.log1p(p["s"]) for p in valid)
            fill_dt = sum(p["dt_s"] for p in seg if not p["valid"])
            tx, ty = otx + otx / vdt * fill_dt, oty + oty / vdt * fill_dt
            scale = float(np.exp(ols + ols / vdt * fill_dt))
            # 총 이동(경로 길이)과 방향 바뀜: 순이동이 0이어도 왕복·흔들림이면 static 이 아니다
            path = [sum(abs(p["tx"]) for p in valid) / W, sum(abs(p["ty"]) for p in valid) / H]
            rev = [reversal_count([p[k] for p in valid], 0.5) for k in ("tx", "ty")]
            out.update({"status": "measured",
                        "image_translation_px": [round(tx, 1), round(ty, 1)],
                        "image_translation_frac": [round(tx / W, 3), round(ty / H, 3)],
                        "translation_frac_per_s": [round(tx / W / dur, 3), round(ty / H / dur, 3)],
                        "observed_translation_frac": [round(otx / W, 3), round(oty / H, 3)],
                        "estimated_fill_s": round(fill_dt, 3),
                        "path_length_frac": [round(v, 3) for v in path],
                        "direction_changes": rev,
                        "scale_change": round(scale, 3),
                        "candidates": candidates(tx / W, ty / H, scale, path, rev)})
        segments.append(out)
    return {"sample_fps": fps, "pair_step_s": round(K / fps, 3), "analysis_size": [W, H],
            "cuts_after_s": [round((c + 1) / fps, 3) for c in cuts], "segments": segments,
            "pairs": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items()} for p in all_pairs]}


def reversal_count(v, min_px):
    """부호가 바뀐 횟수(|값| < min_px 인 쌍은 건너뜀)."""
    signs = [np.sign(x) for x in v if abs(x) >= min_px]
    return int(sum(1 for a, b in zip(signs, signs[1:]) if a != b))


def candidates(fx, fy, scale, path=(0.0, 0.0), rev=(0, 0)):
    """화면 내용 이동 → 가능한 촬영 기법 후보(여럿). 사람이 영상을 보고 확인해야 한다."""
    out = []
    for name, net, pl, r in (("가로", fx, path[0], rev[0]), ("세로", fy, path[1], rev[1])):
        if pl >= MOVE_MIN_FRAC and (r > 0 or pl > 2 * abs(net) + MOVE_MIN_FRAC):
            out.append(f"{name} 방향으로 갔다 돌아옴(총 이동 화면의 {pl*100:.0f}%, 순이동 {net*100:+.0f}%, "
                       f"방향 바뀜 {r}회) → 왕복 무빙·흔들림·핸드헬드 후보, 영상 확인 필요")
    if fy >= MOVE_MIN_FRAC:
        out.append("화면 내용이 아래로 이동 → tilt up 또는 pedestal/crane up 후보")
    elif fy <= -MOVE_MIN_FRAC:
        out.append("화면 내용이 위로 이동 → tilt down 또는 pedestal/crane down 후보")
    if fx >= MOVE_MIN_FRAC:
        out.append("화면 내용이 오른쪽으로 이동 → pan left 또는 truck left 후보")
    elif fx <= -MOVE_MIN_FRAC:
        out.append("화면 내용이 왼쪽으로 이동 → pan right 또는 truck right 후보")
    if scale >= 1 + SCALE_MIN:
        out.append("확대 근사 증가 → push-in(dolly-in) 또는 zoom-in 후보")
    elif scale <= 1 - SCALE_MIN:
        out.append("확대 근사 감소 → pull-out(dolly-out) 또는 zoom-out 후보")
    if not out:
        out.append(f"전역 이동·확대가 작음 → static/locked-off 후보(피사체만 움직였을 수 있음, "
                   f"{STEP_NOTE})")
    return out


# ---------- 출력 ----------

def contact_sheet(frames, times, crop, n, path):
    N = len(frames)
    idx = sorted(set(np.linspace(0, N - 1, min(n, N)).round().astype(int)))
    h, w = frames.shape[1:3]
    cols = min(4, len(idx))
    rows = (len(idx) + cols - 1) // cols
    pad = 22
    sheet = Image.new("RGB", (cols * w, rows * (h + pad)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    f = font(13)
    for k, i in enumerate(idx):
        x, y = (k % cols) * w, (k // cols) * (h + pad)
        sheet.paste(Image.fromarray(frames[i]), (x, y + pad))
        d.text((x + 4, y + 3), ts(times[i]), fill=(230, 230, 230), font=f)
        if crop != [0, 0, w, h]:
            d.rectangle([x + crop[0], y + pad + crop[1], x + crop[2] - 1, y + pad + crop[3] - 1], outline=(255, 200, 0))
    sheet.save(path, quality=90)
    return [round(times[i], 3) for i in idx]


def palette_png(colors, path):
    W, H = 600, 80
    im = Image.new("RGB", (W, H + 20), (255, 255, 255))
    d = ImageDraw.Draw(im)
    x = 0
    for c in colors:
        cw = max(1, round(W * c["share"]))
        d.rectangle([x, 0, x + cw, H], fill=c["hex"])
        d.text((x + 3, H + 3), f"{c['hex']} {c['share']*100:.0f}%", fill=(0, 0, 0), font=font(11))
        x += cw
    im.save(path)


def parse_box(s):
    b = [int(float(v)) for v in s.split(",")]
    if len(b) != 4 or b[2] <= b[0] or b[3] <= b[1]:
        sys.exit(f"bad crop {s!r}: need x0,y0,x1,y1 with x1>x0, y1>y0 (source pixels)")
    return b


def analyse(media, rng, crop_arg, no_crop, fps, n_frames, k, out, step_s=0.5):
    out.mkdir(parents=True, exist_ok=True)
    m = load_media(media, rng, fps)
    frames = m["frames"]
    H, W = frames.shape[1:3]
    sx = W / m["src_w"]
    if crop_arg:
        b = parse_box(crop_arg)
        if b[0] < 0 or b[1] < 0 or b[2] > m["src_w"] or b[3] > m["src_h"]:
            sys.exit(f"--crop {b} is outside the source frame {m['src_w']}x{m['src_h']}")
        crop = [round(b[0] * sx), round(b[1] * sx), min(W, round(b[2] * sx)), min(H, round(b[3] * sx))]
        crop_mode = "manual"
    elif no_crop:
        crop, crop_mode = [0, 0, W, H], "none"
    else:
        crop = detect_letterbox(frames)
        crop_mode = "auto_letterbox" if crop != [0, 0, W, H] else "auto_none_found"
    x0, y0, x1, y1 = crop
    if x1 - x0 < 16 or y1 - y0 < 16:
        sys.exit(f"crop {crop} too small; pass --crop or --no-crop")
    fc = frames[:, y0:y1, x0:x1]
    h = hashlib.sha256()
    with open(media, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    res = {
        "media": str(media), "media_sha256": h.hexdigest(),
        "conditions": {
            "kind": m["kind"], "range_ms": rng, "source_size": [m["src_w"], m["src_h"]], "source_fps": m["src_fps"],
            "analysis_size": [W, H], "analysis_crop": {"mode": crop_mode, "box_analysis_px": crop,
                                                       "box_source_px": [round(v / sx) for v in crop]},
            "aspect_after_crop": round((x1 - x0) / (y1 - y0), 3),
            "color_space": "ffmpeg/PIL 기본 변환 RGB, BT.709 가정(색 관리 안 함). 휘도는 Rec.709 Y(감마 적용 값)",
            "playback_speed": 1.0, "sample_fps": fps if m["kind"] == "video" else None,
            "frames_analysed": int(len(frames)),
        },
        "mood": mood_stats(fc, k),
        "motion": motion_analysis(fc, fps, step_s) if m["kind"] == "video" else None,
    }
    res["contact_times_s"] = contact_sheet(frames, m["times_s"], crop, n_frames, out / "contact.jpg")
    palette_png(res["mood"]["dominant_colors"], out / "palette.png")
    (out / "probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def summary_rows(r):
    mo = r["mood"]
    rows = [("휘도 평균 / p5·p50·p95", f"{mo['luma_mean']} / {mo['luma_p5']}·{mo['luma_p50']}·{mo['luma_p95']}"),
            ("대비 p95-p5", mo["contrast_p95_p5"]), ("채도 평균", mo["saturation_mean"]),
            ("지배색", " ".join(f"{c['hex']}({c['share']*100:.0f}%)" for c in mo["dominant_colors"]))]
    if r["motion"]:
        for j, s in enumerate(r["motion"]["segments"]):
            tag = f"구간{j+1} {s['start_s']}–{s['end_s']}s"
            if s["status"] == "unknown":
                rows.append((tag, f"unknown (신뢰 쌍 {s['valid_fraction']*100:.0f}%, {s['unknown_reasons']})"))
            else:
                fx, fy = s["image_translation_frac"]
                rows.append((tag, f"이동 x {fx*100:+.1f}% y {fy*100:+.1f}% (화면 대비), 확대 근사 {s['scale_change']}, "
                                  f"신뢰 쌍 {s['valid_fraction']*100:.0f}% · 후보: " + "; ".join(s["candidates"])))
    return rows


def write_report(out, r, cmp=None):
    c = r["conditions"]
    L = ["# ref_probe 보고서", "",
         "> 자동 측정 증거다. 촬영 기법·분위기 판정이 아니다. 후보 해석은 영상을 직접 보고 확인한 뒤 references[].observed 에 기록한다.", "",
         f"- 파일: `{r['media']}`  종류: {c['kind']}  구간(ms): {c['range_ms']}",
         f"- 원본 {c['source_size'][0]}x{c['source_size'][1]} @ {c['source_fps']} fps → 분석 {c['analysis_size'][0]}px 폭, "
         f"샘플 {c['sample_fps']} fps, 프레임 {c['frames_analysed']}",
         f"- 분석 영역: {c['analysis_crop']['mode']} 원본 px {c['analysis_crop']['box_source_px']} (크롭 후 화면비 {c['aspect_after_crop']})",
         f"- 색: {c['color_space']}  재생 속도: {c['playback_speed']} (보정 없음)", ""]
    if r["motion"] and r["motion"]["cuts_after_s"]:
        L.append(f"- 컷 전환 감지(초): {r['motion']['cuts_after_s']}")
        L.append("")
    if cmp is None:
        L += ["| 항목 | 값 |", "|---|---|"] + [f"| {a} | {b} |" for a, b in summary_rows(r)]
    else:
        L += ["## 비교 (실험 기능 · 판정 없음)", "",
              f"- B: `{cmp['media']}` 구간 {cmp['conditions']['range_ms']} 분석 영역 {cmp['conditions']['analysis_crop']['mode']} "
              f"{cmp['conditions']['analysis_crop']['box_source_px']} 화면비 {cmp['conditions']['aspect_after_crop']}",
              "- 화면비·크롭·구간이 다르면 수치를 그대로 비교하지 않는다.", "",
              "| 항목 | A (레퍼런스) | B (비교 대상) |", "|---|---|---|"]
        ra, rb = summary_rows(r), summary_rows(cmp)
        for i in range(max(len(ra), len(rb))):
            a = ra[i] if i < len(ra) else ("", "")
            b = rb[i] if i < len(rb) else ("", "")
            L.append(f"| {a[0] or b[0]} | {a[1]} | {b[1]} |")
    L += ["", "파일: contact.jpg, palette.png, probe.json" + (", compare/" if cmp else "")]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media")
    ap.add_argument("--out", required=True)
    ap.add_argument("--range", nargs=2, type=int, metavar=("IN_MS", "OUT_MS"))
    ap.add_argument("--crop", help="x0,y0,x1,y1 (원본 px). 레터박스 자동 감지 대신 사용")
    ap.add_argument("--no-crop", action="store_true", help="레터박스 감지 끄기(전체 화면)")
    ap.add_argument("--fps", type=float, default=12.0, help="분석 샘플 fps (기본 12)")
    ap.add_argument("--step-s", type=float, default=0.5, help="움직임 측정 프레임 쌍 간격(초, 기본 0.5)")
    ap.add_argument("--frames", type=int, default=12, help="접촉 시트 칸 수 (기본 12)")
    ap.add_argument("--colors", type=int, default=5)
    ap.add_argument("--compare")
    ap.add_argument("--compare-range", nargs=2, type=int, metavar=("IN_MS", "OUT_MS"))
    ap.add_argument("--compare-crop")
    a = ap.parse_args(argv)
    if a.range and a.range[1] <= a.range[0]:
        sys.exit("--range: OUT_MS must be > IN_MS")
    out = Path(a.out)
    r = analyse(a.media, a.range, a.crop, a.no_crop, a.fps, a.frames, a.colors, out, a.step_s)
    cmp = None
    if a.compare:
        cmp = analyse(a.compare, a.compare_range, a.compare_crop, a.no_crop, a.fps, a.frames, a.colors, out / "compare",
                      a.step_s)
    write_report(out, r, cmp)
    print(f"wrote {out/'report.md'}")
    return r, cmp


if __name__ == "__main__":
    main()
