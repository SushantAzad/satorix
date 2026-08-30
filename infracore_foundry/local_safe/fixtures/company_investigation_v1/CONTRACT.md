# Local synthetic company investigation: fixture contract v1

## Scope and safety

This package is a specification and local fixture consistency test, not an importer,
pipeline, database migration, fuzzy matcher, graph service, or runtime integration
test. No runtime implementation or permission is enabled by these files.

Every company, person, address, and identifier is invented for this demonstration.
Names carry a SYNTHETIC marker. DEMO-C/DEMO-D/DEMO-A identifiers are not government
identifiers and must never be looked up externally. No real geography or credentials
are needed. The existing CIN/DIN validators are **not compatible** with these IDs;
a later separately approved bounded adapter/identity decision is required. Do not
fabricate CIN/DIN-shaped values or weaken validators as part of this package.

The existing relationship names and directions remain:

- Director -> DIRECTED -> Company
- Company -> REGISTERED_AT -> Address

No runtime source, Docker configuration, or Local Safe policy changes are included.

## Inputs and outcomes

All CSVs are UTF-8, header-first, with unique source_record_id values. The four
`*_initial.csv` files form one initial batch. `companies_update.csv` is a subsequent
patch batch, not a replacement snapshot. Blank CSV cells represent missing values.
Line 1 is the header; data row 1 is physical CSV line 2. There are no multiline cells.

Initial counts: companies 11 = 8 accepted + 2 rejected + 1 review; directors 4 =
3 accepted + 1 rejected; addresses 4 = 3 accepted + 1 rejected; directorships 5 =
4 accepted + 1 rejected. Total: **24 = 18 accepted + 5 rejected + 1 review**.

Accepted means structurally valid and eligible for publication, even when merged
into an existing identity. Eight accepted company rows yield five companies;
three rows are consolidated, of which one is an exact duplicate excluding its
source_record_id. Review rows are not accepted and are not published. Rejections
and review decisions retain original values and reason codes.

Expected initial state: **5 Companies + 3 Directors + 3 Addresses = 11 entities**;
**4 DIRECTED + 5 REGISTERED_AT = 9 active relationships**. Directorships are links,
not additional entities. Provenance and change records are not ontology entities.

`expected_results.json` contains the exhaustive row outcomes/canonical mappings,
canonical properties, initial links and evidence, all ten company-pair scores,
updated active link keys, changes, and replay expectations.

## Required fields and normalization

- Company: source_record_id, company_id, company_name, address_id, status.
  A missing company_id with an otherwise usable record goes to review; an invalid
  nonempty ID or missing name is rejected. Status is active or paused for this demo.
- Director: source_record_id, director_id, director_name.
- Address: source_record_id, address_id, address_text.
- Directorship: source_record_id, director_id, company_id, appointed_date (ISO date).
  Both endpoints must resolve to accepted canonical entities.
- Update: same columns as Company; must reference an existing accepted company and
  address. Absent companies/directorships/addresses are unchanged, never deleted.

Valid fixture IDs match DEMO-C-[0-9]{3}, DEMO-D-[0-9]{3}, DEMO-A-[0-9]{3}.
Trim/collapse whitespace in display strings. Address normalization additionally
case-folds text. Preserve the original values in evidence. Within an initial batch,
the lowest source_record_id selects a canonical company's display name; preserve
all other names as aliases. Sorting makes this independent of CSV row order.

Company identity is its explicit synthetic ID, not a name hash. Equal IDs with name
variants consolidate; conflicting IDs must not merge on name similarity. CROW-011
has no authoritative ID and is a plausible candidate for DEMO-C-001: it remains
unpublished pending review. No numeric fuzzy confidence is claimed or fabricated.
Later resolver integration must respect its configured threshold and never promote
this candidate automatically. This package tests the expected hold, not the actual
production resolver's scoring. Address fixture IDs reference normalizedAddress,
the existing ontology's natural address key. Any future adapter must preserve that
mapping and the source ID; it must not silently replace the existing natural key.

## Bounded Layer 2 -> Layer 3 boundary (proposed, not implemented)

Use `contract_version=local-company-investigation/v1`,
`dataset_id=synthetic-company-investigation`,
`source_id=local-synthetic-company-fixtures-v1`, and
`client_id=LOCAL_SYNTHETIC_DEMO` throughout. No PLATFORM_GLOBAL fallback for this
dataset. No tenant isolation guarantee is asserted by this fixture package.

