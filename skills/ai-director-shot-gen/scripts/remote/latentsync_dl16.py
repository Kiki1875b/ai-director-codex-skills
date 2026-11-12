# LatentSync 1.6 UNet (512px, same architecture as 1.5). Run on the server with HF_ENDPOINT=https://huggingface.co:
#   C:\ai\latentsync\.venv\Scripts\python.exe -I latentsync_dl16.py
# Use with: latentsync_run.py --ckpt C:\ai\latentsync\checkpoints16\latentsync_unet.pt --config configs/unet/stage2_512.yaml
import os, shutil, sys, torch
from huggingface_hub import hf_hub_download
C = r"C:\ai\latentsync\checkpoints16"; REV = "c42c7e6c8e9c213626389fa7d9a3c444b8536353"
assert os.environ.get("HF_ENDPOINT") == "https://huggingface.co"
for f in ["latentsync_unet.pt", "README.md"]:
    out = os.path.join(C, f)
    if os.path.exists(out): print("have", out); continue
    p = hf_hub_download("ByteDance/LatentSync-1.6", f, revision=REV, cache_dir=os.path.join(C, "_hf"))
    os.makedirs(os.path.dirname(out), exist_ok=True); shutil.copyfile(p, out); print("ok", f, os.path.getsize(out))
shutil.rmtree(os.path.join(C, "_hf"), ignore_errors=True)
sd = torch.load(os.path.join(C, "latentsync_unet.pt"), map_location="cpu", weights_only=True); print("weights_only ok", list(sd)[:3])
