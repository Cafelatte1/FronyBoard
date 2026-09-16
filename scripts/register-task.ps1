<#
.SYNOPSIS
  Register (or re-register) the "FronyBoard Server" scheduled task on the home server.

.DESCRIPTION
  Runs ON the server in an elevated PowerShell. Trigger: at system startup. Principal: the service
  account with S4U logon, so the server is up before anyone logs on and no password is stored.
  A second trigger re-checks every 10 minutes (MultipleInstances = IgnoreNew makes it a no-op while
  running) — it covers what RestartCount cannot: a process that exited 0, or one the scheduler still
  believes is running. Retry is 999 times a minute apart, matching the sibling Frony tasks.
  The task runs the launcher %USERPROFILE%\fronyboard-server.cmd (copy scripts\fronyboard-server.cmd.example
  and fill it in first). The launcher pins AIRA_DATA_DIR explicitly — every Frony launcher owns its own
  paths, which is what makes the principal safe to change.

.EXAMPLE
  powershell -NoProfile -File scripts\register-task.ps1
#>
param(
    [string]$TaskName = "FronyBoard Server",
    [string]$Launcher = (Join-Path $env:USERPROFILE "fronyboard-server.cmd")
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Launcher)) { throw "launcher not found: $Launcher (copy scripts\fronyboard-server.cmd.example)" }

$action = New-ScheduledTaskAction -Execute $Launcher
$boot = New-ScheduledTaskTrigger -AtStartup
$recheck = New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Minutes 10)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
# RunLevel은 Limited — 최고 권한이면 deploy.ps1의 잔존 프로세스 정리가 일반 셸에서 안 된다. 등록 자체만 관리자 권한 필요.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($boot, $recheck) -Settings $settings -Principal $principal | Out-Null
"registered: $TaskName -> $Launcher (S4U as $env:USERNAME, at startup, retry 999x1m). Start it now with: schtasks /Run /TN `"$TaskName`""
