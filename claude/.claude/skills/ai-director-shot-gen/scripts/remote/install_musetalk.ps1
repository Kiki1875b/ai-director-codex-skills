# Install MuseTalk 1.5 lip sync (code MIT, weights MIT/Apache-2.0/WTFPL) on the GPU server in its own venv.
# Does not touch ComfyUI or the other venvs (qwen3tts, cosyvoice, chatterbox); only reuses the uv binary
# and the uv-managed CPython 3.10 under C:\ai\qwen3tts\python.
#
# Code inspected 2026-11-08 at commit 0a89dec45a0192b824e3cf4daf96c239440c5ed8.
# - mmcv/mmpose/DWPose are NOT installed. The wrapper (lipsync.py) replaces DWPose 68-point face landmarks
#   and the S3FD face detector with MediaPipe FaceMesh (Apache-2.0, model bundled in the wheel, no download),
#   keeping MuseTalk's bbox / half-face logic. Repo files are left unmodified.
# - Weights come only from huggingface.co (HF_ENDPOINT forced; download_weights.bat would use hf-mirror.com),
#   pinned to repo commit SHAs. Only safetensors where the repo offers them; the remaining .pth files
#   (unet.pth, 79999_iter.pth) are checked to load with torch.load(weights_only=True).
# - resnet18-5c106cde.pth (in download_weights.bat) is NOT used: it is a legacy-tar pickle that refuses
#   weights_only=True, and it is redundant - it only initialises BiSeNet's backbone, which 79999_iter.pth
#   then overwrites completely (strict load, all 191 keys incl. 120 cp.resnet.* keys; checked 2026-11-08).
#   lipsync.py turns Resnet18.init_weight into a no-op so the file is never opened.
# - Not downloaded (not needed for inference): DWPose, LatentSync syncnet, MuseTalk v1.0 unet, S3FD.
# - ffmpeg: static GPL build 7.1.1 from Gyan's official GitHub release, sha256 pinned.
# Usage (on the server):  powershell -ExecutionPolicy Bypass -File install_musetalk.ps1
# then copy musetalk_lipsync.py to C:\ai\musetalk\lipsync.py.
$ErrorActionPreference = "Stop"
$root = "C:\ai\musetalk"
$log = "C:\ai\logs\musetalk_install.log"
New-Item -ItemType Directory -Force $root, "C:\ai\logs", "$root\bin", "$root\models" | Out-Null
Start-Transcript -Path $log -Append

# --- repo at pinned commit -------------------------------------------------------------------------
$commit = "0a89dec45a0192b824e3cf4daf96c239440c5ed8"
if (-not (Test-Path "$root\MuseTalk\.git")) {
  git clone --no-checkout https://github.com/TMElyralab/MuseTalk "$root\MuseTalk"
}
git -C "$root\MuseTalk" checkout --detach $commit
if ((git -C "$root\MuseTalk" rev-parse HEAD) -ne $commit) { throw "repo not at pinned commit" }

# --- ffmpeg (static, pinned) -----------------------------------------------------------------------
if (-not (Test-Path "$root\bin\ffmpeg.exe")) {
  $zip = "$root\bin\ffmpeg.zip"
  Invoke-WebRequest "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip" -OutFile $zip
  $h = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
  if ($h -ne "04861d3339c5ebe38b56c19a15cf2c0cc97f5de4fa8910e4d47e5e6404e4a2d4") { throw "ffmpeg sha256 mismatch: $h" }
  Expand-Archive $zip -DestinationPath "$root\bin\_ff" -Force
  Copy-Item "$root\bin\_ff\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe", "$root\bin\_ff\ffmpeg-7.1.1-essentials_build\bin\ffprobe.exe", "$root\bin\_ff\ffmpeg-7.1.1-essentials_build\LICENSE" "$root\bin\"
  Remove-Item -Recurse -Force "$root\bin\_ff", $zip
}
& "$root\bin\ffmpeg.exe" -hide_banner -version | Select-Object -First 1

# --- venv ------------------------------------------------------------------------------------------
$uv = "C:\ai\qwen3tts\bin\uv.exe"
$env:UV_PYTHON_INSTALL_DIR = "C:\ai\qwen3tts\python"
if (-not (Test-Path "$root\.venv")) { & $uv venv "$root\.venv" --python 3.10 }
$py = "$root\.venv\Scripts\python.exe"

