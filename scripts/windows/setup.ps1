# Create the virtualenv and install the project with dev extras.
. (Join-Path $PSScriptRoot "_common.ps1")
Set-Location $Root
# Test for the interpreter, not the directory: a failed run leaves a
# .venv behind, and re-running must not mistake that for a working one.
if (-not (Test-Path $Python)) { py -3.12 -m venv .venv }
& ".venv\Scripts\pip.exe" install -e ".[dev]"
& ".venv\Scripts\playwright.exe" install chromium
Write-Host "Setup complete."
