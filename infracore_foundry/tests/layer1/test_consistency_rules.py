"""Tests for the consistency rules engine."""

import pytest
import pandas as pd

from layer1_ingestion.profiling.consistency_rules import (
    PaidUpCannotExceedAuthorized,
    IncorporationDateNotFuture,
    DirectorLimit,
    run_all_rules,
)


class TestPaidUpCannotExceedAuthorized:
    def test_valid_data(self):
        df = pd.DataFrame({"PaidUpCapital": [500], "AuthorizedCapital": [1000]})
        result = PaidUpCannotExceedAuthorized().check(df)
        assert result is None

    def test_violation(self):
        df = pd.DataFrame({"PaidUpCapital": [1500], "AuthorizedCapital": [1000]})
        result = PaidUpCannotExceedAuthorized().check(df)
        assert result is not None
        assert result.violation_count == 1

    def test_missing_columns(self):
        df = pd.DataFrame({"Name": ["Test"]})
        result = PaidUpCannotExceedAuthorized().check(df)
        assert result is None


class TestIncorporationDateNotFuture:
    def test_valid_date(self):
        df = pd.DataFrame({"IncorporationDate": ["2020-01-01"]})
        result = IncorporationDateNotFuture().check(df)
        assert result is None

    def test_future_date(self):
        df = pd.DataFrame({"IncorporationDate": ["2099-12-31"]})
        result = IncorporationDateNotFuture().check(df)
        assert result is not None


class TestDirectorLimit:
    def test_valid(self):
        df = pd.DataFrame({"CurrentDirectorships": [15]})
        result = DirectorLimit().check(df)
        assert result is None

    def test_violation(self):
        df = pd.DataFrame({"CurrentDirectorships": [25]})
        result = DirectorLimit().check(df)
        assert result is not None


class TestRunAllRules:
    def test_no_violations(self, sample_company_df):
        violations = run_all_rules(sample_company_df)
        capital_violations = [v for v in violations if v.rule_name == "paid_up_cannot_exceed_authorized"]
        assert len(capital_violations) == 0
