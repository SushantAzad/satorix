$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8006/api/v1'
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType application/json -Body (@{
    email='admin@satorix.internal'; password='LocalFixtureAdminOnly123'
} | ConvertTo-Json)
$headers = @{Authorization=('Bearer '+$login.access_token)}
function Import-TestCsv($kind, $csv, $mapping) {
    $body = @{kind=$kind;source='CSV workflow smoke test';synthetic=$true;csv_text=$csv;mapping=$mapping}
    $preview = Invoke-RestMethod -Method Post -Uri "$base/imports/preview" -Headers $headers -ContentType application/json -Body ($body|ConvertTo-Json)
    if ($preview.status -ne 'ready') { throw ($preview|ConvertTo-Json -Depth 6) }
    $result = Invoke-RestMethod -Method Post -Uri "$base/imports/$($preview.import_id)/commit" -Headers $headers -ContentType application/json -Body '{}'
    if ($result.status -ne 'completed') { throw ($result|ConvertTo-Json -Depth 6) }
    $result
}
$company = Import-TestCsv 'company' "Code,Company`nCSV-SMOKE-C-001,SYNTHETIC CSV Orchard Company" @{id='Code';name='Company'}
$replay = Import-TestCsv 'company' "Code,Company`nCSV-SMOKE-C-001,SYNTHETIC CSV Orchard Company" @{id='Code';name='Company'}
if ($replay.results[0].status -ne 'unchanged') { throw 'Identical company replay changed data' }
$director = Import-TestCsv 'director' "id,name`nCSV-SMOKE-D-001,SYNTHETIC CSV River Person" @{id='id';name='name'}
$link = Import-TestCsv 'directorship' "director,company,date`nCSV-SMOKE-D-001,CSV-SMOKE-C-001,2025-01-01" @{director_id='director';company_id='company';appointed_date='date'}
$linkReplay = Import-TestCsv 'directorship' "director,company,date`nCSV-SMOKE-D-001,CSV-SMOKE-C-001,2025-02-01" @{director_id='director';company_id='company';appointed_date='date'}
$bad = @{kind='directorship';source='CSV workflow smoke test';csv_text="d,c`nCSV-MISSING-D,CSV-SMOKE-C-001";mapping=@{director_id='d';company_id='c'}}
$invalid = Invoke-RestMethod -Method Post -Uri "$base/imports/preview" -Headers $headers -ContentType application/json -Body ($bad|ConvertTo-Json)
if ($invalid.status -ne 'invalid' -or $invalid.import_id) { throw 'Broken reference was accepted' }
$profile = Invoke-RestMethod -Uri "$base/entities/company/CSV-SMOKE-C-001?refresh=true" -Headers $headers
$network = Invoke-RestMethod -Uri "$base/network/company/CSV-SMOKE-C-001?refresh=true" -Headers $headers
$report = Invoke-RestMethod -Method Post -Uri "$base/reports/generate" -Headers $headers -ContentType application/json -Body (@{entity_type='company';entity_id='CSV-SMOKE-C-001';report_type='corporate_due_diligence'}|ConvertTo-Json)
if ($report.report_content.sections.executive_summary.risk_score -ne $null) { throw 'Missing risk became zero' }
Write-Output 'PASS: entity imports, unchanged replay, directorship update, broken reference validation, profile/network/report requests'
$network | ConvertTo-Json -Depth 8
