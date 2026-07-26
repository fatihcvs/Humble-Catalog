# Shared setup used by every script in this folder.
# Dot-source this file; do not run it directly.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Port = if ($env:HUMBLE_PORT) { [int]$env:HUMBLE_PORT } else { 8087 }

function Require-Venv {
    if (-not (Test-Path $Python)) {
        Write-Error "No virtualenv at .venv - run scripts\windows\setup.ps1 first."
    }
}
