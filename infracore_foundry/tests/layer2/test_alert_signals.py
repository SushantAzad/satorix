import unittest
from shared.alert_signals import signals, reconcile
from shared.gemini_evidence import project_evidence


class SignalTests(unittest.TestCase):
    def graph(self, score=70, inferred=False):
        return {'nodes': [dict(object_type='director', entityId='D', riskScore=0),
                          dict(object_type='company', entityId='C', riskScore=score, synthetic=True)],
                'edges': [dict(sourceLabel='director', sourcePK='D', targetLabel='company', targetPK='C', type='DIRECTED', isInferred=inferred)]}

    def test_high_and_exposure(self):
        graph = self.graph()
        self.assertEqual(len(signals(graph)), 2)
        self.assertEqual(graph['nodes'][0]['riskScore'], 0)

    def test_invalid_scores_and_inferred(self):
        for score in [None, True, '90', -1, 101, float('nan'), 69]:
            self.assertEqual(signals(self.graph(score)), {})
        self.assertEqual(len(signals(self.graph(inferred=True))), 1)

    def test_idempotence_ack_and_changed_evidence(self):
        first = reconcile({}, signals(self.graph()), '2026-01-01')
        for a in first.values(): a['isAcknowledged'] = True
        same = reconcile(first, signals(self.graph()), '2026-01-02')
        self.assertTrue(all(a['isAcknowledged'] for a in same.values()))
        changed = reconcile(first, signals(self.graph(80)), '2026-01-03')
        self.assertTrue(all(not a['isAcknowledged'] for a in changed.values()))
        self.assertEqual(reconcile(first, {}, 'later'), {})

    def test_evidence_allowlist_and_stability(self):
        report = dict(entity_id='C', entity_type='company', synthetic=False,
                      sections={'entity_record': {'name': 'Real Co', 'password': 'secret', 'email': 'private'},
                                'relationship_snapshot': self.graph()})
        payload, digest = project_evidence(report)
        self.assertNotIn('secret', str(payload))
        self.assertNotIn('private', str(payload))
        self.assertEqual(payload['entity']['name'], 'Real Co')
        self.assertFalse(payload['synthetic'])
        self.assertEqual(digest, project_evidence(report)[1])
        report['synthetic'] = True
        self.assertNotEqual(digest, project_evidence(report)[1])


if __name__ == '__main__': unittest.main()
