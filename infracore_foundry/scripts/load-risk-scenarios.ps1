[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8003/ingest/risk-scenarios' -Headers @{'X-API-Key'='local-fixture-api-key-not-production'}
$result | Format-List
Write-Host 'Search RISK LAB in the Intelligence dashboard. IDs: TEST-RISK-C-001 through TEST-RISK-C-012.'
Write-Host 'Synthetic scenario rule scores only; this loader tests ontology, search, profiles and graphs, not Layer 1 ingestion or production risk models.'
