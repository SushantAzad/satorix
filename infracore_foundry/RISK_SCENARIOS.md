# Synthetic risk scenario pack

Run `scripts/load-risk-scenarios.ps1` while contained Development mode is running.
Search for `RISK LAB`, or individual names below. The existing Amberbridge fixture
is unchanged. All added rows belong to `LOCAL_SYNTHETIC_DEMO` and use a separate
`TEST-RISK-*` identity namespace (not government identifiers).

The pack creates 12 companies, 12 directors, 12 projects, four shared addresses,
and 36 relationships through the Layer 3 object funnel. Repeated loads reuse
the same identities. This is a dashboard/ontology test pack, not a Layer 1/2
connector ingestion test or a validation of production risk models.

Company IDs TEST-RISK-C-001 through TEST-RISK-C-012:

- Clearwater Stable: 0 (LOW)
- Sunmeadow Minor Delay: 15 (LOW)
- Pineharbor Review: 30 (LOW)
- Ambervale Threshold: 40 (MEDIUM)
- Coppercloud Governance: 55 (MEDIUM)
- Redwillow Elevated: 70 (HIGH)
- Stormglass Multi Signal: 85 (HIGH)
- Crimsonpeak Maximum: 100 (HIGH)
- Mistfield Missing Metrics: unassessed (NONE, not a measured zero)
- Limebrook Below Medium: 39 (LOW)
- Goldreef Below High: 69 (MEDIUM)
- Rubyshore High Boundary: 70 (HIGH)

Scores sum four explicitly synthetic input components, capped at 100:
financial stress (0–35), regulatory exposure (0–30), governance issues (0–20),
and delivery delays (0–15). Missing inputs yield an unassessed result.
Directors use governance inputs only; projects use the four scenario components;
addresses are unassessed. These rules are deliberately test-only, not calibrated
financial probabilities, allegations, or legal assessments.

The profile summary explains each component. Search and graph colors use LOW
below 40, MEDIUM from 40 to 69, HIGH from 70, and gray for unassessed values.
Legacy dashboard numeric fields retain zero for an absent score, but their band
is NONE and risk badges display UNSCORED rather than a numeric assessment.

Verify: `python -S -m unittest tests.layer2.test_risk_scenarios`.
