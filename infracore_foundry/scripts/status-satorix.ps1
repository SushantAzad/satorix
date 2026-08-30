[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projects = @(
    @{Mode='Safe'; Project='satorix-local-safe'},
    @{Mode='Development'; Project='satorix-development'},
    @{Mode='Unrestricted'; Project='satorix-unrestricted'},
    @{Mode='Historical (quarantined)'; Project='infracore_foundry'}
)
foreach ($item in $projects) {
    $names = @(& docker ps --filter "label=com.docker.compose.project=$($item.Project)" --format '{{.Names}}')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Docker status.' }
    $state = if ($names.Count -gt 0 -and $names[0]) { "RUNNING ($($names.Count) containers)" } else { 'stopped' }
    Write-Host ("{0,-26} {1}" -f $item.Mode, $state)
}
