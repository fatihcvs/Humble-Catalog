# Everything that must pass before a commit: tests, then the privacy gate.
. (Join-Path $PSScriptRoot "_common.ps1")
Require-Venv
Set-Location $Root
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Error "Tests failed - stopping before the leak check." }
& $Python scripts\check_no_data_tracked.py
if ($LASTEXITCODE -ne 0) { Write-Error "A data file is tracked by git." }
& $Python scripts\leak_check.py
if ($LASTEXITCODE -ne 0) { Write-Error "Leak check failed." }
Write-Host "`nVerified: tests pass, no private data in the repo."
