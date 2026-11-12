"""Run: python tests/test_ref_probe.py  (from scripts/, no pytest needed). Needs ffmpeg on PATH.

Synthetic clips with known camera motion: the crop window over a big texture moves, so the
expected direction of the picture content is known exactly.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ref_probe  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="ref_probe_test_"))


def texture(path, w=1600, h=1600, seed=1):
    rng = np.random.default_rng(seed)
    small = rng.random((h // 16, w // 16, 3))
    im = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    fine = (rng.random((h, w, 1)) * 60).astype(np.int16)
    a = np.clip(np.asarray(im).astype(np.int16) + fine - 30, 0, 255).astype(np.uint8)
    Image.fromarray(a).save(path)
    return path


TEX = texture(TMP / "tex.png")
TEX2 = texture(TMP / "tex2.png", seed=7)


def clip(name, vf, src=TEX, dur=3):
    out = TMP / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "24", "-i", str(src), "-t", str(dur),
                    "-vf", vf + ",format=yuv420p", "-c:v", "libx264", "-crf", "18", str(out)], check=True)
    return out


def probe(path, *extra):
    r, _ = ref_probe.main([str(path), "--out", str(TMP / (Path(path).stem + "_out")), *extra])
    return r


def seg0(r):
    return r["motion"]["segments"][0]


def test_tilt_up_candidate():
    # window moves UP over the texture -> content moves DOWN in frame -> tilt up / pedestal up
    r = probe(clip("tilt_up", "crop=640:360:400:'800-t*100'"))
    s = seg0(r)
    assert s["status"] == "measured", s
    assert s["image_translation_frac"][1] > 0.3, s
    assert abs(s["image_translation_frac"][0]) < 0.05, s
    assert any("tilt up" in c for c in s["candidates"]), s["candidates"]


def test_tilt_down_candidate():
    r = probe(clip("tilt_down", "crop=640:360:400:'200+t*100'"))
    s = seg0(r)
    assert s["image_translation_frac"][1] < -0.3, s
    assert any("tilt down" in c for c in s["candidates"]), s["candidates"]


def test_pan_right_candidate():
    # window moves right -> content moves left -> pan right
    r = probe(clip("pan_right", "crop=640:360:'200+t*120':600"))
    s = seg0(r)
    assert s["image_translation_frac"][0] < -0.3, s
    assert any("pan right" in c for c in s["candidates"]), s["candidates"]


def test_push_in_candidate():
    # crop window shrinks around the centre, scaled back to 640x360 -> magnification grows
    vf = "crop=1600:900:0:350,zoompan=z='1+0.004*on':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=640x360:fps=24"
    s = seg0(probe(clip("push_in", vf)))
    assert s["status"] == "measured", s
    assert s["scale_change"] > 1.1, s
    assert any("push-in" in c for c in s["candidates"]), s["candidates"]


def test_slow_tilt_up_is_not_static():
    # 3초에 화면 높이의 약 8% (인접 프레임당 1px 미만) - 정수 px 상관이면 0으로 묻힌다
    s = seg0(probe(clip("slow_tilt", "crop=640:360:400:'800-t*10'")))
    assert s["status"] == "measured", s
    assert 0.05 < s["image_translation_frac"][1] < 0.12, s
    assert any("tilt up" in c for c in s["candidates"]), s["candidates"]


def test_slow_push_in_is_not_static():
    vf = "crop=1600:900:0:350,zoompan=z='1+0.001*on':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=640x360:fps=24"
    s = seg0(probe(clip("slow_push", vf)))
    assert s["scale_change"] > 1.03, s
    assert any("push-in" in c for c in s["candidates"]), s["candidates"]


def test_out_and_back_is_not_static():
    # 1.5초 동안 오른쪽으로 갔다가 1.5초 동안 원위치 - 순이동 0이지만 static 이 아니다
    r = probe(clip("out_back", "crop=640:360:'400+120*(0.75-abs(t-1.5)/2)*2':600"))
    s = seg0(r)
    assert abs(s["image_translation_frac"][0]) < 0.05, s
    assert s["path_length_frac"][0] > 0.3, s
    assert s["direction_changes"][0] >= 1, s
    assert not any("static" in c for c in s["candidates"]), s["candidates"]
    assert any("돌아옴" in c for c in s["candidates"]), s["candidates"]


def test_candidates_unit_out_and_back():
    c = ref_probe.candidates(0.0, 0.0, 1.0, path=(0.2, 0.0), rev=(1, 0))
    assert not any("static" in x for x in c) and any("돌아옴" in x for x in c), c


def test_static_and_letterbox_detected():
    r = probe(clip("letterbox", "crop=640:270:400:400,pad=640:360:0:45:black"))
    c = r["conditions"]["analysis_crop"]
    assert c["mode"] == "auto_letterbox", c
    top, bot = c["box_source_px"][1], c["box_source_px"][3]
    assert 40 <= top <= 50 and 310 <= bot <= 320, c
    assert any("static" in x for x in seg0(r)["candidates"]), seg0(r)


def test_manual_crop_overrides_letterbox():
    r = probe(TMP / "letterbox.mp4", "--crop", "0,0,640,360")
    assert r["conditions"]["analysis_crop"]["mode"] == "manual"


def test_crop_outside_frame_rejected():
    for box in ("0,0,1280,360", "-10,0,600,360"):
        try:
            probe(TMP / "letterbox.mp4", f"--crop={box}")
        except SystemExit:
            continue
        raise AssertionError(f"crop {box} accepted")


def test_cut_splits_segments():
    a = clip("cut_a", "crop=640:360:400:400", TEX, 1.5)
    b = clip("cut_b", "crop=640:360:400:400", TEX2, 1.5)
    lst = TMP / "list.txt"
    lst.write_text(f"file '{a.as_posix()}'\nfile '{b.as_posix()}'\n")
    out = TMP / "cut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                   check=True)
    r = probe(out)
    assert len(r["motion"]["cuts_after_s"]) == 1, r["motion"]["cuts_after_s"]
    assert abs(r["motion"]["cuts_after_s"][0] - 1.5) < 0.2
    assert len(r["motion"]["segments"]) == 2


def test_flat_frame_is_unknown():
    flat = TMP / "flat.png"
    Image.new("RGB", (1600, 1600), (40, 40, 40)).save(flat)
    s = seg0(probe(clip("flat", "crop=640:360:400:'800-t*100'", flat)))
    assert s["status"] == "unknown", s


def test_image_mood_only():
    r = probe(TEX)
    assert r["motion"] is None
    assert len(r["mood"]["dominant_colors"]) == 5
    assert 0 < r["mood"]["luma_mean"] < 255


def test_compare_report():
    ref_probe.main([str(TMP / "tilt_up.mp4"), "--out", str(TMP / "cmp"), "--compare", str(TMP / "tilt_down.mp4")])
    rep = (TMP / "cmp" / "report.md").read_text(encoding="utf-8")
    assert "실험 기능" in rep and "| 항목 | A" in rep


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:400])
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
