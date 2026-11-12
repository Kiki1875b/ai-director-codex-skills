# Install CosyVoice (Apache-2.0) and Chatterbox multilingual (MIT) on the GPU server, each in its own venv.
# Code inspected 2026-11-08: CosyVoice @074ca6dc (weights_only loads; no network when model_dir is local),
# Chatterbox @ab55923c (weights_only loads; downloads only in from_pretrained; adds the Perth audio watermark).
# RTX 5070 (Blackwell) needs torch >= 2.7 with cu128, so both repos' torch pins are overridden.
$ErrorActionPreference = "Continue"
$uv = "C:\ai\qwen3tts\bin\uv.exe"
$env:UV_PYTHON_INSTALL_DIR = "C:\ai\qwen3tts\python"
$log = "C:\ai\logs\tts_compare_install.log"
Start-Transcript -Path $log -Append
"torch==2.7.1`ntorchaudio==2.7.1" | Set-Content C:\ai\torch_override.txt

# ---- CosyVoice ----
$cv = "C:\ai\cosyvoice"
New-Item -ItemType Directory -Force $cv | Out-Null
if (-not (Test-Path "$cv\repo")) { git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git "$cv\repo" }
Push-Location "$cv\repo"; git checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc; git submodule update --init --recursive; Pop-Location
& $uv python install 3.10
if (-not (Test-Path "$cv\.venv")) { & $uv venv "$cv\.venv" --python 3.10 }
$py = "$cv\.venv\Scripts\python.exe"
& $uv pip install --python $py "torch==2.7.1" "torchaudio==2.7.1" --index-url https://download.pytorch.org/whl/cu128
$req = Get-Content "$cv\repo\requirements.txt" | Where-Object {
  $_ -notmatch '^--' -and $_ -notmatch '^torch' -and $_ -notmatch "sys_platform == 'linux'" -and
  $_ -notmatch '^(gradio|fastapi|fastapi-cli|uvicorn|tensorboard|grpcio|grpcio-tools|deepspeed)=='
}
$req | Set-Content "$cv\requirements-win.txt"
& $uv pip install --python $py -r "$cv\requirements-win.txt" --override C:\ai\torch_override.txt
& $uv pip install --python $py "huggingface_hub==0.36.0"
& $py -c "from huggingface_hub import snapshot_download as d; d('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir=r'C:\ai\cosyvoice\models\Fun-CosyVoice3-0.5B')"
& $py -c "import torch; print('cosyvoice torch', torch.__version__, torch.cuda.is_available())"
Write-Output "== cosyvoice install done"

# ---- Chatterbox ----
$cb = "C:\ai\chatterbox"
New-Item -ItemType Directory -Force $cb | Out-Null
if (-not (Test-Path "$cb\.venv")) { & $uv venv "$cb\.venv" --python 3.11 }
$py2 = "$cb\.venv\Scripts\python.exe"
& $uv pip install --python $py2 "torch==2.7.1" "torchaudio==2.7.1" --index-url https://download.pytorch.org/whl/cu128
& $uv pip install --python $py2 "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox@ab55923c27757c90cfcc407baa57dc25a7d25217" --override C:\ai\torch_override.txt
& $py2 -c "from huggingface_hub import snapshot_download as d; print(d('ResembleAI/chatterbox', allow_patterns=['ve.pt','t3_mtl23ls_v2.safetensors','t3_mtl23ls_v3.safetensors','s3gen.pt','grapheme_mtl_merged_expanded_v1.json','conds.pt','Cangjie5_TC.json'], local_dir=r'C:\ai\chatterbox\models'))"
& $py2 -c "import torch; print('chatterbox torch', torch.__version__, torch.cuda.is_available())"
Write-Output "== chatterbox install done"
Stop-Transcript
