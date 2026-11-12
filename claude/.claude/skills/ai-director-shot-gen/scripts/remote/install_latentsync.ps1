# Install LatentSync 1.5 lip sync (code Apache-2.0, weights CreativeML OpenRAIL++-M: commercial use allowed
# with use restrictions) on the GPU server in its own venv. Does not touch ComfyUI or the other venvs.
#
# Code inspected 2026-11-08 at commit a229c3948406bc2cf6eaf4873e662e70c6a04746.
# - insightface (non-commercial models) and onnxruntime are NOT installed: the wrapper (latentsync_run.py)
#   replaces latentsync.utils.face_detector.FaceDetector with MediaPipe FaceMesh (Apache-2.0).
# - decord is NOT installed: the wrapper stubs it and reads audio with soundfile.
# - VAE (sd-vae-ft-mse, safetensors) in C:\ai\latentsync\models\sd-vae and ffmpeg 7.1.1 static in C:\ai\latentsync\bin
#   (were copied from the removed MuseTalk install; install_musetalk.ps1 shows the pinned sources).
# - Not downloaded (training/eval only): stable_syncnet.pt, auxiliary/*. Only latentsync_unet.pt and whisper/tiny.pt,
#   both loaded by the repo with torch.load(weights_only=True).
$ErrorActionPreference = "Stop"
$root = "C:\ai\latentsync"
New-Item -ItemType Directory -Force $root, "C:\ai\logs", "$root\checkpoints\whisper" | Out-Null
Start-Transcript -Path "C:\ai\logs\latentsync_install.log" -Append

$commit = "a229c3948406bc2cf6eaf4873e662e70c6a04746"
if (-not (Test-Path "$root\LatentSync\.git")) { git clone --no-checkout https://github.com/bytedance/LatentSync "$root\LatentSync" }
git -C "$root\LatentSync" checkout --detach $commit
if ((git -C "$root\LatentSync" rev-parse HEAD) -ne $commit) { throw "repo not at pinned commit" }

$uv = "C:\ai\qwen3tts\bin\uv.exe"
$env:UV_PYTHON_INSTALL_DIR = "C:\ai\qwen3tts\python"
if (-not (Test-Path "$root\.venv")) { & $uv venv "$root\.venv" --python 3.10 }
$py = "$root\.venv\Scripts\python.exe"
& $uv pip install --python $py "torch==2.7.1" "torchvision==0.22.1" --index-url https://download.pytorch.org/whl/cu128
& $uv pip install --python $py `
  "numpy==1.26.4" "opencv-python==4.9.0.80" "diffusers==0.32.2" "transformers==4.48.0" "huggingface_hub==0.30.2" `
  "omegaconf==2.3.0" "einops==0.7.0" "kornia==0.8.0" "ffmpeg-python==0.2.0" "imageio==2.31.1" "imageio-ffmpeg==0.5.1" `
  "soundfile==0.12.1" "scipy==1.13.1" "accelerate==0.26.1" "tqdm" "packaging" "safetensors==0.4.5" `
  "absl-py==2.1.0" "attrs==24.2.0" "flatbuffers==24.3.25" "protobuf==4.25.5" "matplotlib==3.9.2"
& $uv pip install --python $py --no-deps "mediapipe==0.10.14"

$env:HF_ENDPOINT = "https://huggingface.co"; $env:HF_HUB_DISABLE_TELEMETRY = "1"
$dl = @'
import os, shutil, sys, torch
from huggingface_hub import hf_hub_download
C = sys.argv[1]; REV = "32a20d29aead0498e3e885e90dbbe8027da1b61b"
for f in ["latentsync_unet.pt", "whisper/tiny.pt", "README.md"]:
    out = os.path.join(C, f)
    if os.path.exists(out): print("have", out); continue
    p = hf_hub_download("ByteDance/LatentSync-1.5", f, revision=REV, cache_dir=os.path.join(C, "_hf"))
    os.makedirs(os.path.dirname(out), exist_ok=True); shutil.copyfile(p, out); print("ok", f, os.path.getsize(out))
shutil.rmtree(os.path.join(C, "_hf"), ignore_errors=True)
for f in ["latentsync_unet.pt", "whisper/tiny.pt"]:
    sd = torch.load(os.path.join(C, f), map_location="cpu", weights_only=True); print("weights_only ok", f, list(sd)[:3])
'@
$dl | Set-Content -Encoding ascii "$root\dl_weights.py"
& $py -I "$root\dl_weights.py" "$root\checkpoints"
if ($LASTEXITCODE -ne 0) { throw "weights failed" }
& $py -c "import torch, diffusers, kornia, mediapipe; print('torch', torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
& $uv pip freeze --python $py | Set-Content -Encoding ascii "$root\latentsync_freeze.txt"
Write-Output "== install done"
Stop-Transcript
