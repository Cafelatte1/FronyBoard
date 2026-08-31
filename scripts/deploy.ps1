<#
.SYNOPSIS
  Deploy a release tag to this home server, or just restart the server.

.DESCRIPTION
  Runs ON the server, from its checkout. Stops the "AIRA Server" scheduled task
  (uv sync cannot replace a running aira.exe), optionally checks out -Tag and
  runs uv sync, then starts the task again and prints its status.

.EXAMPLE
  powershell -NoProfile -File scripts\deploy.ps1 -Tag v0.7.6   # release: checkout + uv sync + restart
  powershell -NoProfile -File scripts\deploy.ps1               # restart only

  From a dev PC over Tailscale:
  ssh -i ~/.ssh/aira_homeserver flash@100.67.93.87 "powershell -NoProfile -File C:\Users\flash\projects\project-aira\scripts\deploy.ps1 -Tag v0.7.6"
#>
param(
    [string]$Tag,
    [string]$TaskName = "AIRA Server"
)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

# 1. stop — wait for the task to end, then kill any aira process it left behind
schtasks /End /TN $TaskName | Out-Null
$procs = { Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*aira*serve*" -or $_.Name -eq "aira.exe" } }
for ($i = 0; $i -lt 20 -and (& $procs); $i++) { Start-Sleep 1 }
& $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 1

# 2. checkout + sync (release only). The server never commits, so dropping its uv.lock drift is safe.
$failed = $false
if ($Tag) {
    git checkout -- backend/uv.lock
    git fetch --tags --quiet
    git checkout --quiet $Tag
    if ($LASTEXITCODE -ne 0) {
        "checkout $Tag failed - restarting what is checked out"
        $failed = $true
    } else {
        Push-Location backend
        uv sync --quiet
        if ($LASTEXITCODE -ne 0) { "uv sync failed (exit $LASTEXITCODE)"; $failed = $true }
        Pop-Location
    }
}
"at: $(git describe --tags)"

# 3. start — always, so a failed step never leaves the server down
schtasks /Run /TN $TaskName | Out-Null
Start-Sleep 6
schtasks /Query /TN $TaskName /FO LIST | Select-String "Status"
if ($failed) { exit 1 }