# Full transitive lock (from a working install) next to this script, used as constraints when present.
$lock = Join-Path $PSScriptRoot "musetalk_freeze.txt"
$c = @(); if (Test-Path $lock) { $c = @("-c", $lock) }
& $uv pip install --python $py "torch==2.7.1" "torchvision==0.22.1" --index-url https://download.pytorch.org/whl/cu128
# Top-level pins; transitive versions come from musetalk_freeze.txt (copy it next to this script).
& $uv pip install --python $py @c `
  "numpy==1.26.4" "opencv-python==4.9.0.80" "diffusers==0.30.2" "transformers==4.39.2" "huggingface_hub==0.30.2" `
  "librosa==0.11.0" "soundfile==0.12.1" "einops==0.8.1" "safetensors==0.4.5" `
  "absl-py==2.1.0" "attrs==24.2.0" "flatbuffers==24.3.25" "protobuf==4.25.5" "matplotlib==3.9.2"
# MediaPipe without jax/jaxlib, opencv-contrib, sounddevice (not needed for FaceMesh; matplotlib is, via solutions/__init__).
& $uv pip install --python $py --no-deps "mediapipe==0.10.14"

# --- weights (huggingface.co only, pinned revisions) -----------------------------------------------
$env:HF_ENDPOINT = "https://huggingface.co"
$env:HF_HUB_DISABLE_TELEMETRY = "1"
$dl = @'
import os, shutil, sys
from huggingface_hub import hf_hub_download
M = sys.argv[1]
J = [  # (repo, revision, file, dest dir under models)
 ("TMElyralab/MuseTalk", "2bcb936e2fddb4d86db4c62fd45b387d0c061571", "musetalkV15/unet.pth", "musetalkV15"),
 ("TMElyralab/MuseTalk", "2bcb936e2fddb4d86db4c62fd45b387d0c061571", "musetalkV15/musetalk.json", "musetalkV15"),
 ("TMElyralab/MuseTalk", "2bcb936e2fddb4d86db4c62fd45b387d0c061571", "LICENSE.txt", "musetalkV15"),
 ("stabilityai/sd-vae-ft-mse", "31f26fdeee1355a5c34592e401dd41e45d25a493", "config.json", "sd-vae"),
 ("stabilityai/sd-vae-ft-mse", "31f26fdeee1355a5c34592e401dd41e45d25a493", "diffusion_pytorch_model.safetensors", "sd-vae"),
 ("openai/whisper-tiny", "169d4a4341b33bc18d8881c4b69c2e104e1cc0af", "config.json", "whisper"),
 ("openai/whisper-tiny", "169d4a4341b33bc18d8881c4b69c2e104e1cc0af", "preprocessor_config.json", "whisper"),
 ("openai/whisper-tiny", "169d4a4341b33bc18d8881c4b69c2e104e1cc0af", "model.safetensors", "whisper"),
 ("ManyOtherFunctions/face-parse-bisent", "0073b233a5a3c4b1377d4dbf49245017938a72b5", "79999_iter.pth", "face-parse-bisent"),
]
assert os.environ.get("HF_ENDPOINT") == "https://huggingface.co"
for repo, rev, f, d in J:
    out = os.path.join(M, d, os.path.basename(f))
    if os.path.exists(out):
        print("have", out); continue
    os.makedirs(os.path.dirname(out), exist_ok=True)
    p = hf_hub_download(repo, f, revision=rev, cache_dir=os.path.join(M, "_hfcache"))
    shutil.copyfile(p, out)
    print("ok", repo, f, os.path.getsize(out))
shutil.rmtree(os.path.join(M, "_hfcache"), ignore_errors=True)
import torch
for f in ["musetalkV15/unet.pth", "face-parse-bisent/79999_iter.pth"]:
    sd = torch.load(os.path.join(M, f), map_location="cpu", weights_only=True)  # refuses pickled code
    print("weights_only ok", f, len(sd))
'@
$dl | Set-Content -Encoding ascii "$root\dl_weights.py"
Remove-Item -Force -ErrorAction SilentlyContinue "$root\models\face-parse-bisent\resnet18-5c106cde.pth"
& $py -I "$root\dl_weights.py" "$root\models"
if ($LASTEXITCODE -ne 0) { throw "weight download / weights_only check failed" }

& $py -c "import torch, diffusers, transformers, cv2, librosa, mediapipe as mp; from mediapipe.python.solutions import face_mesh; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0), 'mp', mp.__version__)"
if ($LASTEXITCODE -ne 0) { throw "import check failed" }
& $uv pip freeze --python $py | Set-Content -Encoding ascii "$root\musetalk_freeze.txt"
Get-Content "$root\musetalk_freeze.txt"
Write-Output "== install done"
Stop-Transcript
