"""Detail pass (video-to-video refine) for a Wan clip that came out soft/waxy.

The 4-step distilled model keeps the big shapes but smears hair strands, skin texture and eye detail. This re-runs
only the LAST, low-noise part of sampling on the already-generated frames: the clip is VAE-encoded, noised to a low
sigma and denoised again by the low-noise model, conditioned on the same first/last keys. Motion and composition stay;
fine detail is redrawn.

  python refine_remote.py --src-pid <prompt_id of the original job> --image start.png [--end-image end.png] \
      --prompt-file prompts/motion/S3-6.txt --out media/video/S3-6-vid-v3r.mp4 --steps 8 --start 6

--src-pid takes the original job's 48 fps RIFE frames from the server and keeps every 3rd (= the model's own
16 fps frames, no interpolated frames). --steps/--start set the strength: sampling starts at step `start` of `steps`
with shift 5 (8/6 ~ sigma 0.62, 8/7 ~ 0.42, 12/11 ~ 0.31). Lower sigma = closer to the original.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wan_remote import NEG, UNETS, fit  # noqa: E402


def native_frames(srv, pid, tmp):
    h = requests.get(f"{srv}/history/{pid}", timeout=60).json()
    if pid not in h:
        sys.exit(f"{pid} not in server history (restarted?)")
    imgs = sorted([i for o in h[pid]["outputs"].values() for i in o.get("images", [])], key=lambda x: x["filename"])
    imgs = imgs[::3]  # 48 fps RIFE grid -> the model's own 16 fps frames
    for k, i in enumerate(imgs):
        b = requests.get(f"{srv}/view", params={"filename": i["filename"], "subfolder": i["subfolder"],
                                                 "type": i["type"]}, timeout=120).content
        open(os.path.join(tmp, f"n{k:05d}.png"), "wb").write(b)
    return len(imgs)


def upload(srv, path, name, kind):
    r = requests.post(f"{srv}/upload/image", files={"image": (name, open(path, "rb"), kind)},
                      data={"overwrite": "true"}, timeout=300)
    r.raise_for_status()
    return r.json()["name"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--src-pid", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--end-image")
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--negative-extra", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--start", type=int, default=6)
    ap.add_argument("--shift", type=float, default=5.0)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--timeout", type=int, default=6 * 3600)
    a = ap.parse_args()
    srv = a.server.rstrip("/")
    tmp = tempfile.mkdtemp(prefix="refine_")
    n = native_frames(srv, a.src_pid, tmp)
    if (n - 1) % 4:
        sys.exit(f"{n} native frames is not 4k+1")
    src_mp4 = os.path.join(tmp, "src.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "16", "-i", os.path.join(tmp, "n%05d.png"),
                    "-c:v", "libx264", "-crf", "1", "-pix_fmt", "yuv444p", src_mp4], check=True)
    vid = upload(srv, src_mp4, f"aidv_{uuid.uuid4().hex[:8]}.mp4", "video/mp4")
    img = upload_img = requests.post(f"{srv}/upload/image", files={"image": (f"aid_{uuid.uuid4().hex[:8]}.png",
                                     fit(a.image, a.width, a.height), "image/png")}, data={"overwrite": "true"},
                                     timeout=60).json()["name"]
    pos = open(a.prompt_file, encoding="utf-8").read().strip()
    neg = NEG + (", " + a.negative_extra if a.negative_extra else "")
    seed = a.seed if a.seed is not None else random.randint(0, 2**31)
    prefix = f"aid/{os.path.splitext(os.path.basename(a.out))[0]}"
    wf = {
        "2": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNETS["distill260412"][1]}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": a.shift}},
        "7": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "8": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": pos}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": neg}},
        "11": {"class_type": "LoadImage", "inputs": {"image": img}},
        "12": {"class_type": "WanImageToVideo", "inputs": {"positive": ["9", 0], "negative": ["10", 0], "vae": ["8", 0],
               "start_image": ["11", 0], "width": a.width, "height": a.height, "length": n, "batch_size": 1}},
        "30": {"class_type": "LoadVideo", "inputs": {"file": vid}},
        "31": {"class_type": "GetVideoComponents", "inputs": {"video": ["30", 0]}},
        "32": {"class_type": "VAEEncode", "inputs": {"pixels": ["31", 0], "vae": ["8", 0]}},
        "14": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["6", 0], "add_noise": "enable", "noise_seed": seed,
               "steps": a.steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0],
               "negative": ["12", 1], "latent_image": ["32", 0], "start_at_step": a.start, "end_at_step": 10000,
               "return_with_leftover_noise": "disable"}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["8", 0]}},
        "18": {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": ["15", 0],
               "clear_cache_after_n_frames": 10, "multiplier": 3, "fast_mode": False, "ensemble": True,
               "scale_factor": 1.0, "dtype": "float32", "torch_compile": False, "batch_size": 1}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["18", 0], "filename_prefix": prefix}},
    }
    if a.end_image:
        e = requests.post(f"{srv}/upload/image", files={"image": (f"aid_{uuid.uuid4().hex[:8]}_end.png",
                          fit(a.end_image, a.width, a.height), "image/png")}, data={"overwrite": "true"},
                          timeout=60).json()["name"]
        wf["17"] = {"class_type": "LoadImage", "inputs": {"image": e}}
        wf["12"]["class_type"] = "WanFirstLastFrameToVideo"
        wf["12"]["inputs"]["end_image"] = ["17", 0]
    with open(os.path.splitext(a.out)[0] + "_workflow.json", "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=1)
    r = requests.post(f"{srv}/prompt", json={"prompt": wf}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"queue failed {r.status_code}: {r.text[:2000]}")
    pid = r.json()["prompt_id"]
    print(f"queued {pid} refine of {a.src_pid}: {n} frames, steps {a.start}->{a.steps}", flush=True)
    t0 = time.time()
    while True:
        time.sleep(5)
        h = requests.get(f"{srv}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid]["status"]
            if st.get("status_str") != "success":
                sys.exit(f"failed: {json.dumps(st.get('messages'), ensure_ascii=False)[:3000]}")
            outs = h[pid]["outputs"]
            break
        if time.time() - t0 > a.timeout:
            sys.exit("timeout")
    imgs = sorted([i for o in outs.values() for i in o.get("images", [])], key=lambda x: x["filename"])[::2]
    for k, i in enumerate(imgs):
        b = requests.get(f"{srv}/view", params={"filename": i["filename"], "subfolder": i["subfolder"],
                                                 "type": i["type"]}, timeout=120).content
        open(os.path.join(tmp, f"f{k:05d}.png"), "wb").write(b)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "24", "-i", os.path.join(tmp, "f%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"prompt_id": pid, "src": a.src_pid, "seconds": round(time.time() - t0, 1), "frames": len(imgs),
                      "out": a.out, "steps": a.steps, "start": a.start}, ensure_ascii=False))


if __name__ == "__main__":
    main()
