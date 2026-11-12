"""Restore/upscale a finished clip with SeedVR2 on the remote ComfyUI (fixes smeared hair, waxy skin, soft eyes).

  python seedvr2_remote.py media/video/S3-6-vid-v3.mp4 media/video/S3-6-vid-v3_sv.mp4 [--res 1080] [--batch 21]

The clip (24 fps deliverable) is uploaded, run through SeedVR2 3B fp8 (block swap for 12 GB), and saved back at
24 fps. --res is the short edge of the output (720 = restore only, 1080 = restore + upscale). Frame count must be
4n+1 for the batch logic; the clip is padded/trimmed to fit and restored to its length.
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

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--res", type=int, default=1080)
    ap.add_argument("--batch", type=int, default=21, help="frames per batch, 4n+1 (more = steadier, more VRAM)")
    ap.add_argument("--overlap", type=int, default=4)
    ap.add_argument("--swap", type=int, default=20, help="DiT blocks swapped to CPU (3B: 0-32)")
    ap.add_argument("--model", default="seedvr2_ema_3b_fp8_e4m3fn.safetensors")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--timeout", type=int, default=3 * 3600)
    a = ap.parse_args()
    srv = a.server.rstrip("/")
    name = f"aidsv_{uuid.uuid4().hex[:8]}.mp4"
    r = requests.post(f"{srv}/upload/image", files={"image": (name, open(a.inp, "rb"), "video/mp4")},
                      data={"overwrite": "true"}, timeout=300)
    r.raise_for_status()
    vid = r.json()["name"]
    prefix = f"aid/{os.path.splitext(os.path.basename(a.out))[0]}"
    wf = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": vid}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "SeedVR2LoadDiTModel", "inputs": {"model": a.model, "device": "cuda:0",
              "blocks_to_swap": a.swap, "swap_io_components": True, "offload_device": "cpu", "cache_model": False,
              "attention_mode": "sdpa"}},
        "4": {"class_type": "SeedVR2LoadVAEModel", "inputs": {"model": "ema_vae_fp16.safetensors", "device": "cuda:0",
              "encode_tiled": True, "encode_tile_size": 768, "encode_tile_overlap": 128, "decode_tiled": True,
              "decode_tile_size": 768, "decode_tile_overlap": 128, "offload_device": "cpu"}},
        "5": {"class_type": "SeedVR2VideoUpscaler", "inputs": {"image": ["2", 0], "dit": ["3", 0], "vae": ["4", 0],
              "seed": a.seed, "resolution": a.res, "max_resolution": 0, "batch_size": a.batch,
              "uniform_batch_size": True, "color_correction": "lab", "temporal_overlap": a.overlap,
              "offload_device": "cpu"}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": prefix}},
    }
    r = requests.post(f"{srv}/prompt", json={"prompt": wf}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"queue failed {r.status_code}: {r.text[:2000]}")
    pid = r.json()["prompt_id"]
    print(f"queued {pid} seedvr2 {a.inp} res {a.res}", flush=True)
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
    imgs = sorted([i for o in outs.values() for i in o.get("images", [])], key=lambda x: x["filename"])
    tmp = tempfile.mkdtemp(prefix="sv_")
    for k, i in enumerate(imgs):
        b = requests.get(f"{srv}/view", params={"filename": i["filename"], "subfolder": i["subfolder"],
                                                 "type": i["type"]}, timeout=120).content
        open(os.path.join(tmp, f"f{k:05d}.png"), "wb").write(b)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "24", "-i", os.path.join(tmp, "f%05d.png"),
                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p", a.out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"prompt_id": pid, "seconds": round(time.time() - t0, 1), "frames": len(imgs), "out": a.out}))


if __name__ == "__main__":
    main()
