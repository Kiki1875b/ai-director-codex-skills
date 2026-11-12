"""Face detailer for a finished Wan clip: crop the face region, upscale it, redraw it with the low-noise model at
that size (video-to-video, conditioned on the same crop of the first/last keys), shrink it back and paste it in
with a feathered edge. Fixes small faces in medium/wide shots, which the model has only a few latent cells for.

  python face_detail.py --video media/video/S2-5-vid-v5.mp4 --image start.png --end-image end.png \
      --box 384,14,752,286 --scale 2.48 --prompt "close-up of a young woman's face ..." \
      --out media/video/S2-5-vid-v5fd.mp4 [--steps 8 --start 5]

--box x0,y0,x1,y1 in 1280x720 video pixels: must cover the face for the whole clip (the camera is locked).
The upscaled crop is rounded to multiples of 16. Frame count must be 4n+1 (Wan latent).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import numpy as np
import requests
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wan_remote import NEG, UNETS  # noqa: E402


def read_frames(path, d):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", "scale=1280:720", os.path.join(d, "o%05d.png")],
                   check=True)
    return sorted(f for f in os.listdir(d) if f.startswith("o"))


def up(srv, data, name, kind):
    r = requests.post(f"{srv}/upload/image", files={"image": (name, data, kind)}, data={"overwrite": "true"}, timeout=300)
    r.raise_for_status()
    return r.json()["name"]


def png_bytes(im):
    import io
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--video", required=True)
    ap.add_argument("--image", required=True); ap.add_argument("--end-image")
    ap.add_argument("--box", required=True)
    ap.add_argument("--scale", type=float, default=2.5)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative-extra", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=8); ap.add_argument("--start", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--feather", type=int, default=18)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--fetch", help="prompt_id of a finished detail job: skip queueing, only download and paste back")
    a = ap.parse_args()
    srv = a.server.rstrip("/")
    x0, y0, x1, y1 = map(int, a.box.split(","))
    cw, ch = x1 - x0, y1 - y0
    W, H = int(round(cw * a.scale / 16)) * 16, int(round(ch * a.scale / 16)) * 16
    tmp = tempfile.mkdtemp(prefix="fd_")
    names = read_frames(a.video, tmp)
    n = len(names)
    if (n - 1) % 4:
        names = names[:(n - 1) // 4 * 4 + 1]; n = len(names)
    for i, f in enumerate(names):
        Image.open(os.path.join(tmp, f)).convert("RGB").crop((x0, y0, x1, y1)).resize((W, H), Image.LANCZOS) \
            .save(os.path.join(tmp, f"c{i:05d}.png"))
    if a.fetch:
        pid, t0 = a.fetch, time.time()
        outs = requests.get(f"{srv}/history/{pid}", timeout=30).json()[pid]["outputs"]
        return paste(a, srv, tmp, names, outs, pid, t0, x0, y0, cw, ch)
    crop_mp4 = os.path.join(tmp, "crop.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "16", "-i", os.path.join(tmp, "c%05d.png"),
                    "-c:v", "libx264", "-crf", "1", "-pix_fmt", "yuv444p", crop_mp4], check=True)
    vid = up(srv, open(crop_mp4, "rb"), f"aidfd_{uuid.uuid4().hex[:8]}.mp4", "video/mp4")

    def key_crop(p):
        k = Image.open(p).convert("RGB").resize((1280, 720), Image.LANCZOS)
        return png_bytes(k.crop((x0, y0, x1, y1)).resize((W, H), Image.LANCZOS))
    st = up(srv, key_crop(a.image), f"aidfd_{uuid.uuid4().hex[:8]}.png", "image/png")
    neg = NEG + (", " + a.negative_extra if a.negative_extra else "")
    prefix = f"aid/{os.path.splitext(os.path.basename(a.out))[0]}"
    wf = {
        "2": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNETS["distill260412"][1]}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 5.0}},
        "7": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "8": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": a.prompt}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": neg}},
        "11": {"class_type": "LoadImage", "inputs": {"image": st}},
        "12": {"class_type": "WanImageToVideo", "inputs": {"positive": ["9", 0], "negative": ["10", 0], "vae": ["8", 0],
               "start_image": ["11", 0], "width": W, "height": H, "length": n, "batch_size": 1}},
        "30": {"class_type": "LoadVideo", "inputs": {"file": vid}},
        "31": {"class_type": "GetVideoComponents", "inputs": {"video": ["30", 0]}},
        "32": {"class_type": "VAEEncode", "inputs": {"pixels": ["31", 0], "vae": ["8", 0]}},
        "14": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["6", 0], "add_noise": "enable", "noise_seed": a.seed,
               "steps": a.steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0],
               "negative": ["12", 1], "latent_image": ["32", 0], "start_at_step": a.start, "end_at_step": 10000,
               "return_with_leftover_noise": "disable"}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["8", 0]}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix}},
    }
    if a.end_image:
        en = up(srv, key_crop(a.end_image), f"aidfd_{uuid.uuid4().hex[:8]}_end.png", "image/png")
        wf["17"] = {"class_type": "LoadImage", "inputs": {"image": en}}
        wf["12"]["class_type"] = "WanFirstLastFrameToVideo"
        wf["12"]["inputs"]["end_image"] = ["17", 0]
    r = requests.post(f"{srv}/prompt", json={"prompt": wf}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"queue failed {r.status_code}: {r.text[:2000]}")
    pid = r.json()["prompt_id"]
    print(f"queued {pid} face detail {W}x{H} x{n}", flush=True)
    t0 = time.time()
    while True:
        time.sleep(5)
        h = requests.get(f"{srv}/history/{pid}", timeout=30).json()
        if pid in h:
            if h[pid]["status"].get("status_str") != "success":
                sys.exit(f"failed: {json.dumps(h[pid]['status'].get('messages'), ensure_ascii=False)[:3000]}")
            outs = h[pid]["outputs"]; break
        if time.time() - t0 > 3 * 3600:
            sys.exit("timeout")
    paste(a, srv, tmp, names, outs, pid, t0, x0, y0, cw, ch)


def get(srv, img, tries=6):
    for i in range(tries):
        try:
            return requests.get(f"{srv}/view", params={"filename": img["filename"], "subfolder": img["subfolder"],
                                                        "type": img["type"]}, timeout=120).content
        except requests.exceptions.ConnectionError:
            time.sleep(3 * (i + 1))
    raise


def paste(a, srv, tmp, names, outs, pid, t0, x0, y0, cw, ch):
    n = len(names)
    x1, y1 = x0 + cw, y0 + ch
    imgs = sorted([i for o in outs.values() for i in o.get("images", [])], key=lambda x: x["filename"])
    mask = Image.new("L", (cw, ch), 0)
    f = a.feather
    mask.paste(255, (f, f, cw - f, ch - f)); mask = mask.filter(ImageFilter.GaussianBlur(f / 2))
    for i, (img, fn) in enumerate(zip(imgs, names)):
        b = get(srv, img)
        open(os.path.join(tmp, "r.png"), "wb").write(b)
        patch = Image.open(os.path.join(tmp, "r.png")).convert("RGB").resize((cw, ch), Image.LANCZOS)
        base = Image.open(os.path.join(tmp, fn)).convert("RGB")
        # keep the original colour: shift the patch mean to the original crop mean
        orig = np.asarray(base.crop((x0, y0, x1, y1))).astype(np.float32)
        p = np.asarray(patch).astype(np.float32)
        p = np.clip(p - p.mean(axis=(0, 1)) + orig.mean(axis=(0, 1)), 0, 255).astype(np.uint8)
        base.paste(Image.fromarray(p), (x0, y0), mask)
        base.save(os.path.join(tmp, f"p{i:05d}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", os.path.join(tmp, "p%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.copy(os.path.join(tmp, "c00060.png") if os.path.exists(os.path.join(tmp, "c00060.png")) else
                os.path.join(tmp, "c00000.png"), os.path.splitext(a.out)[0] + "_crop_in.png")
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"prompt_id": pid, "seconds": round(time.time() - t0, 1), "frames": n, "box": [x0, y0, x1, y1], "out": a.out}))


if __name__ == "__main__":
    main()
