# Local investigation workspace

Start Docker Desktop, then run from this directory:

```powershell
.\scripts\start-satorix.ps1 -Mode Development
.\scripts\load-company-demo.ps1
```

Sign in at http://127.0.0.1:3000 and open Amberbridge's Network Explorer.
Choose Copperfern to inspect one shortest path and the recorded shared director
and address. Paths traverse relationships in either direction and are limited
to the selected depth and enabled filters. No connection in the view does not
prove database-wide disconnection.

Choose a relationship, then select an `Open RROW-...` or other source-record
reference. The evidence panel shows the original sealed fixture CSV fields,
data-row ordinal (excluding the header), filename, SHA-256, and batch identity.
This is synthetic source data, not a government document or a claim that a live
external source was verified.

`GET /api/v1/evidence/fixtures/{record_id}` requires a valid dashboard JWT for
`LOCAL_SYNTHETIC_DEMO` and explicit `LOCAL_SAFE_MODE=true`. It accepts registered
record identifiers only, checks the fixture seal, and returns `Cache-Control:
no-store`. Other tenants, unrestricted mode, unknown IDs, and invalid fixture
content do not receive source rows. No file path or URL is accepted from callers.

Checks:

```powershell
python -S -m unittest tests.layer2.test_fixture_evidence tests.layer2.test_company_fixture_pipeline
cd layer6_dashboard\frontend\intelligence
.\node_modules\.bin\tsc.cmd --noEmit -p tsconfig.json
node tests\investigation.cjs
```
