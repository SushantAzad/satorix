# Run from PowerShell with Docker Desktop's Linux engine running.
param([switch]$SkipBuild)
throw 'Recovery startup is quarantined. Use scripts/start-local-safe.ps1; no builds/downloads are permitted.'
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed: $($ComposeArgs -join ' ')" }
}

function Wait-Endpoint {
    param([string]$Url)
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 10 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                if ($Url -match ':800[1-6]/') {
                    $health = $response.Content | ConvertFrom-Json
                    if ($health.status -and $health.status -notin @('ok', 'healthy')) {
                        throw "Dependency health is $($health.status)"
                    }
                    if ($Url.EndsWith('/ping') -and $health.pong -ne $true) {
                        throw 'Layer 1 ping failed'
                    }
                }
                Write-Host "Ready: $Url"
                return
            }
        } catch { }
        Start-Sleep -Seconds 3
    }
    throw "Readiness timeout: $Url. Inspect docker compose logs before continuing."
}

Invoke-Compose -ComposeArgs @('config', '--quiet')
if (-not $SkipBuild) {
    Invoke-Compose -ComposeArgs @('build', 'layer1-api', 'streaming-worker', 'layer2-api',
        'layer3-api', 'layer4-api', 'layer5-api', 'layer6-api')
}
Invoke-Compose -ComposeArgs @('up', '-d', '--wait', '--wait-timeout', '300',
    'postgres', 'redis', 'kafka', 'neo4j', 'elasticsearch', 'minio')
Invoke-Compose -ComposeArgs @('up', '--no-deps', '--exit-code-from', 'minio-init', 'minio-init')
Invoke-Compose -ComposeArgs @('up', '--no-deps', '--exit-code-from', 'airflow-init', 'airflow-init')
Invoke-Compose -ComposeArgs @('up', '-d', '--no-deps', '--wait', '--wait-timeout', '300',
    'airflow-webserver', 'airflow-scheduler', 'airflow-worker')

$apiChecks = @(
    @('layer1-api', 'http://localhost:8001/ping'),
    @('layer2-api', 'http://localhost:8002/health'),
    @('layer3-api', 'http://localhost:8003/health'),
    @('layer4-api', 'http://localhost:8004/api/v1/health'),
    @('layer5-api', 'http://localhost:8005/api/v1/health'),
    @('layer6-api', 'http://localhost:8006/health')
)
foreach ($check in $apiChecks) {
    Invoke-Compose -ComposeArgs @('up', '-d', '--no-deps', $check[0])
    Wait-Endpoint -Url $check[1]
    Invoke-Compose -ComposeArgs @('logs', '--tail', '15', $check[0])
}
Invoke-Compose -ComposeArgs @('up', '-d', '--no-deps', 'streaming-worker')

# Frontends share a dependency volume: initialize them sequentially.
foreach ($check in @(
    @('intelligence-dashboard', 'http://localhost:3000/'),
    @('operational-dashboard', 'http://localhost:3001/'),
    @('schema-manager', 'http://localhost:3002/')
)) {
    Invoke-Compose -ComposeArgs @('up', '-d', '--no-deps', $check[0])
    Wait-Endpoint -Url $check[1]
}

Get-Content -Raw (Join-Path $PSScriptRoot 'smoke-phase-a.py') |
    docker compose exec -T layer6-api python -
if ($LASTEXITCODE -ne 0) { throw 'Phase A smoke checks failed.' }
Invoke-Compose -ComposeArgs @('ps', '-a')
