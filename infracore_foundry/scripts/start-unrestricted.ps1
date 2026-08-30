[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$SkipBuild,
    [switch]$AcknowledgeUnrestrictedRisk
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath '.env' -PathType Leaf)) {
    throw 'Unrestricted mode requires an uncommitted .env created from .env.example.'
}
$required = @('POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','MINIO_ACCESS_KEY','MINIO_SECRET_KEY',
    'ENCRYPTION_KEY','API_KEY','JWT_SECRET_KEY','DEFAULT_ADMIN_EMAIL','DEFAULT_ADMIN_PASSWORD',
    'AIRFLOW_ADMIN_PASSWORD','NEO4J_PASSWORD','LLM_PROVIDER')
$values = @{}
foreach ($line in Get-Content -LiteralPath '.env') {
    if ($line -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') { $values[$matches[1]] = $matches[2] }
}
foreach ($key in $required) {
    if (-not $values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($values[$key]) -or $values[$key] -match 'CHANGE_ME') {
        throw "Unrestricted .env is missing a non-placeholder value for $key."
    }
}

$conflicts = @('satorix-local-safe','satorix-development','infracore_foundry')
foreach ($project in $conflicts) {
    $running = & docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Docker projects.' }
    if ($running) { throw "Conflicting project '$project' is running. Stop it before Unrestricted mode." }
}

$composeArgs = @('compose','--env-file','.env','-f','docker-compose.yml','-f','compose.unrestricted.json','-p','satorix-unrestricted')
function Invoke-UnrestrictedCompose {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Unrestricted Compose failed: ' + ($Arguments -join ' ')) }
}

Invoke-UnrestrictedCompose -Arguments @('config','--quiet')
$overlay = Get-Content -Raw -LiteralPath 'compose.unrestricted.json' | ConvertFrom-Json
if ($overlay.name -ne 'satorix-unrestricted') { throw 'Unexpected unrestricted project name.' }
foreach ($number in 1..6) {
    if ($overlay.services."layer$number-api".environment.LOCAL_SAFE_MODE -ne 'false') {
        throw "Unrestricted gate was not disabled for layer$number-api."
    }
}
if ($CheckOnly) {
    Write-Host 'Unrestricted configuration and credentials checked; no builds, downloads, services or external requests were started.'
    return
}
if (-not $AcknowledgeUnrestrictedRisk) {
    throw 'Starting Unrestricted mode requires -AcknowledgeUnrestrictedRisk.'
}

function Wait-Endpoint {
    param([string]$Url)
    foreach ($attempt in 1..60) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 3 }
    }
    throw "Readiness timeout: $Url"
}

try {
    if (-not $SkipBuild) {
        Invoke-UnrestrictedCompose -Arguments @('build','layer1-api','streaming-worker','layer2-api','layer3-api','layer4-api','layer5-api','layer6-api')
    }
    Invoke-UnrestrictedCompose -Arguments @('up','-d','--wait','--wait-timeout','300','postgres','redis','kafka','neo4j','elasticsearch','minio')
    Invoke-UnrestrictedCompose -Arguments @('up','--no-deps','--exit-code-from','minio-init','minio-init')
    Invoke-UnrestrictedCompose -Arguments @('up','--no-deps','--exit-code-from','airflow-init','airflow-init')
    Invoke-UnrestrictedCompose -Arguments @('up','-d','--no-deps','airflow-webserver','airflow-scheduler','airflow-worker')

    foreach ($check in @(
        @('layer1-api','http://127.0.0.1:8001/ping'),
        @('layer2-api','http://127.0.0.1:8002/health'),
        @('layer3-api','http://127.0.0.1:8003/'),
        @('layer4-api','http://127.0.0.1:8004/health'),
        @('layer5-api','http://127.0.0.1:8005/health'),
        @('layer6-api','http://127.0.0.1:8006/health')
    )) {
        Invoke-UnrestrictedCompose -Arguments @('up','-d','--no-deps',$check[0])
        Wait-Endpoint -Url $check[1]
    }
    Invoke-UnrestrictedCompose -Arguments @('up','-d','--no-deps','streaming-worker')

    foreach ($check in @(
        @('intelligence-dashboard','http://127.0.0.1:3000/'),
        @('operational-dashboard','http://127.0.0.1:3001/'),
        @('schema-manager','http://127.0.0.1:3002/')
    )) {
        Invoke-UnrestrictedCompose -Arguments @('up','-d','--no-deps',$check[0])
        Wait-Endpoint -Url $check[1]
    }

    Invoke-UnrestrictedCompose -Arguments @('up','-d','ollama')
    Invoke-UnrestrictedCompose -Arguments @('up','--exit-code-from','ollama-init','ollama-init')
    Write-Host 'UNRESTRICTED mode launched. External access, mutations, workers, schedules, webhooks, LLMs, model downloads and integration side effects are enabled.'
} catch {
    & docker @composeArgs stop
    throw
}
