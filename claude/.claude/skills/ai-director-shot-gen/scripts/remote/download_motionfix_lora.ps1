$ErrorActionPreference = 'Stop'
$dst = 'C:\ai\ComfyUI_windows_portable\ComfyUI\models\loras'
foreach ($n in 'wan2.2_i2v_lightx2v_motion_fix_high.safetensors','wan2.2_i2v_lightx2v_motion_fix_low.safetensors') {
  $p = Join-Path $dst $n
  if (-not (Test-Path $p)) { curl.exe -sL -o $p "https://huggingface.co/rzgar/Wan2.2_I2V_LightX2V_Slow-Mo_Fix/resolve/main/$n" }
  "{0} {1:N0} MB" -f $n, ((Get-Item $p).Length/1MB)
}
