# Local CSV import

Open http://127.0.0.1:3000/imports in the focused dashboard and sign in with a platform administrator or
data steward account.
The local fixture account is admin@satorix.internal / LocalFixtureAdminOnly123.

## Workflow

1. Choose Companies; download the synthetic template or select your UTF-8 CSV.
2. Set a meaningful source label and whether new records are synthetic.
3. Map columns, validate, and inspect the normalized rows.
4. Confirm import. Review accepted/failed rows and saved history.
5. Repeat for Directors, then Directorships.
6. Search the company in Intelligence and open its network and due-diligence report.

Safe mode blocks imports. Development allows these local writes without enabling
external connectors. No mode is switched automatically.

## Contract and limits

- Maximum 256 KB, 200 data rows, 40 columns.
- Company: id, name required; status, registeredAddress optional.
- Director: id, name required.
- Directorship: director_id, company_id required; appointed_date optional.
- IDs are stable internal keys, not verified CIN/DIN registrations.
- Existing records are merged; blank optional cells preserve existing values.
- Duplicate identities inside a file and broken directorship references reject
  the preview. A confirmed preview is revalidated against current relationships.
- Identical entity files are unchanged on replay. Directorship writes serialize
  by identity, update existing properties, and do not insert another relationship.
- Each ontology row commits independently. Runtime errors can leave partial
  imports. Do not assume a network timeout means nothing was written.
- Previews/results persist in PostgreSQL and are scoped to user plus tenant.
  No client ID is accepted from the browser. Confirmation uses saved rows.
- Source label, file SHA-256 and CSV row number are retained as provenance.
  Original unmapped columns/file bytes are not archived in this first version.
- This goes directly to Layer 3 through its write funnel, not the complete
  Layer 1/2 connector/pipeline workflow.
- Address text is imported as a profile property; automatic address entities,
  ownership relationships, risk calculation, large-file/background jobs and
  original-file evidence viewing are not yet part of this feature.
- Focused search and graph read PostgreSQL directly, not separate projections.
  Frontend caches may briefly show older data; refresh after imports.
  Historical full-stack projections are not reconciled automatically.
- Import history includes unconfirmed previews; no retention cleanup is provided yet.

## Checks

- python -m unittest tests.layer2.test_csv_import -v
- scripts/test-csv-import.ps1 (writes named synthetic smoke-test records only)
- Intelligence frontend TypeScript check.

The smoke test imports company CSV-SMOKE-C-001 and director CSV-SMOKE-D-001,
replays the company and updates their directorship. It also checks rejected
references and requests the resulting profile, network and report.
