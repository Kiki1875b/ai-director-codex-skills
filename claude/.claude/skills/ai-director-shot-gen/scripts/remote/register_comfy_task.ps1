[Console]::OutputEncoding = [Text.Encoding]::UTF8
$u = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c C:\ai\start_comfy.bat' -WorkingDirectory 'C:\ai'
$t = New-ScheduledTaskTrigger -AtLogOn -User $u
$p = New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'ComfyUI-Remote' -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null
"task registered for $u"
if (-not (Get-ScheduledTask -TaskName ComfyUI-Remote -ErrorAction SilentlyContinue)) { throw "task missing" }
Get-CimInstance Win32_Process | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*ComfyUImain.py*' } | % { Stop-Process -Id $_.ProcessId -Force; "stopped $($_.ProcessId)" }
Start-Sleep 3
Start-ScheduledTask -TaskName 'ComfyUI-Remote'
"started"
