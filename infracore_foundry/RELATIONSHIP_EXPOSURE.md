# Relationship exposure v1

Own recorded risk remains unchanged. A separate exposure panel on entity
profiles, network explorer (root and selected node), and company Intelligence
shows connected companies and their recorded scores. Newly generated reports
include the same exposure calculation and relationship evidence.

Rules:

- Only direct, recorded DIRECTED and OWNS links to company nodes count.
- Both directions are considered, with the actual direction shown in evidence.
- No transitive propagation, inferred links, shared-address propagation or
  automatic personal-risk increases.
- One company counts once, even if multiple links connect it.
- Bands: below 40 LOW, 40–69 MEDIUM, 70–100 HIGH.
- Missing, malformed or out-of-range scores remain unknown.
- Unavailable graph service is distinct from no qualifying links.
- Exposure is independent of the network display depth/checkboxes; the API
  retrieves depth 1 under the authenticated tenant's visibility rules.
- Maximum connected-company score is context only, not the subject's score.
- Appointments are recorded relationships, not proof of a current role.
  Temporal eligibility rules are not yet implemented.
- Synthetic labels are preserved. No real-world risk model is validated.

Try director TEST-RISK-D-006: own recorded score 0; one connected company
TEST-RISK-C-006 at 70/HIGH, review recommended.
TEST-RISK-D-009 demonstrates a connected company with unknown risk.

Small graphs (up to 12 nodes) now use a label-aware grid; larger graphs use a
force layout. Layout runs after element updates and fitting respects the actual
container dimensions. This fixes the initial async embedded-graph clustering
path without changing stored graph data.

Checks:

    python -B -m unittest tests.layer2.test_relationship_exposure tests.layer2.test_due_diligence
    node layer6_dashboard/frontend/intelligence/tests/graph-layout.cjs

Live API verification covered Person 06, unknown-risk connections and report
exposure, with own risk unchanged. Browser visual confirmation still requires a
signed-in in-app browser session.
