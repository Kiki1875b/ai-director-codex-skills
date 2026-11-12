# Install Qwen3-TTS (Apache-2.0) on the GPU server in its own venv, separate from ComfyUI.
# Code inspected 2026-11-08 at commit 022e286b: no network use when audio inputs are local files and
# HF_HUB_OFFLINE=1; weights load via transformers (safetensors). flash-attn skipped on Windows (sdpa).
# RTX 5070 (Blackwell) needs torch >= 2.7 with cu128.
$ErrorActionPreference = "Stop"
$root = "C:\ai\qwen3tts"
$log = "C:\ai\logs\qwen3tts_install.log"
New-Item -ItemType Directory -Force $root, "C:\ai\logs", "$root\bin", "$root\models" | Out-Null
Start-Transcript -Path $log -Append

$uv = "$root\bin\uv.exe"
if (-not (Test-Path $uv)) {
  $zip = "$root\bin\uv.zip"
  Invoke-WebRequest "https://github.com/astral-sh/uv/releases/download/0.9.5/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip
  Expand-Archive $zip -DestinationPath "$root\bin" -Force
  Remove-Item $zip
}
& $uv --version

$env:UV_PYTHON_INSTALL_DIR = "$root\python"
& $uv python install 3.11
if (-not (Test-Path "$root\.venv")) { & $uv venv "$root\.venv" --python 3.11 }
$py = "$root\.venv\Scripts\python.exe"

& $uv pip install --python $py "torch==2.7.1" "torchaudio==2.7.1" --index-url https://download.pytorch.org/whl/cu128
& $uv pip install --python $py "git+https://github.com/QwenLM/Qwen3-TTS@022e286b98fbec7e1e916cb940cdf532cd9f488e" "huggingface_hub==0.36.0"

$dl = @"
from huggingface_hub import snapshot_download as d
for rid in ['Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign', 'Qwen/Qwen3-TTS-12Hz-1.7B-Base', 'Qwen/Qwen3-TTS-12Hz-0.6B-Base']:
    p = d(rid, local_dir=r'$root\models\\' + rid.split('/')[1])
    print('ok', rid, p)
"@
$dl | Set-Content "$root\dl.py"
& $py "$root\dl.py"

& $py -c "import torch, qwen_tts; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
Get-ChildItem "$root\models" -Recurse -Include *.py, *.pkl, *.bin, *.pt | Select-Object FullName
Write-Output "== install done"
Stop-Transcript
