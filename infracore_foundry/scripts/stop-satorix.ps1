[CmdletBinding()]
param(
    [ValidateSet('Safe','Development','Unrestricted','All')]
    [string]$Mode = 'All'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$targets = if ($Mode -eq 'All') { @('Safe','Development','Unrestricted') } else { @($Mode) }
foreach ($target in $targets) {
    if ($target -eq 'Unrestricted') {
        $ids = @(& docker ps -q --filter 'label=com.docker.compose.project=satorix-unrestricted')
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Unrestricted containers.' }
        if ($ids.Count -gt 0 -and $ids[0]) { & docker stop @ids | Out-Null }
        if ($LASTEXITCODE -ne 0) { throw 'Failed to stop Unrestricted mode.' }
        continue
    }
    $project = if ($target -eq 'Safe') { 'satorix-local-safe' } else { 'satorix-development' }
    $files = if ($target -eq 'Safe') {
        @('-f','compose.local-safe.json')
    } else {
        @('-f','compose.local-safe.json','-f','compose.development.json')
    }
    & docker compose --env-file local_safe/empty.env @files -p $project stop
    if ($LASTEXITCODE -ne 0) { throw "Failed to stop $target mode." }
}
Write-Host "Stopped requested Satorix mode: $Mode. Data volumes were preserved."
