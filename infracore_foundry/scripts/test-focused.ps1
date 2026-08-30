$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8006/api/v1'
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType application/json -Body (@{
    email='admin@satorix.internal'; password='LocalFixtureAdminOnly123'
}|ConvertTo-Json)
$headers = @{Authorization=('Bearer '+$login.access_token)}
$analysis = Invoke-RestMethod -Uri "$base/focused-intelligence/CSV-SMOKE-C-001" -Headers $headers
if ($analysis.directors -notcontains 'CSV-SMOKE-D-001') { throw 'Intelligence director analysis failed' }
if ($null -ne $analysis.risk_score) { throw 'Unknown risk became zero' }
$search = Invoke-RestMethod -Uri "$base/entities/search?q=Orchard" -Headers $headers
if ($search.results.entityId -notcontains 'CSV-SMOKE-C-001') { throw 'PostgreSQL search failed' }
$other = @{'X-API-Key'='local-fixture-api-key-not-production';'X-Client-ID'='OTHER-TEST-TENANT'}
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8003/search?q=Orchard' -Headers $other
if ($result.results.Count -ne 0) { throw 'Tenant isolation failed' }
Write-Output 'PASS: focused intelligence, PostgreSQL search, unknown risk and tenant isolation'
