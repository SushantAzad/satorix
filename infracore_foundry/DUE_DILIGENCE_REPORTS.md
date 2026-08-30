# Due-diligence reports

Report Center now generates fresh available-data snapshots through the dashboard
API without requiring external connectors or LLM requests.

## Try it

1. Sign in at http://127.0.0.1:3000.
2. Open a company profile and select Due Diligence, or open Report Center.
3. Generate for TEST-RISK-C-008 (100/HIGH), TEST-RISK-C-009 (unknown/NONE),
   or DEMO-C-001 (0/LOW).
4. Inspect the preview, reopen with View, or Download JSON.

Snapshots contain recorded entity properties, risk, depth-limited network,
source metadata, limitations and a manual review checklist. Synthetic fixtures
are explicitly identified. Missing risk remains null, not zero.

Reports are stored for 24 hours and scoped to both the authenticated user and
tenant. Generating again creates a new snapshot. Download JSON to retain a copy.
Save failures return errors, never successful report IDs.

Only the available-data due-diligence template is supported in Report Center.
Regulatory exposure, portfolio health and peer comparison are not represented as
completed specialist reports. Existing legacy reports without tenant metadata
are not exposed by the new endpoints; no old records were deleted.
PDF export and independently verified external-source analysis are not implemented.
The separate Layer 5 report endpoints are unchanged by this dashboard fix.

## Verification

- python -m unittest tests.layer2.test_due_diligence -v
- layer6_dashboard/frontend/intelligence/node_modules/.bin/tsc.cmd --noEmit -p layer6_dashboard/frontend/intelligence/tsconfig.json
- Live dashboard API: generate, fetch saved report, list; high, zero and unknown risk.

The Layer 3 entity detail route no longer uses the legacy non-tenant-keyed cache.
It queries the tenant-filtered database for each detail request.