L1 raw storage: raw-data bucket. L2 output and the manifest: processed-data bucket.
The proposed prefix is
`local-company-investigation/<source_id>/<batch_id>/<dataset_version>/`.
Manifest entries explicitly name entity kind, object key, schema, SHA-256 checksum,
and row count. Neither a filename stem nor a run ID determines the source/entity
type. L3 must use manifest locations, not discover files in the raw bucket.

Required manifest fields:

- contract_version, dataset_id, source_id, client_id, batch_id, run_id;
- input_checksum, pipeline_version, dataset_version;
- operation: initial or update; update also carries predecessor_batch_id;
- files: exact bucket/key/checksum/entity kind/schema/count;
- input/accepted/rejected/review counts, and processing completion status.

Content identity is defined without timestamps: for each approved input file, in
lexicographic filename order, append UTF-8 filename, NUL, lowercase SHA-256 of its
exact bytes, and LF. SHA-256 that byte sequence to obtain input_checksum.
batch_id is SHA-256 of UTF-8 client_id + NUL + source_id + NUL + input_checksum.
Names, contents, and line endings therefore participate in identity; replay means
the same file set and bytes, not merely similar rows. The test implements this
checksum recipe in memory and checks that initial/update inputs differ.

pipeline_version is a fixed version of the selected transformation configuration.
dataset_version is `<batch_id>:<pipeline_version>` for this bounded fixture flow.
run_id identifies an execution attempt and is never an entity key. An already
applied (client_id, source_id, batch_id, pipeline_version) returns its prior result;
pipeline-version reprocessing is outside this MVP contract. A future runtime may
record an attempt audit without duplicating business data, evidence, or changes.

Processed records must retain: source_record_id, original file/CSV line, source_id,
batch_id, run_id, dataset_version, client_id, canonical type/key, resolution outcome,
normalized properties, and evidence references. Relationship records additionally
carry type, source canonical key, target canonical key, and source-record evidence.
Map company_name/director_name -> name, address_text -> fullAddress and
normalizedAddress, appointed_date -> appointedDate. Keep required ontology
properties explicit. This is not a claim that existing API inputs already accept
these fields or the synthetic identities.

Evidence identity is (client_id, source_id, batch_id, filename, source_record_id).
Row IDs in expected_results.json are short references to those qualified records.
Every accepted entity is traceable through its row mapping. Each initial link lists
its assertion and endpoint evidence. Multiple rows supporting one fact must not
create duplicate edges. Exact duplicates have distinct evidence but one fact.

## Graph questions and signal

For Company 001, Director 001 serves both it and Company 002. Both companies are
registered at Address 001. Companies 003 and 005 share Address 002. Company 004
uses Address 003 and Director 003. Company 005 has no supplied directorship; this
means no observed link, not a claim about the fictional company's legal status.

Compute per unordered pair of distinct companies from current links only:
shared director +1; shared address +1; both types +1. Each rule contributes at most
once, regardless of supporting-row or director counts. Scores are 0..3, not ML,
probabilities, risk calibration, or allegations. Return rules and supporting paths
with evidence in the future runtime. Initially 001/002 scores 3 and 003/005 scores
1; all other pairs score 0. There are two valid shortest paths of length two between
001 and 002. Tests accept either; do not depend on database tie ordering.

## Update and replay

The one accepted update row preserves Company 002's ID, changes its display name
and status, and moves it from existing Address 001 to existing Address 003. Preserve
the old name as an alias and all old evidence. One logical company-change event
contains the before/after fields and UROW-001 evidence; storage may use multiple
physical records. Retire the old REGISTERED_AT from current traversal and add the
new edge with update/address evidence. Keep the old assertion in history; do not
overwrite it or remove Address 001. Unchanged DIRECTED assertions retain their
original evidence. Entity and active-link counts stay 11 and 9. Retired physical
history records are not counted as active graph links.

After update, 001/002 scores 1, 002/004 scores 1, 003/005 scores 1, others 0.
Replaying initial before update, update after update, or initial after update adds
zero canonical entities, edges, evidence records, or logical change events. In the
last case, do not roll back the newer state. Return already_applied. The future
runtime must persist this decision; a fixture test cannot establish persistence,
concurrency safety, database idempotency, or cross-store consistency.

## Local validation

From the repository root, run:

    python -B local_safe/fixtures/company_investigation_v1/test_consistency.py

Uses only Python standard-library imports and files in this package. It performs
no writes, imports no Satorix runtime modules, opens no sockets, and starts no
services. It validates a local expected-state oracle, including replay semantics,
not the future application implementation. No dependencies need installation.
