import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ingestion.object_mapper import ObjectMapper


class TestObjectMapper:
    def setup_method(self):
        self.mapper = ObjectMapper()

    def test_map_company_master(self):
        df = pd.DataFrame([{
            "CIN": "L45201MH2003PLC142301",
            "CompanyName": "Infracore Developments Limited",
            "Status": "Active",
            "RegisteredState": "MH",
            "CompanyType": "Public Limited",
        }])
        records = self.mapper.map_dataframe("company_master", df)
        assert len(records) == 1
        assert records[0]["cin"] == "L45201MH2003PLC142301"
        assert records[0]["name"] == "Infracore Developments Limited"
        assert records[0]["registeredState"] == "Maharashtra"

    def test_map_directors(self):
        df = pd.DataFrame([{
            "DIN": "112233",
            "DirectorName": "Arvind Kapoor",
            "Nationality": "Indian",
        }])
        records = self.mapper.map_dataframe("directors", df)
        assert len(records) == 1
        assert records[0]["din"] == "00112233"
        assert records[0]["name"] == "Arvind Kapoor"

    def test_skips_rows_missing_pk(self):
        df = pd.DataFrame([{"CompanyName": "No CIN Company"}])
        records = self.mapper.map_dataframe("company_master", df)
        assert len(records) == 0

    def test_unknown_source_returns_empty(self):
        df = pd.DataFrame([{"col": "val"}])
        records = self.mapper.map_dataframe("unknown_source_xyz", df)
        assert records == []

    def test_coerce_currency(self):
        df = pd.DataFrame([{
            "CIN": "L45201MH2003PLC142301",
            "CompanyName": "Test Co",
            "AuthorizedCapital": "500000000",
        }])
        records = self.mapper.map_dataframe("company_master", df)
        assert records[0]["authorizedCapital"] == 500000000.0

    def test_coerce_date_indian_format(self):
        df = pd.DataFrame([{
            "CIN": "L45201MH2003PLC142301",
            "CompanyName": "Test Co",
            "IncorporationDate": "15/01/2003",
        }])
        records = self.mapper.map_dataframe("company_master", df)
        assert "incorporationDate" in records[0]
        assert records[0]["incorporationDate"].startswith("2003")
