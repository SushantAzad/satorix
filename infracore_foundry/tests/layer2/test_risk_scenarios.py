import unittest
from shared.risk_scenarios import build_risk_scenarios


class RiskScenariosTests(unittest.TestCase):
    def test_expected_scores_and_coverage(self):
        objects, links = build_risk_scenarios()
        companies = [p for kind, p in objects if kind == "company"]
        self.assertEqual([p['riskScore'] for p in companies], [0,15,30,40,55,70,85,100,None,39,69,70])
        self.assertEqual(len(objects), 40)
        self.assertEqual(len(links), 36)
        self.assertTrue(all(p['synthetic'] for _, p in objects))

    def test_replay_is_deterministic_and_references_resolve(self):
        objects, links = build_risk_scenarios()
        self.assertEqual((objects, links), build_risk_scenarios())
        fields = {'company':'cin','director':'din','project':'projectId','address':'normalizedAddress'}
        ids = {(kind, p[fields[kind]]) for kind, p in objects}
        self.assertEqual(len(ids), 40)
        for link in links:
            self.assertIn((link['source_type'], link['source_id']), ids)
            self.assertIn((link['target_type'], link['target_id']), ids)

    def test_unassessed_is_not_zero(self):
        objects, _ = build_risk_scenarios()
        missing = next(p for kind, p in objects if kind == 'company' and p['cin'] == 'TEST-RISK-C-009')
        self.assertIsNone(missing['riskScore'])
        self.assertEqual(missing['riskAssessmentStatus'], 'UNASSESSED')
