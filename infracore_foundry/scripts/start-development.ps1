[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$composeArgs = @('compose','--env-file','local_safe/empty.env','-f','compose.local-safe.json','-f','compose.development.json','-p','satorix-development')

function Invoke-DevelopmentCompose {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Development Compose failed: ' + ($Arguments -join ' ')) }
}

# Reuse the complete base containment audit before validating the development overlay.
& (Join-Path $PSScriptRoot 'start-local-safe.ps1') -CheckOnly
if ($LASTEXITCODE -ne 0) { throw 'Base containment preflight failed.' }

$overlay = Get-Content -Raw -LiteralPath 'compose.development.json' | ConvertFrom-Json
if ($overlay.name -ne 'satorix-development') { throw 'Unexpected development project name.' }
foreach ($number in 1..6) {
    $service = $overlay.services."layer$number-api"
    if ($service.entrypoint[1] -ne '/opt/satorix-safe/development_launch.py' -or
        $service.environment.DEVELOPMENT_MODE -ne 'true' -or
        $service.environment.LOCAL_SAFE_MODE -ne 'true') {
        throw "Invalid contained development policy for layer$number-api"
    }
}

$safeRunning = & docker ps --filter 'label=com.docker.compose.project=satorix-local-safe' --format '{{.Names}}'
$legacyRunning = & docker ps --filter 'label=com.docker.compose.project=infracore_foundry' --format '{{.Names}}'
$unrestrictedRunning = & docker ps --filter 'label=com.docker.compose.project=satorix-unrestricted' --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect running containers.' }
if ($safeRunning) { throw 'Safe mode is running. Stop it with scripts/stop-satorix.ps1 -Mode Safe before switching.' }
if ($legacyRunning) { throw 'Historical Satorix containers remain quarantined and must be stopped.' }
if ($unrestrictedRunning) { throw 'Unrestricted mode is running. Stop it before switching to Development.' }

Invoke-DevelopmentCompose -Arguments @('config','--quiet')
$rendered = (& docker @composeArgs config --format json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Unable to render development configuration.' }
foreach ($number in 1..6) {
    $service = $rendered.services."layer$number-api"
    if ($service.entrypoint[1] -ne '/opt/satorix-safe/development_launch.py' -or
        $service.environment.LOCAL_SAFE_MODE -ne 'true') { throw "Rendered development policy failed for layer$number-api" }
}
if ($rendered.networks.'local-safe'.driver_opts.'com.docker.network.bridge.enable_ip_masquerade' -ne 'false') {
    throw 'Development network must keep IP masquerading disabled.'
}
if ($CheckOnly) { Write-Host 'Contained development configuration checked; no services started.'; return }

try {
    Invoke-DevelopmentCompose -Arguments @('rm','-f','neo4j')
    Invoke-DevelopmentCompose -Arguments @('up','-d','--no-build','--pull','never','--wait','--wait-timeout','180','postgres','redis','kafka','neo4j','elasticsearch','minio')
    $networkPolicy = & docker network inspect satorix-development_local-safe --format '{{.Internal}} {{index .Options "com.docker.network.bridge.enable_ip_masquerade"}}'
    if ($LASTEXITCODE -ne 0 -or $networkPolicy -ne 'false false') { throw 'Development no-masquerade network policy not confirmed.' }
    Invoke-DevelopmentCompose -Arguments @('run','--rm','--no-deps','--pull','never','minio-init')

    foreach ($number in 1..6) {
        $serviceName = "layer$number-api"
        Invoke-DevelopmentCompose -Arguments @('up','-d','--no-build','--pull','never','--no-deps',$serviceName)
        $endpoint = if ($number -eq 1) { '/ping' } elseif ($number -eq 3) { '/' } else { '/health' }
        $ready = $false
        foreach ($attempt in 1..30) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + (8000 + $number) + $endpoint) -TimeoutSec 2 -MaximumRedirection 0
                if ($response.StatusCode -eq 200) { $ready = $true; break }
            } catch { Start-Sleep -Seconds 2 }
        }
        if (-not $ready) {
            Invoke-DevelopmentCompose -Arguments @('logs','--tail','40',$serviceName)
            throw "$serviceName failed contained development startup."
        }
    }

    Invoke-DevelopmentCompose -Arguments @('up','-d','--no-build','--pull','never','--no-deps','intelligence-dashboard','operational-dashboard','schema-manager')
    foreach ($port in 3000..3002) {
        $ready = $false
        foreach ($attempt in 1..30) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 2
                if ($response.StatusCode -eq 200 -and $response.Headers['Content-Security-Policy'] -like "default-src 'self'*") { $ready = $true; break }
            } catch { Start-Sleep -Seconds 2 }
        }
        if (-not $ready) { throw "Development dashboard on port $port failed HTTP/CSP startup." }
    }
    Write-Host 'Contained development mode launched. Local mutations are enabled; external connectors, LLMs, workers, DAGs and routed egress remain disabled.'
} catch {
    & docker @composeArgs stop
    throw
}
