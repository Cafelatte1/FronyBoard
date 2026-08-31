<#
.SYNOPSIS
  One-time bootstrap for a new Frony home server (run ON the new machine, as admin).

.DESCRIPTION
  Enables the OpenSSH server, authorizes the aira_homeserver deploy key, and
  installs git + uv. Everything after this (clone, data move, scheduled tasks,
  funnel) is done over ssh from a dev PC — see docs/operations.md and AIR-058.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\bootstrap-server.ps1
#>

$ErrorActionPreference = "Stop"

# 1. OpenSSH server (adds its own firewall rule)
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
Set-Service sshd -StartupType Automatic
Start-Service sshd

# 2. authorize the deploy key (admin accounts read administrators_authorized_keys)
$pub = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHIy5dmWLRX38lgffoe1TSRC43FUQOwJy0oYxjDOx6lI frony-to-homeserver"
$path = "C:\ProgramData\ssh\administrators_authorized_keys"
Set-Content -Path $path -Value $pub -Encoding ascii
icacls $path /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null

# 3. git + uv
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id astral-sh.uv -e --accept-package-agreements

"bootstrap done — sshd running, deploy key authorized, git + uv installed"
