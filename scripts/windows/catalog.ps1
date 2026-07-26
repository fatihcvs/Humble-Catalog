# Passthrough to the catalog CLI, e.g.
#   .\scripts\windows\catalog.ps1 enrich --limit 20
. (Join-Path $PSScriptRoot "_common.ps1")
Require-Venv
Set-Location $Root
& $Python -m humble_catalog @args
exit $LASTEXITCODE
