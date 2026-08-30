$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8006/api/v1'
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType application/json -Body (@{
    email='admin@satorix.internal'; password='LocalFixtureAdminOnly123'
}|ConvertTo-Json)
$headers = @{Authorization=('Bearer '+$login.access_token)}
$scan = Invoke-RestMethod -Method Post -Uri "$base/alerts/scan" -Headers $headers
if ($scan.total -lt 1) { throw 'No signals generated: load synthetic risk fixtures first' }
$alerts = Invoke-RestMethod -Uri "$base/alerts?limit=200" -Headers $headers
$target = $alerts.alerts | Where-Object { $_.affectedEntityId -eq 'TEST-RISK-D-006' } | Select-Object -First 1
if (-not $target) { throw 'Expected synthetic director exposure missing' }
$ack = Invoke-RestMethod -Method Patch -Uri "$base/alerts/$($target.alertId)/acknowledge" -Headers $headers -ContentType application/json -Body '{}'
if (-not $ack.isAcknowledged) { throw 'Acknowledgement failed' }
$null = Invoke-RestMethod -Method Post -Uri "$base/alerts/scan" -Headers $headers
$detail = Invoke-RestMethod -Uri "$base/alerts/$($target.alertId)" -Headers $headers
if (-not $detail.isAcknowledged) { throw 'Repeat scan lost acknowledgement' }
$filtered = Invoke-RestMethod -Uri "$base/alerts?acknowledged=false" -Headers $headers
if ($filtered.alerts.alertId -contains $target.alertId) { throw 'Acknowledgement filter failed' }
$report = Invoke-RestMethod -Method Post -Uri "$base/reports/generate" -Headers $headers -ContentType application/json -Body '{"entity_type":"director","entity_id":"TEST-RISK-D-006","report_type":"corporate_due_diligence"}'
$preview = Invoke-RestMethod -Uri "$base/gemini/reports/$($report.report_id)/preview" -Headers $headers
if ($preview.payload.entity_id -ne 'TEST-RISK-D-006' -or $preview.sha256.Length -ne 64) { throw 'Evidence preview failed' }
$config = Invoke-RestMethod -Uri "$base/gemini/status" -Headers $headers
Write-Output "PASS: $($scan.total) persisted signals; synthetic director exposure, acknowledgement, repeat scan, filters and Gemini evidence preview. Gemini ready: $($config.ready). No provider request made."
