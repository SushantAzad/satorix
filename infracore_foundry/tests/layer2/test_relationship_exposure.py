import copy
import unittest
from shared.relationship_exposure import relationship_exposure


def node(kind, key, score):
    return {"object_type": kind, "entityId": key, "name": key, "riskScore": score}


def edge(src_kind, src, dst_kind, dst, kind="DIRECTED", inferred=False):
    return {"sourceLabel": src_kind, "sourcePK": src, "targetLabel": dst_kind,
            "targetPK": dst, "type": kind, "isInferred": inferred,
            "properties": {"source_record_id": "test-evidence"}}


class ExposureTests(unittest.TestCase):
    def test_high_company_does_not_change_personal_score_and_deduplicates(self):
        e = edge("director", "D", "company", "C")
        graph = {"nodes": [node("director", "D", 0), node("company", "C", 70)], "edges": [e, e]}
        original = copy.deepcopy(graph)
        result = relationship_exposure("director", "D", graph)
        self.assertEqual(result["high_count"], 1)
        self.assertEqual(result["max_recorded_score"], 70)
        self.assertEqual(len(result["companies"][0]["relationships"]), 1)
        self.assertEqual(graph, original)

    def test_unknown_zero_and_thresholds(self):
        scores = [None, 0, 39, 40, 69, 70, 100, "70", -1, True]
        graph = {"nodes": [node("company", str(i), s) for i, s in enumerate(scores)],
                 "edges": [edge("director", "D", "company", str(i)) for i in range(len(scores))]}
        r = relationship_exposure("director", "D", graph)
        self.assertEqual((r["unknown_count"], r["low_count"], r["medium_count"], r["high_count"]), (4, 2, 2, 2))

    def test_indirect_inferred_address_and_missing_nodes_excluded(self):
        graph = {"nodes": [node("company", "C", 100), node("company", "C2", 100)],
                 "edges": [edge("director", "D2", "company", "C"),
                           edge("director", "D", "company", "C", inferred=True),
                           edge("director", "D", "company", "C2", "REGISTERED_AT"),
                           edge("director", "D", "company", "HIDDEN")]}
        self.assertEqual(relationship_exposure("director", "D", graph)["companies"], [])

    def test_ownership_direction_and_self_link(self):
        graph = {"nodes": [node("company", "A", 0), node("company", "B", 80)],
                 "edges": [edge("company", "B", "company", "A", "OWNS"),
                           edge("company", "A", "company", "A", "OWNS")]}
        self.assertEqual(relationship_exposure("company", "A", graph)["high_count"], 1)

    def test_no_connections_and_service_failure_are_distinct(self):
        empty = relationship_exposure("director", "D", {"nodes": [], "edges": []})
        failed = relationship_exposure("director", "D", None)
        self.assertEqual(empty["status"], "available")
        self.assertIsNone(empty["max_recorded_score"])
        self.assertEqual(failed["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
