# Run the test suite. Extra args pass through to pytest.
. (Join-Path $PSScriptRoot "_common.ps1")
Require-Venv
Set-Location $Root
& $Python -m pytest @args
exit $LASTEXITCODE
