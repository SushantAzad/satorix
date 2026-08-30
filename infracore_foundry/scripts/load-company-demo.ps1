[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$apiKey = 'local-fixture-api-key-not-production'
$headers = @{ 'X-API-Key' = $apiKey }
$body = @{ fixture_id = 'company_investigation_v1' } | ConvertTo-Json

$l1 = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8001/api/v1/fixtures/import' -Headers $headers -ContentType 'application/json' -Body $body
$l2 = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8002/fixtures/company-investigation/process' -Headers $headers -ContentType 'application/json' -Body $body
$l3Body = @{
    fixture_id = 'company_investigation_v1'
    manifest_bucket = $l2.manifest_bucket
    manifest_key = $l2.manifest_key
} | ConvertTo-Json
$l3 = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8003/ingest/fixture' -Headers $headers -ContentType 'application/json' -Body $l3Body

$login = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8006/api/v1/auth/login' -ContentType 'application/json' -Body (@{
    email = 'admin@satorix.internal'
    password = 'LocalFixtureAdminOnly123'
} | ConvertTo-Json)
$dashboardHeaders = @{ Authorization = "Bearer $($login.access_token)" }
$null = Invoke-RestMethod -Uri 'http://127.0.0.1:8006/api/v1/entities/company/DEMO-C-001?refresh=true' -Headers $dashboardHeaders
$network = Invoke-RestMethod -Uri 'http://127.0.0.1:8006/api/v1/network/company/DEMO-C-001?depth=2&refresh=true' -Headers $dashboardHeaders

[pscustomobject]@{
    Layer1 = $l1.status
    Layer2 = $l2.status
    Layer3 = $l3.status
    RawRecords = $l1.records_extracted
    ObjectsWritten = $l3.objects_written
    LinksWritten = $l3.links_written
    NetworkEntities = $network.metadata.entityCount
    NetworkRelationships = $network.metadata.relationshipCount
    CompanyProfile = 'http://127.0.0.1:3000/entity/company/DEMO-C-001'
}
