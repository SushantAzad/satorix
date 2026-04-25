import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from semantic.properties.indian_types import (
    CIN_Type, DIN_Type, GST_Type, Currency_INR, IndianDate_Type, RiskScore_Type, normalize_state
)


class TestCINType:
    def test_valid_cin(self):
        cin = CIN_Type.validate("L45201MH2003PLC142301")
        assert str(cin) == "L45201MH2003PLC142301"

    def test_normalizes_lowercase(self):
        cin = CIN_Type.validate("l45201mh2003plc142301")
        assert str(cin) == "L45201MH2003PLC142301"

    def test_strips_whitespace(self):
        cin = CIN_Type.validate("  L45201MH2003PLC142301  ")
        assert str(cin) == "L45201MH2003PLC142301"

    def test_invalid_cin_raises(self):
        with pytest.raises(ValueError):
            CIN_Type.validate("INVALID123")

    def test_extract_components(self):
        cin = CIN_Type.validate("L45201MH2003PLC142301")
        comps = cin.extract_components()
        assert comps["listing_status"] == "L"
        assert comps["state_code"] == "MH"
        assert comps["year"] == "2003"
        assert comps["company_type"] == "PLC"


class TestDINType:
    def test_valid_din(self):
        din = DIN_Type.validate("00112233")
        assert str(din) == "00112233"

    def test_zero_pads_short_din(self):
        din = DIN_Type.validate("112233")
        assert str(din) == "00112233"

    def test_integer_din(self):
        din = DIN_Type.validate(112233)
        assert str(din) == "00112233"

    def test_invalid_din(self):
        with pytest.raises(ValueError):
            DIN_Type.validate("ABCD1234")


class TestCurrencyINR:
    def test_valid_amount(self):
        c = Currency_INR.validate(1000000)
        assert float(c) == 1000000.0

    def test_to_lakhs(self):
        c = Currency_INR.validate(5000000)
        assert c.to_lakhs() == 50.0

    def test_to_crores(self):
        c = Currency_INR.validate(100000000)
        assert c.to_crores() == 10.0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            Currency_INR.validate(-100)

    def test_display_format(self):
        c = Currency_INR.validate(12345678)
        assert c.display().startswith("₹")


class TestIndianDateType:
    def test_iso_format(self):
        d = IndianDate_Type.validate("2024-02-08")
        assert d.year == 2024
        assert d.month == 2
        assert d.day == 8

    def test_dd_mm_yyyy(self):
        d = IndianDate_Type.validate("08/02/2024")
        assert d.year == 2024
        assert d.month == 2

    def test_financial_year_april(self):
        d = IndianDate_Type.validate("2024-04-01")
        assert d.financial_year() == "FY2025"

    def test_financial_year_march(self):
        d = IndianDate_Type.validate("2024-03-31")
        assert d.financial_year() == "FY2024"

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            IndianDate_Type.validate("not-a-date")


class TestRiskScoreType:
    def test_valid_scores(self):
        assert int(RiskScore_Type.validate(0)) == 0
        assert int(RiskScore_Type.validate(100)) == 100
        assert int(RiskScore_Type.validate(55)) == 55

    def test_low_band(self):
        score = RiskScore_Type.validate(30)
        assert score.get_band() == "LOW"

    def test_medium_band(self):
        score = RiskScore_Type.validate(55)
        assert score.get_band() == "MEDIUM"

    def test_high_band(self):
        score = RiskScore_Type.validate(75)
        assert score.get_band() == "HIGH"

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            RiskScore_Type.validate(101)
        with pytest.raises(ValueError):
            RiskScore_Type.validate(-1)


class TestNormalizeState:
    def test_code_to_full_name(self):
        assert normalize_state("MH") == "Maharashtra"
        assert normalize_state("GJ") == "Gujarat"
        assert normalize_state("DL") == "Delhi"

    def test_full_name_preserved(self):
        assert normalize_state("Maharashtra") == "Maharashtra"

    def test_lowercase_code(self):
        assert normalize_state("mh") == "Maharashtra"
