[Console]::OutputEncoding = [Text.Encoding]::UTF8
Get-CimInstance Win32_Process | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*main.py*--port 8188*' } | % { Stop-Process -Id $_.ProcessId -Force; "stopped $($_.ProcessId)" }
Start-Sleep 4
Start-ScheduledTask -TaskName 'ComfyUI-Remote'
"started task"
