<#
.SYNOPSIS
  Register (or re-register) the "FronyBoard Server" scheduled task on the home server.

.DESCRIPTION
  Runs ON the server in an elevated PowerShell. Trigger: at system startup. Principal: SYSTEM,
  so the server is up before anyone logs on. A second trigger re-checks every 10 minutes
  (MultipleInstances = IgnoreNew makes it a no-op while running). No time limit, restarts on failure.
  The task runs the launcher %USERPROFILE%\fronyboard-server.cmd (copy scripts\fronyboard-server.cmd.example
  and fill it in first). Because SYSTEM's %LOCALAPPDATA% is the system profile, the launcher
  must pin AIRA_DATA_DIR explicitly.

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
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($boot, $recheck) -Settings $settings -Principal $principal | Out-Null
"registered: $TaskName -> $Launcher (SYSTEM, at startup). Start it now with: schtasks /Run /TN `"$TaskName`""
