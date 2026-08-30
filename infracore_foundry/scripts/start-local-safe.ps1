[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$composeArgs = @('compose', '--env-file', 'local_safe/empty.env', '-f', 'compose.local-safe.json', '-p', 'satorix-local-safe')
function Invoke-SafeCompose {
    param([string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Safe Compose failed: ' + ($Arguments -join ' ')) }
}
$config = Get-Content -Raw -LiteralPath 'compose.local-safe.json' | ConvertFrom-Json
if ($config.name -ne 'satorix-local-safe' -or $config.networks.'local-safe'.internal -ne $false) { throw 'Host-accessible egress-disabled bridge required' }
if ($config.networks.'local-safe'.driver_opts.'com.docker.network.bridge.gateway_mode_ipv4' -ne 'nat') { throw 'NAT bridge gateway required for loopback-only published ports' }
if ($config.networks.'local-safe'.driver_opts.'com.docker.network.bridge.enable_ip_masquerade' -ne 'false') { throw 'IP masquerading must remain disabled' }
$readOnlyAppRoots = @('layer3_ontology','layer4_graph_intelligence','layer5_analytics_ai','layer6_dashboard/backend')
foreach ($root in $readOnlyAppRoots) {
    if (Get-ChildItem -LiteralPath $root -Filter '.env' -File -Recurse) { throw "Local credential file forbidden in safe source mount: $root" }
}
foreach ($number in 1..6) {
    $hasEmptyEnvMount = @($config.services."layer$number-api".volumes) -contains './local_safe/empty.env:/app/.env:ro'
    if (($number -le 2) -ne $hasEmptyEnvMount) { throw "Unexpected empty .env mount policy for layer$number-api" }
}
$forbidden = @('airflow-init','airflow-webserver','airflow-scheduler','airflow-worker','streaming-worker','ollama','ollama-init')
foreach ($property in $config.services.PSObject.Properties) {
    $name = $property.Name; $service = $property.Value
    if ($name -in $forbidden -or $service.build -or $service.network_mode -or $service.extra_hosts -or $service.privileged) { throw "Unsafe service configuration: $name" }
    if ($service.pull_policy -ne 'never' -or @($service.networks).Count -ne 1 -or $service.networks[0] -ne 'local-safe' -or $service.dns[0] -ne '127.0.0.1') { throw "Unsafe networking or pull policy: $name" }
    foreach ($port in $service.ports) { if (-not $port.StartsWith('127.0.0.1:')) { throw "Non-loopback port: $name" } }
    if ($name -like 'layer*-api' -and ($service.environment.LOCAL_SAFE_MODE -ne 'true' -or $service.entrypoint[1] -ne '/opt/satorix-safe/launch.py')) { throw "Missing safe launcher: $name" }
    & docker image inspect $service.image --format '{{.Id}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Image not cached: $($service.image). STOP: do not build or pull without approval." }
}
foreach ($property in $config.volumes.PSObject.Properties) {
    $volume = $property.Value
    if ($volume.external) {
        if ($volume.name -notmatch '^infracore_foundry_(frontend_shared|intelligence_node|operational_node|schema_node)_modules$') { throw 'Unapproved existing volume' }
        & docker volume inspect $volume.name --format '{{.Name}}' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Cached frontend dependencies missing: $($volume.name). No installation allowed." }
    }
}
# Do not inspect or reuse old data. Refuse simultaneous legacy services.
$legacyRunning = & docker ps --filter 'label=com.docker.compose.project=infracore_foundry' --format '{{.Names}}'
if ($LASTEXITCODE -ne 0 -or $legacyRunning) { throw 'Legacy Satorix containers must remain stopped.' }
$developmentRunning = & docker ps --filter 'label=com.docker.compose.project=satorix-development' --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect contained development containers.' }
if ($developmentRunning) { throw 'Development mode is running. Stop it with scripts/stop-satorix.ps1 -Mode Development before switching.' }
$unrestrictedRunning = & docker ps --filter 'label=com.docker.compose.project=satorix-unrestricted' --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Unrestricted containers.' }
if ($unrestrictedRunning) { throw 'Unrestricted mode is running. Stop it with scripts/stop-satorix.ps1 -Mode Unrestricted before switching.' }
Invoke-SafeCompose -Arguments @('config','--quiet')
if ($CheckOnly) { Write-Host 'Safe configuration and offline prerequisites checked; no services started.'; return }
try {
    # This Neo4j image can retain an unusable process state after Compose stop.
    # Recreate only its disposable container; the isolated fixture volume is preserved.
    Invoke-SafeCompose -Arguments @('rm','-f','neo4j')
    Invoke-SafeCompose -Arguments @('up','-d','--no-build','--pull','never','--wait','--wait-timeout','180','postgres','redis','kafka','neo4j','elasticsearch','minio')
    $networkPolicy = & docker network inspect satorix-local-safe_local-safe --format '{{.Internal}} {{index .Options "com.docker.network.bridge.enable_ip_masquerade"}}'
    if ($LASTEXITCODE -ne 0 -or $networkPolicy -ne 'false false') { throw 'Docker no-masquerade network policy not confirmed' }
    Invoke-SafeCompose -Arguments @('run','--rm','--no-deps','--pull','never','minio-init')
    foreach ($number in 1..6) {
        $serviceName = "layer$number-api"
        Invoke-SafeCompose -Arguments @('up','-d','--no-build','--pull','never','--no-deps',$serviceName)
        $endpoint = if ($number -eq 1) { '/ping' } elseif ($number -eq 3) { '/' } else { '/health' }
        $ready = $false
        foreach ($attempt in 1..30) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + (8000 + $number) + $endpoint) -TimeoutSec 2 -MaximumRedirection 0
                if ($response.StatusCode -eq 200) { $ready = $true; break }
            } catch { Start-Sleep -Seconds 2 }
        }
        if (-not $ready) { Invoke-SafeCompose -Arguments @('logs','--tail','40',$serviceName); throw "$serviceName failed safe startup. Do not download dependencies or bypass safety." }
    }
    Invoke-SafeCompose -Arguments @('up','-d','--no-build','--pull','never','--no-deps','intelligence-dashboard','operational-dashboard','schema-manager')
    foreach ($port in 3000..3002) {
        $ready = $false
        foreach ($attempt in 1..30) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 2
                $csp = $response.Headers['Content-Security-Policy']
                if ($response.StatusCode -eq 200 -and $csp -like "default-src 'self'*" ) { $ready = $true; break }
            } catch { Start-Sleep -Seconds 2 }
        }
        if (-not $ready) {
            $dashboard = @('intelligence-dashboard','operational-dashboard','schema-manager')[$port - 3000]
            Invoke-SafeCompose -Arguments @('logs','--tail','40',$dashboard)
            throw "$dashboard failed safe HTTP/CSP startup. Do not install dependencies or bypass safety."
        }
    }
    Write-Host 'Safe services launched. Review logs and browser CSP before functional testing. No sync, LLM, DAG or webhook execution is enabled.'
} catch {
    & docker @composeArgs stop
    throw
}
