"""Read-only fixture oracle; does not test or import the Satorix runtime."""
import copy
import csv
import hashlib
import itertools
import json
from pathlib import Path
import re
import unittest
from datetime import date


ROOT = Path(__file__).resolve().parent
FILES = (
    "companies_initial.csv", "directors_initial.csv",
    "addresses_initial.csv", "directorships_initial.csv",
)


def clean(value):
    return " ".join(value.split())


def valid_id(value, kind):
    return re.fullmatch(r"DEMO-" + kind + r"-[0-9]{3}", value) is not None


def edge_key(edge):
    return "|".join(edge[key] for key in ("type", "source", "target"))


def content_identity(filenames, expected):
    payload = b"".join(
        name.encode() + b"\0" + hashlib.sha256((ROOT / name).read_bytes()).hexdigest().encode() + b"\n"
        for name in sorted(filenames)
    )
    checksum = hashlib.sha256(payload).hexdigest()
    batch = hashlib.sha256(
        (expected["client_id"] + "\0" + expected["source_id"] + "\0" + checksum).encode()
    ).hexdigest()
    return checksum, batch


def pair_scores(company_ids, relationships):
    directors = {key: set() for key in company_ids}
    addresses = {key: set() for key in company_ids}
    for edge in relationships:
        if edge["type"] == "DIRECTED":
            directors[edge["target"]].add(edge["source"])
        elif edge["type"] == "REGISTERED_AT":
            addresses[edge["source"]].add(edge["target"])
        else:
            raise AssertionError("Unexpected relationship type")
    result = {}
    for a, b in itertools.combinations(sorted(company_ids), 2):
        shared_director = bool(directors[a] & directors[b])
        shared_address = bool(addresses[a] & addresses[b])
        result[a + "|" + b] = int(shared_director) + int(shared_address) + int(shared_director and shared_address)
    return result


class FixtureConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((ROOT / "expected_results.json").read_text(encoding="utf-8"))
        cls.rows = {}
        for name in (*FILES, "companies_update.csv"):
            with (ROOT / name).open(encoding="utf-8", newline="") as stream:
                cls.rows[name] = list(csv.DictReader(stream))

    def outcomes(self):
        """Minimal declared fixture validation; no fuzzy-scoring implementation."""
        result = {name: {"accepted": {}, "rejected": {}, "review": {}} for name in FILES}
        for name in FILES:
            for row in self.rows[name]:
                decision, value = "accepted", None
                if name == "companies_initial.csv":
                    value = row["company_id"]
                    if not clean(row["company_name"]):
                        decision, value = "rejected", "missing_company_name"
                    elif not value:
                        decision, value = "review", "missing_authoritative_company_id"
                    elif not valid_id(value, "C"):
                        decision, value = "rejected", "invalid_company_id"
                elif name == "directors_initial.csv":
                    value = row["director_id"]
                    if not valid_id(value, "D"):
                        decision, value = "rejected", "invalid_director_id"
                elif name == "addresses_initial.csv":
                    value = row["address_id"]
                    if not clean(row["address_text"]):
                        decision, value = "rejected", "missing_address_text"
                else:
                    value = "DIRECTED|" + row["director_id"] + "|" + row["company_id"]
                    if row["company_id"] not in result[FILES[0]]["accepted"].values():
                        decision, value = "rejected", "unknown_company_reference"
                result[name][decision][row["source_record_id"]] = value
        return result

    def initial_state(self):
        outcomes = self.outcomes()
        entities = {"Company": {}, "Director": {}, "Address": {}}
        evidence = {}
        for name, kind in zip(FILES[:3], entities):
            for row in sorted(self.rows[name], key=lambda r: r["source_record_id"]):
                rid = row["source_record_id"]
                if rid not in outcomes[name]["accepted"]:
                    continue
                key = outcomes[name]["accepted"][rid]
                evidence.setdefault(key, []).append(rid)
                if kind == "Company":
                    value = {"name": clean(row["company_name"]), "status": row["status"], "address_id": row["address_id"]}
                elif kind == "Director":
                    value = {"name": clean(row["director_name"])}
                else:
                    value = {"normalizedAddress": clean(row["address_text"]).casefold()}
                entities[kind].setdefault(key, value)
        links = []
        for row in self.rows[FILES[3]]:
            rid = row["source_record_id"]
            if rid in outcomes[FILES[3]]["accepted"]:
                d, c = row["director_id"], row["company_id"]
                links.append({"type": "DIRECTED", "source": d, "target": c, "evidence": [rid] + evidence[d] + evidence[c]})
        for c, properties in entities["Company"].items():
            a = properties["address_id"]
            links.append({"type": "REGISTERED_AT", "source": c, "target": a, "evidence": evidence[c] + evidence[a]})
        return entities, links

    def test_csv_structure_and_synthetic_values(self):
        headers = {
            FILES[0]: ["source_record_id", "company_id", "company_name", "address_id", "status"],
            FILES[1]: ["source_record_id", "director_id", "director_name"],
            FILES[2]: ["source_record_id", "address_id", "address_text"],
            FILES[3]: ["source_record_id", "director_id", "company_id", "appointed_date"],
        }
        headers["companies_update.csv"] = headers[FILES[0]]
        row_ids = []
        for name, rows in self.rows.items():
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(list(row), headers[name])
                self.assertNotIn(None, row.values())
                row_ids.append(row["source_record_id"])
                for field in ("company_name", "director_name", "address_text"):
                    if row.get(field):
                        self.assertTrue(clean(row[field]).casefold().startswith("synthetic "))
                if "appointed_date" in row:
                    self.assertEqual(date.fromisoformat(row["appointed_date"]).isoformat(), row["appointed_date"])
        self.assertEqual(len(row_ids), len(set(row_ids)))

    def test_exact_outcomes_counts_and_references(self):
        outcomes = self.outcomes()
        self.assertEqual(outcomes, self.expected["initial"]["outcomes"])
        counts = self.expected["initial"]["counts"]
        self.assertEqual(sum(len(self.rows[name]) for name in FILES), counts["input_rows"])
        for decision in ("accepted", "rejected", "review"):
            self.assertEqual(sum(len(item[decision]) for item in outcomes.values()), counts[decision + "_rows"])
        self.assertEqual(counts["input_rows"], sum(counts[key + "_rows"] for key in ("accepted", "rejected", "review")))
        entities, _ = self.initial_state()
        for name in FILES:
            for row in self.rows[name]:
                if row["source_record_id"] not in outcomes[name]["accepted"]:
                    continue
                for field, kind, prefix in (("company_id", "Company", "C"), ("director_id", "Director", "D"), ("address_id", "Address", "A")):
                    if field in row:
                        self.assertTrue(valid_id(row[field], prefix))
                        self.assertIn(row[field], entities[kind])
                if "status" in row:
                    self.assertIn(row["status"], ("active", "paused"))

    def test_duplicates_variants_and_review(self):
        rows = self.rows[FILES[0]]
        groups = {}
        accepted = self.outcomes()[FILES[0]]["accepted"]
        payloads = []
        for row in rows:
            if row["source_record_id"] in accepted:
                groups.setdefault(row["company_id"], []).append(row)
                payloads.append(tuple((k, v) for k, v in row.items() if k != "source_record_id"))
        counts = self.expected["initial"]["counts"]
        self.assertEqual(len(payloads) - len(set(payloads)), counts["exact_duplicate_company_rows"])
        self.assertEqual(len(payloads) - len(groups), counts["company_rows_consolidated"])
        self.assertEqual(len({r["company_name"] for r in groups["DEMO-C-001"]}), 3)
        review = self.expected["initial"]["review_candidates"]
        self.assertEqual(set(review), set(self.outcomes()[FILES[0]]["review"]))
        for rid, entry in review.items():
            row = next(r for r in rows if r["source_record_id"] == rid)
            self.assertFalse(row["company_id"])
            self.assertEqual(entry["decision"], "review")
            self.assertFalse(entry["automatic_merge"])
            self.assertFalse(entry["published"])
            self.assertEqual(entry["candidate_company_ids"], ["DEMO-C-001"])
            self.assertIn("amberbridge", row["company_name"].casefold())

    def test_canonical_entities_links_and_evidence(self):
        entities, links = self.initial_state()
        expected = self.expected["initial"]
        self.assertEqual(entities, expected["canonical_entities"])
        self.assertEqual(sum(map(len, entities.values())), expected["counts"]["canonical_entity_count"])
        self.assertEqual(links, expected["active_relationships"])
        self.assertEqual(len(links), expected["counts"]["active_relationship_count"])
        self.assertEqual(len(links), len({edge_key(edge) for edge in links}))
        source_locations = {row["source_record_id"]: (name, line) for name in FILES for line, row in enumerate(self.rows[name], 2)}
        accepted = {rid for item in self.outcomes().values() for rid in item["accepted"]}
        for edge in links:
            source_type, target_type = ("Director", "Company") if edge["type"] == "DIRECTED" else ("Company", "Address")
            self.assertIn(edge["source"], entities[source_type])
            self.assertIn(edge["target"], entities[target_type])
            self.assertTrue(edge["evidence"])
            self.assertEqual(len(edge["evidence"]), len(set(edge["evidence"])))
            for rid in edge["evidence"]:
                self.assertIn(rid, accepted)
                self.assertIn(rid, source_locations)
                self.assertGreaterEqual(source_locations[rid][1], 2)

    def test_scores_and_graph_questions(self):
        entities, links = self.initial_state()
        self.assertEqual(self.expected["signal"]["rules"], {"shared_director": 1, "shared_address": 1, "multiple_relationship_types": 1})
        scores = pair_scores(entities["Company"], links)
        self.assertEqual(scores, self.expected["initial"]["pair_scores"])
        # Duplicate assertions must not inflate a signal.
        self.assertEqual(scores, pair_scores(entities["Company"], links + links))
        query = self.expected["initial"]["investigation"]
        start = query["company"]
        directors = {e["source"] for e in links if e["type"] == "DIRECTED" and e["target"] == start}
        addresses = {e["target"] for e in links if e["type"] == "REGISTERED_AT" and e["source"] == start}
        self.assertEqual(sorted(directors), query["directors"])
        self.assertEqual(sorted({e["target"] for e in links if e["type"] == "DIRECTED" and e["source"] in directors} - {start}), query["shared_director_companies"])
        self.assertEqual(sorted({e["source"] for e in links if e["type"] == "REGISTERED_AT" and e["target"] in addresses} - {start}), query["shared_address_companies"])
        adjacency = {}
        for edge in links:
            a, b = edge["source"], edge["target"]
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        paths = [[start]]
        found = []
        while paths and not found:
            found = [p for p in paths if p[-1] == query["shortest_path_target"]]
            if not found:
                paths = [p + [n] for p in paths for n in sorted(adjacency[p[-1]]) if n not in p]
        self.assertEqual(sorted(found), sorted(query["allowed_shortest_paths"]))
        self.assertTrue(all(len(p) - 1 == query["shortest_path_hops"] for p in found))
        reached, pending = set(), [start]
        while pending:
            node = pending.pop()
            if node not in reached:
                reached.add(node)
                pending.extend(adjacency[node] - reached)
        self.assertNotIn(query["disconnected_target"], reached)

    def test_update_and_replay_specification(self):
        entities, links = self.initial_state()
        spec = self.expected["update"]
        rows = self.rows[spec["file"]]
        self.assertEqual(len(rows), spec["counts"]["input_rows"])
        self.assertEqual(len(rows), spec["counts"]["accepted_rows"])
        self.assertEqual(spec["counts"]["rejected_rows"] + spec["counts"]["review_rows"], 0)
        self.assertEqual({r["source_record_id"]: r["company_id"] for r in rows}, spec["canonical_mappings"])
        initial_batch = content_identity(FILES, self.expected)[1]
        update_batch = content_identity([spec["file"]], self.expected)[1]
        self.assertEqual(content_identity(FILES, self.expected), content_identity(tuple(reversed(FILES)), self.expected))
        self.assertNotEqual(initial_batch, update_batch)
        applied = {initial_batch}
        history, retired, added = [], [], []
        original_entities = copy.deepcopy(entities)
        original_links = copy.deepcopy(links)

        def apply_update_once():
            # In-memory specification only: no claim about runtime persistence.
            if update_batch in applied:
                return "already_applied"
            for row in rows:
                key = row["company_id"]
                self.assertIn(key, entities["Company"])
                self.assertIn(row["address_id"], entities["Address"])
                self.assertTrue(valid_id(key, "C"))
                self.assertIn(row["status"], ("active", "paused"))
                before = copy.deepcopy(entities["Company"][key])
                after = {"name": clean(row["company_name"]), "status": row["status"], "address_id": row["address_id"]}
                history.append({"entity_id": key, "source_record_id": row["source_record_id"], "before": before, "after": after})
                entities["Company"][key] = after
                for edge in list(links):
                    if edge["type"] == "REGISTERED_AT" and edge["source"] == key:
                        retired.append(edge_key(edge))
                        links.remove(edge)
                address_row = next(r for r in self.rows[FILES[2]] if r["address_id"] == row["address_id"])
                edge = {"type": "REGISTERED_AT", "source": key, "target": row["address_id"], "evidence": [row["source_record_id"], address_row["source_record_id"]]}
                added.append(edge)
                links.append(edge)
            applied.add(update_batch)
            return "applied"

        self.assertEqual(apply_update_once(), "applied")
        self.assertEqual(history, spec["changes"])
        self.assertEqual(len(history), spec["logical_change_event_count"])
        self.assertEqual(retired, spec["retired_relationships"])
        self.assertEqual(added, spec["added_relationships"])
        self.assertEqual(sorted(map(edge_key, links)), sorted(spec["active_relationship_keys"]))
        self.assertEqual(len(links), spec["counts"]["active_relationship_count"])
        self.assertEqual(sum(map(len, entities.values())), spec["counts"]["canonical_entity_count"])
        self.assertEqual(pair_scores(entities["Company"], links), spec["pair_scores"])
        changed = {r["company_id"] for r in rows}
        for kind, records in original_entities.items():
            for key, value in records.items():
                if kind != "Company" or key not in changed:
                    self.assertEqual(entities[kind][key], value)
        self.assertEqual([e for e in links if e["type"] == "DIRECTED"], [e for e in original_links if e["type"] == "DIRECTED"])
        snapshot = copy.deepcopy((entities, links, history))
        self.assertEqual(apply_update_once(), self.expected["replay"]["outcome"])
        self.assertIn(initial_batch, applied)  # old batch remains applied, never reverts update
        self.assertEqual((entities, links, history), snapshot)
        for scenario in ("same_initial_before_update", "same_update_after_update", "same_initial_after_update"):
            for key, value in self.expected["replay"][scenario].items():
                self.assertEqual(value, False if key == "reverts_update" else 0)
        self.assertEqual(len(history), self.expected["replay"]["logical_change_events_after_update"])
        self.assertEqual(len(links), self.expected["replay"]["active_relationship_count"])
        self.assertEqual(sum(map(len, entities.values())), self.expected["replay"]["canonical_entity_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
