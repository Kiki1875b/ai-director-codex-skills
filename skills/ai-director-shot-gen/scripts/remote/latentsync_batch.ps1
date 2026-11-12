# Run the approved LatentSync 1.6 recipe on several shots, one after another (one GPU job at a time).
#   powershell -ExecutionPolicy Bypass -File latentsync_batch.ps1 -Jobs "S2-3:largest,S4-2:left" [-MaxVram 10] [-Throttle 1.0]
# Inputs: C:\ai\latentsync\in\<shot>_video.mp4 + <shot>_voice.wav (from .claude/skills/ai-director-shot-gen/scripts/lipsync_legacy/lipsync_prep.py).
# While someone games on the server: -MaxVram 6.5 -Throttle 0.5 (about 9.5 min per 5 s shot instead of about 4-5).
param([string]$Jobs = "S2-3:largest", [double]$MaxVram = 10, [double]$Throttle = 1.0)
Set-Location C:\ai\latentsync
foreach ($j in $Jobs.Split(',')) {
  $s, $pick = $j.Split(':')
  Write-Output "== $s"
  $t = Get-Date
  & .\.venv\Scripts\python.exe latentsync_run.py --video "C:\ai\latentsync\in\${s}_video.mp4" --audio "C:\ai\latentsync\in\${s}_voice.wav" `
    --out "C:\ai\latentsync\out\${s}_ls16.mp4" --pick $pick --ckpt C:\ai\latentsync\checkpoints16\latentsync_unet.pt `
    --config configs/unet/stage2_512.yaml --cfg 1.75 --lowmem --max-vram $MaxVram --throttle $Throttle 2>&1 |
    Select-String 'face track|VRAM GB|wrote|Error'
  'minutes ' + [math]::Round(((Get-Date) - $t).TotalMinutes, 1)
}
