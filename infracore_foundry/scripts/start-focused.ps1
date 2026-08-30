[CmdletBinding()]
param([switch]$CheckOnly, [switch]$EnableGemini)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$argsList = @('compose','--env-file','local_safe/empty.env','-f','compose.focused.json','-p','satorix-development')
if ($EnableGemini) {
    if (-not (Test-Path -LiteralPath '.env.gemini')) { throw 'Create the gitignored .env.gemini with GEMINI_API_KEY and GEMINI_MODEL first.' }
    $argsList += @('-f','compose.gemini.json')
    Write-Warning 'Opt-in Gemini access: Layer 6 gains outbound networking. Python restricts destinations to local services and the Gemini HTTPS endpoint; this is not a sandbox for arbitrary native code. Reports send data only after explicit UI consent.'
}
$config = Get-Content -Raw -LiteralPath compose.focused.json | ConvertFrom-Json
if ($config.networks.'local-safe'.driver_opts.'com.docker.network.bridge.enable_ip_masquerade' -ne 'false') { throw 'Containment policy missing' }
foreach ($name in @('layer3-api','layer6-api')) {
    if ($config.services.$name.environment.SATORIX_FOCUSED -ne 'true' -or $config.services.$name.environment.LOCAL_SAFE_MODE -ne 'true') { throw 'Focused policy missing' }
}
& docker @argsList config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Focused configuration invalid' }
if ($CheckOnly) { return }
foreach ($project in @('satorix-local-safe','satorix-unrestricted','infracore_foundry')) {
    $running = @(& docker ps --filter "label=com.docker.compose.project=$project" --format '{{.ID}}')
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect running modes' }
    if ($running.Count) { throw "Stop $project before starting focused Development mode." }
}
# Stop only legacy services in the same development project. Never delete volumes.
$legacy = @('redis','kafka','neo4j','elasticsearch','minio','minio-init','layer1-api','layer2-api','layer4-api','layer5-api','operational-dashboard','schema-manager')
$ids = @(& docker ps --filter 'label=com.docker.compose.project=satorix-development' --format '{{.ID}} {{.Label "com.docker.compose.service"}}')
foreach ($line in $ids) {
    $parts = $line -split ' ',2
    if ($legacy -contains $parts[1]) {
        & docker stop $parts[0]
        if ($LASTEXITCODE -ne 0) { throw 'Failed to stop legacy service' }
    }
}
& docker @argsList up -d --no-build --pull never --wait --wait-timeout 120
if ($LASTEXITCODE -ne 0) { throw 'Focused startup failed' }
Write-Host 'Focused Satorix: http://127.0.0.1:3000 — PostgreSQL, entity API, intelligence/report API, one dashboard. Existing volumes retained.'
