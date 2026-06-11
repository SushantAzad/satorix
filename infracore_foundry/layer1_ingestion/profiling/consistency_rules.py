"""
14 Indian business data consistency rules implemented as a rule engine.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyViolation:
    rule_name: str
    affected_columns: list[str]
    violation_count: int
    sample_violations: list[dict]
    severity: str


class ConsistencyRule:
    """Base consistency rule."""

    def __init__(self, name: str, description: str, affected_columns: list[str], severity: str) -> None:
        self.name = name
        self.description = description
        self.affected_columns = affected_columns
        self.severity = severity

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        """Override in subclass. Returns violation or None."""
        raise NotImplementedError

    def _has_columns(self, df: pd.DataFrame) -> bool:
        return all(c in df.columns for c in self.affected_columns)


class PaidUpCannotExceedAuthorized(ConsistencyRule):
    def __init__(self):
        super().__init__("paid_up_cannot_exceed_authorized", "PaidUpCapital <= AuthorizedCapital", ["PaidUpCapital", "AuthorizedCapital"], "critical")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        paid = pd.to_numeric(df["PaidUpCapital"], errors="coerce")
        auth = pd.to_numeric(df["AuthorizedCapital"], errors="coerce")
        mask = paid > auth
        violations = df[mask & paid.notna() & auth.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class IncorporationDateNotFuture(ConsistencyRule):
    def __init__(self):
        super().__init__("incorporation_date_not_future", "IncorporationDate <= today", ["IncorporationDate"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        dates = pd.to_datetime(df["IncorporationDate"], errors="coerce")
        future = dates > pd.Timestamp.now()
        violations = df[future & dates.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class CessationAfterAppointment(ConsistencyRule):
    def __init__(self):
        super().__init__("cessation_after_appointment", "CessationDate > AppointmentDate", ["CessationDate", "AppointmentDate"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        cess = pd.to_datetime(df["CessationDate"], errors="coerce")
        appt = pd.to_datetime(df["AppointmentDate"], errors="coerce")
        mask = cess <= appt
        violations = df[mask & cess.notna() & appt.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class ActiveCompanyMustFile(ConsistencyRule):
    def __init__(self):
        super().__init__("active_company_must_file", "Active companies with >3 years without filing", ["Status", "YearsWithoutFiling"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        mask = (df["Status"].str.lower() == "active") & (pd.to_numeric(df["YearsWithoutFiling"], errors="coerce") > 3)
        violations = df[mask]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class CIRPCompanyFinancials(ConsistencyRule):
    def __init__(self):
        super().__init__("cirp_company_financials", "UnderCIRP companies: flag financials as unverified", ["Status"], "info")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if "Status" not in df.columns: return None
        cirp = df[df["Status"].str.lower().str.contains("cirp", na=False)]
        if cirp.empty: return None
        return ConsistencyViolation(self.name, ["Status"], len(cirp), cirp.head(5).to_dict("records"), self.severity)


class DirectorLimit(ConsistencyRule):
    def __init__(self):
        super().__init__("director_limit", "CurrentDirectorships <= 20", ["CurrentDirectorships"], "critical")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        count = pd.to_numeric(df["CurrentDirectorships"], errors="coerce")
        violations = df[count > 20]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class PaidCapitalPositive(ConsistencyRule):
    def __init__(self):
        super().__init__("paid_capital_positive", "PaidUpCapital > 0 for Active", ["PaidUpCapital", "Status"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        paid = pd.to_numeric(df["PaidUpCapital"], errors="coerce")
        mask = (df["Status"].str.lower() == "active") & (paid <= 0) & paid.notna()
        violations = df[mask]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class GSTINStateMatchesAddress(ConsistencyRule):
    def __init__(self):
        super().__init__("gstin_state_matches_address", "GSTIN state code matches registered address state", ["GSTIN", "StateCode"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        gstin_state = df["GSTIN"].astype(str).str[:2]
        addr_state = df["StateCode"].astype(str)
        mask = (gstin_state != addr_state) & (gstin_state != "na") & (addr_state != "na")
        violations = df[mask]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class ActualCostReasonable(ConsistencyRule):
    def __init__(self):
        super().__init__("actual_cost_reasonable", "ActualCost <= BudgetCost * 3.0", ["ActualCost", "BudgetCost"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        actual = pd.to_numeric(df["ActualCost"], errors="coerce")
        budget = pd.to_numeric(df["BudgetCost"], errors="coerce")
        mask = actual > budget * 3.0
        violations = df[mask & actual.notna() & budget.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class CompletionDateLogic(ConsistencyRule):
    def __init__(self):
        super().__init__("completion_date_logic", "ActualCompletionDate >= ContractDate", ["ActualCompletionDate", "ContractDate"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        comp = pd.to_datetime(df["ActualCompletionDate"], errors="coerce")
        cont = pd.to_datetime(df["ContractDate"], errors="coerce")
        mask = comp < cont
        violations = df[mask & comp.notna() & cont.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class DebtEquityEqualsCost(ConsistencyRule):
    def __init__(self):
        super().__init__("debt_plus_equity_equals_cost", "|Debt + Equity - TotalCost| < 5% TotalCost", ["DebtComponent", "EquityComponent", "TotalCost"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        debt = pd.to_numeric(df["DebtComponent"], errors="coerce")
        equity = pd.to_numeric(df["EquityComponent"], errors="coerce")
        total = pd.to_numeric(df["TotalCost"], errors="coerce")
        diff = (debt + equity - total).abs()
        mask = diff > total * 0.05
        violations = df[mask & debt.notna() & equity.notna() & total.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class CurrentRatioMinimum(ConsistencyRule):
    def __init__(self):
        super().__init__("current_ratio_minimum", "CurrentRatio > 0", ["CurrentRatio"], "critical")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        ratio = pd.to_numeric(df["CurrentRatio"], errors="coerce")
        violations = df[(ratio <= 0) & ratio.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class RevenueConsistency(ConsistencyRule):
    def __init__(self):
        super().__init__("revenue_consistency", "Revenue > 0 for operational projects", ["Revenue", "Status"], "warning")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        rev = pd.to_numeric(df["Revenue"], errors="coerce")
        mask = (df["Status"].str.lower().str.contains("operational", na=False)) & ((rev <= 0) | rev.isna())
        violations = df[mask]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


class DebtServiceFeasibility(ConsistencyRule):
    def __init__(self):
        super().__init__("debt_service_feasibility", "DSCR >= 0.8", ["EBITDA", "AnnualDebtService"], "critical")

    def check(self, df: pd.DataFrame) -> Optional[ConsistencyViolation]:
        if not self._has_columns(df): return None
        ebitda = pd.to_numeric(df["EBITDA"], errors="coerce")
        debt_svc = pd.to_numeric(df["AnnualDebtService"], errors="coerce")
        mask = ebitda < debt_svc * 0.8
        violations = df[mask & ebitda.notna() & debt_svc.notna()]
        if violations.empty: return None
        return ConsistencyViolation(self.name, self.affected_columns, len(violations), violations.head(5).to_dict("records"), self.severity)


# All rules registry
ALL_RULES: list[ConsistencyRule] = [
    PaidUpCannotExceedAuthorized(),
    IncorporationDateNotFuture(),
    CessationAfterAppointment(),
    ActiveCompanyMustFile(),
    CIRPCompanyFinancials(),
    DirectorLimit(),
    PaidCapitalPositive(),
    GSTINStateMatchesAddress(),
    ActualCostReasonable(),
    CompletionDateLogic(),
    DebtEquityEqualsCost(),
    CurrentRatioMinimum(),
    RevenueConsistency(),
    DebtServiceFeasibility(),
]


def run_all_rules(df: pd.DataFrame) -> list[ConsistencyViolation]:
    """Run all consistency rules and return violations."""
    violations = []
    for rule in ALL_RULES:
        try:
            result = rule.check(df)
            if result is not None:
                violations.append(result)
                logger.info("Rule '%s' found %d violations", rule.name, result.violation_count)
        except Exception as e:
            logger.warning("Rule '%s' failed: %s", rule.name, str(e))
    return violations
