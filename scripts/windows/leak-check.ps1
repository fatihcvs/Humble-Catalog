# Privacy gate: fails if anything from the real library appears in the repo.
# Required by CLAUDE.md before committing tests, fixtures, or docs.
. (Join-Path $PSScriptRoot "_common.ps1")
Require-Venv
Set-Location $Root
& $Python scripts\leak_check.py
exit $LASTEXITCODE
