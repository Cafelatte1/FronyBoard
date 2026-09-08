<#
.SYNOPSIS
  Register FronyBoard in the MCP clients installed on this PC.

.DESCRIPTION
  Runs on a client PC (not the server). Configures whatever is installed, under
  the name "FronyBoard", and leaves every other MCP entry alone:

    Claude Code     claude mcp add --scope user (HTTP + Authorization header)
    Codex CLI       codex mcp add --url + user env var FRONY_KEY
    Claude Desktop  %APPDATA%\Claude\claude_desktop_config.json (mcp-remote bridge)

  Idempotent: re-run to change the key or the server. Hosted connectors (Claude
  app, ChatGPT) are account-level OAuth and are set up in the app, not here.

.EXAMPLE
  powershell -NoProfile -File scripts\configure_mcp_settings.ps1 -Server http://<server>:8642 -ApiKey frony_...
  powershell -NoProfile -File scripts\configure_mcp_settings.ps1 -Server http://<server>:8642   # reuse the key already configured
#>
param(
    [string]$Server,
    [string]$ApiKey
)
$ErrorActionPreference = "Stop"
if (-not $Server) { throw "pass -Server http://<host>:8642 (the FronyBoard server's tailnet address)" }
$Server = $Server.TrimEnd("/")
$Name = "FronyBoard"
$mcpUrl = "$Server/mcp"
$claudeJson = Join-Path $env:USERPROFILE ".claude.json"
$codexToml = Join-Path $env:USERPROFILE ".codex\config.toml"
$desktopJson = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"

function Read-Json($path) { Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json }
function Write-Json($path, $obj) {
    [IO.File]::WriteAllText($path, ($obj | ConvertTo-Json -Depth 100), (New-Object Text.UTF8Encoding $false))  # no BOM
}
function Strip-Bearer($value) { if ($value) { $value -replace '^Bearer\s+', '' } }
function Has-Entry($obj, $name) { $obj -and ($obj.PSObject.Properties.Name -ccontains $name) }  # property lookup is case-insensitive; entry names are not

# 1. key: reuse whatever a client already holds when none is given
if (-not $ApiKey -and (Test-Path $claudeJson)) {
    $servers = (Read-Json $claudeJson).mcpServers
    foreach ($n in $Name, "fronyboard") {
        if (-not $ApiKey -and (Has-Entry $servers $n)) { $ApiKey = Strip-Bearer $servers.$n.headers.Authorization }
    }
}
if (-not $ApiKey -and (Test-Path $desktopJson)) {
    $ApiKey = Strip-Bearer (Read-Json $desktopJson).mcpServers.$Name.env.AUTH_HEADER
}
if (-not $ApiKey) { throw "no API key: pass -ApiKey (issue one on the server with 'fauth keygen <this-pc>')" }

# 2. prove the key against the server before touching any config
try {
    $info = Invoke-RestMethod "$Server/api/server" -Headers @{ Authorization = "Bearer $ApiKey" }
    "server  $Server  (FronyBoard $($info.version))"
} catch {
    throw "the server rejected the key or is unreachable: $($_.Exception.Message)"
}

# 3. Claude Code (user scope). The old lowercase entry is replaced.
if (Get-Command claude -ErrorAction SilentlyContinue) {
    if (Test-Path $claudeJson) {
        $servers = (Read-Json $claudeJson).mcpServers
        foreach ($n in $Name, "fronyboard") { if (Has-Entry $servers $n) { claude mcp remove $n -s user | Out-Null } }
    }
    claude mcp add --transport http --scope user $Name $mcpUrl --header "Authorization: Bearer $ApiKey" | Out-Null
    "claude code     $Name -> $mcpUrl"
} else { "claude code     not installed" }

# 4. Codex CLI: the key lives in the user env var FRONY_KEY, the config only names it
if (Get-Command codex -ErrorAction SilentlyContinue) {
    [Environment]::SetEnvironmentVariable("FRONY_KEY", $ApiKey, "User")
    $env:FRONY_KEY = $ApiKey
    if (Test-Path $codexToml) {
        foreach ($n in $Name, "fronyboard") {
            if (Select-String -Path $codexToml -Pattern "^\[mcp_servers\.[`"']?$n[`"']?\]" -Quiet) { codex mcp remove $n | Out-Null }
        }
    }
    codex mcp add $Name --url $mcpUrl --bearer-token-env-var FRONY_KEY | Out-Null
    "codex           $Name -> $mcpUrl  (FRONY_KEY set for this user; restart open terminals)"
} else { "codex           not installed" }

# 5. Claude Desktop: local bridge entry (npx mcp-remote), same shape as before
if (Test-Path $desktopJson) {
    $cfg = Read-Json $desktopJson
    if (-not $cfg.mcpServers) { $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
    $entry = [pscustomobject]@{
        command = "npx"
        args    = @("mcp-remote", $mcpUrl, "--allow-http", "--header", 'Authorization:${AUTH_HEADER}')
        env     = [pscustomobject]@{ AUTH_HEADER = "Bearer $ApiKey" }
    }
    foreach ($p in @($cfg.mcpServers.PSObject.Properties | Where-Object { $_.Name -eq $Name })) { $cfg.mcpServers.PSObject.Properties.Remove($p.Name) }
    $cfg.mcpServers | Add-Member -NotePropertyName $Name -NotePropertyValue $entry
    Write-Json $desktopJson $cfg
    "claude desktop  $Name -> $mcpUrl  (restart Claude Desktop to load it)"
} else { "claude desktop  not installed" }
