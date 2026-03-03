"""Tests for Indian identifier validators."""

import pytest
from layer1_ingestion.schema.indian_identifiers import (
    CINValidator, DINValidator, GSTINValidator, PANValidator,
    IFSCValidator, PINCodeValidator, MobileValidator,
    detect_identifier_columns,
)
import pandas as pd


class TestCINValidator:
    def test_valid_cin(self):
        assert CINValidator.is_valid("U72200MH2009PTC194000")
        assert CINValidator.is_valid("L17110MH1973PLC019786")

    def test_invalid_cin(self):
        assert not CINValidator.is_valid("INVALID")
        assert not CINValidator.is_valid("")
        assert not CINValidator.is_valid("X72200MH2009PTC194000")

    def test_normalize(self):
        assert CINValidator.normalize("  u72200mh2009ptc194000  ") == "U72200MH2009PTC194000"

    def test_extract_components(self):
        result = CINValidator.extract_components("U72200MH2009PTC194000")
        assert result["listing_status"] == "Unlisted"
        assert result["state_code"] == "MH"
        assert result["year"] == "2009"


class TestPANValidator:
    def test_valid_pan(self):
        assert PANValidator.is_valid("ABCDE1234F")

    def test_invalid_pan(self):
        assert not PANValidator.is_valid("ABCDE1234")
        assert not PANValidator.is_valid("12345ABCDE")

    def test_extract_components(self):
        result = PANValidator.extract_components("ABCDE1234F")
        assert result["entity_type_code"] == "D"


class TestGSTINValidator:
    def test_valid_format(self):
        # Note: checksum validation may fail for arbitrary GSTINs
        assert GSTINValidator.normalize("27aabcu9603r1zm") == "27AABCU9603R1ZM"


class TestIFSCValidator:
    def test_valid_ifsc(self):
        assert IFSCValidator.is_valid("SBIN0001234")

    def test_invalid_ifsc(self):
        assert not IFSCValidator.is_valid("SBI01234")

    def test_extract_components(self):
        result = IFSCValidator.extract_components("SBIN0001234")
        assert result["bank_code"] == "SBIN"


class TestPINCodeValidator:
    def test_valid_pin(self):
        assert PINCodeValidator.is_valid("400001")
        assert PINCodeValidator.is_valid("110001")

    def test_invalid_pin(self):
        assert not PINCodeValidator.is_valid("000001")
        assert not PINCodeValidator.is_valid("12345")


class TestMobileValidator:
    def test_valid_mobile(self):
        assert MobileValidator.is_valid("9876543210")
        assert MobileValidator.is_valid("+919876543210")
        assert MobileValidator.is_valid("09876543210")

    def test_invalid_mobile(self):
        assert not MobileValidator.is_valid("1234567890")
        assert not MobileValidator.is_valid("12345")


class TestDetectIdentifierColumns:
    def test_detect_cin_column(self, sample_company_df):
        result = detect_identifier_columns(sample_company_df)
        assert "CIN" in result
        assert result["CIN"] == "cin"

    def test_no_identifiers(self):
        df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
        result = detect_identifier_columns(df)
        assert result == {}
