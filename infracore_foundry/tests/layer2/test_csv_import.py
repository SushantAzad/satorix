import unittest
from shared.csv_import import parse_csv


class CsvImportTests(unittest.TestCase):
    def test_mapping_bom_and_quoted_comma(self):
        result = parse_csv("company", '\ufeffCode,Company\nACME-1,"Example, Limited"\n',
                           {"id": "Code", "name": "Company"})
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rows"][0]["data"]["name"], "Example, Limited")

    def test_duplicate_ids_and_missing_name(self):
        result = parse_csv("company", "id,name\nA,First\nA,\n", {"id": "id", "name": "name"})
        self.assertEqual(len(result["errors"]), 2)

    def test_missing_mapping_and_duplicate_headers(self):
        for content, mapping in [("id,name\nA,First", {"id": "id"}),
                                 ("id,id\nA,A", {"id": "id", "name": "id"})]:
            with self.assertRaises(ValueError):
                parse_csv("company", content, mapping)

    def test_invalid_date_and_path_id(self):
        result = parse_csv("directorship", "d,c,date\n../bad,C1,2026-02-30",
                           {"director_id": "d", "company_id": "c", "appointed_date": "date"})
        self.assertEqual(len(result["errors"]), 2)

    def test_size_and_row_bounds(self):
        for content in ["id,name\n" + "x" * 256001, "id,name\n" + "A,Name\n" * 201]:
            with self.assertRaises(ValueError):
                parse_csv("company", content, {"id": "id", "name": "name"})

    def test_wrong_column_count(self):
        result = parse_csv("company", "id,name\nA,Name,extra", {"id": "id", "name": "name"})
        self.assertEqual(len(result["errors"]), 1)

    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            parse_csv("company", "id,name,risk\nA,Name,99",
                      {"id": "id", "name": "name", "riskScore": "risk"})


if __name__ == "__main__":
    unittest.main()
