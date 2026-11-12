[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$cn = 'C:\ai\ComfyUI_windows_portable\ComfyUI\custom_nodes'
$py = 'C:\ai\ComfyUI_windows_portable\python_embeded\python.exe'
$repos = @{
  'ComfyUI-PainterI2V' = 'https://github.com/princepainter/ComfyUI-PainterI2V'
  'ComfyUI-NAG' = 'https://github.com/ChenDarYen/ComfyUI-NAG'
  'ComfyUI-Frame-Interpolation' = 'https://github.com/Fannovel16/ComfyUI-Frame-Interpolation'
}
foreach ($k in $repos.Keys) {
  $p = Join-Path $cn $k
  if (Test-Path $p) { "exists: $k"; git -C $p pull 2>&1 | Out-String } else { git clone --depth 1 $repos[$k] $p 2>&1 | Out-String }
  "== $k files:"; Get-ChildItem $p -File | Select -Expand Name
}
$fi = Join-Path $cn 'ComfyUI-Frame-Interpolation'
if (Test-Path "$fi\requirements-no-cupy.txt") { & $py -s -m pip install -r "$fi\requirements-no-cupy.txt" 2>&1 | Select -Last 3 }
foreach ($k in 'ComfyUI-PainterI2V','ComfyUI-NAG') { $r = Join-Path (Join-Path $cn $k) 'requirements.txt'; if (Test-Path $r) { "req ${k}:"; Get-Content $r; & $py -s -m pip install -r $r 2>&1 | Select -Last 3 } }
