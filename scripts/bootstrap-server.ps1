<#
.SYNOPSIS
  One-time bootstrap for a new Frony home server (run ON the new machine, as admin).

.DESCRIPTION
  Enables the OpenSSH server, authorizes the deploy key passed in -DeployKey (the
  public half of the dev PC's ~/.ssh/fronyboard_homeserver), and installs git + uv.
  Everything after this (clone, data move, scheduled tasks, funnel) is done over ssh
  from a dev PC — see docs/operations.md and AIR-058.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\bootstrap-server.ps1 -DeployKey "ssh-ed25519 AAAA... comment"
#>
param(
    [string]$DeployKey
)

$ErrorActionPreference = "Stop"
if ($DeployKey -notmatch '^ssh-(ed25519|rsa|ecdsa)\S* \S+') { throw "pass -DeployKey with one OpenSSH public key line (ssh-ed25519 AAAA... comment)" }

# 1. OpenSSH server (adds its own firewall rule)
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
Set-Service sshd -StartupType Automatic
Start-Service sshd

# 2. authorize the deploy key (admin accounts read administrators_authorized_keys)
$path = "C:\ProgramData\ssh\administrators_authorized_keys"
Set-Content -Path $path -Value $DeployKey -Encoding ascii
icacls $path /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null

# 3. git + uv
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id astral-sh.uv -e --accept-package-agreements

"bootstrap done — sshd running, deploy key authorized, git + uv installed"
