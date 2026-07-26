# Stop the catalog viewer by killing whatever listens on its port.
#
# Targets the port rather than a stored PID so it also catches a server
# started some other way - a detached run, an editor's task runner, or
# one left over from an earlier session.
. (Join-Path $PSScriptRoot "_common.ps1")

$conns = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($conns.Count -eq 0) {
    Write-Host "Nothing listening on port $Port."
    exit 0
}
foreach ($procId in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) {
    $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
    Stop-Process -Id $procId -Force -ErrorAction Stop
    Write-Host "Stopped $name (PID $procId) on port $Port."
}
