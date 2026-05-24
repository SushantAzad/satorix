from pydantic import field_validator, model_validator
from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase


class FinancialStatement(OntologyObjectBase):
    """Annual or quarterly financial statement for a Company."""

    # Primary key — composed as "{cin}_{financial_year}_{period}"
    statement_id: str

    # Parent company
    cin: str
    company_name: Optional[str] = None

    # Period
    financial_year: str           # e.g. "FY2024"
    period: str = "annual"        # annual | q1 | q2 | q3 | q4
    filing_date: Optional[datetime] = None

    # P&L (in INR Cr)
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    ebitda_margin_pct: Optional[float] = None   # derived
    pat: Optional[float] = None                  # profit after tax
    depreciation: Optional[float] = None

    # Balance sheet (in INR Cr)
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    cash_and_equivalents: Optional[float] = None

    # Ratios (derived or provided)
    debt_equity_ratio: Optional[float] = None
    current_ratio: Optional[float] = None
    debt_service_coverage: Optional[float] = None   # EBITDA / total debt service
    working_capital: Optional[float] = None          # current_assets - current_liabilities

    # Operational
    related_party_tx_value: Optional[float] = None   # related-party transactions in INR Cr
    capex: Optional[float] = None

    # Source
    source: Optional[str] = None   # MCA21 | annual_report | manual

    def primary_key_value(self) -> str:
        return self.statement_id

    def compute_data_quality_score(self) -> float:
        critical = ["statement_id", "cin", "financial_year", "revenue", "total_debt"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    @model_validator(mode="after")
    def derive_ratios(self) -> "FinancialStatement":
        if self.ebitda is not None and self.revenue and self.revenue > 0:
            self.ebitda_margin_pct = round(self.ebitda / self.revenue * 100, 2)
        if self.current_assets is not None and self.current_liabilities is not None:
            self.working_capital = self.current_assets - self.current_liabilities
        if self.current_assets is not None and self.current_liabilities and self.current_liabilities > 0:
            self.current_ratio = round(self.current_assets / self.current_liabilities, 3)
        if self.total_debt is not None and self.equity and self.equity > 0:
            self.debt_equity_ratio = round(self.total_debt / self.equity, 3)
        return self

    class OntologyMeta:
        api_name = "financial_statement"
        display_name = "Financial Statement"
        plural_name = "Financial Statements"
        description = "Annual or quarterly financial statement for an Indian company"
        primary_key_field = "statement_id"
        critical_properties = ["statement_id", "cin", "financial_year", "revenue", "total_debt"]


FINANCIAL_STATEMENT_DEFINITION = {
    "api_name": "financial_statement",
    "display_name": "Financial Statement",
    "plural_name": "Financial Statements",
    "description": "Annual or quarterly P&L and balance sheet data for a company",
    "primary_key_field": "statement_id",
    "properties": {
        "statement_id":          {"type": "str", "required": True, "immutable": True},
        "cin":                   {"type": "str", "required": True},
        "company_name":          {"type": "str"},
        "financial_year":        {"type": "str", "required": True},
        "period":                {"type": "str"},
        "filing_date":           {"type": "datetime"},
        "revenue":               {"type": "float"},
        "ebitda":                {"type": "float"},
        "ebitda_margin_pct":     {"type": "float", "derived": True},
        "pat":                   {"type": "float"},
        "depreciation":          {"type": "float"},
        "total_assets":          {"type": "float"},
        "total_debt":            {"type": "float"},
        "equity":                {"type": "float"},
        "current_assets":        {"type": "float"},
        "current_liabilities":   {"type": "float"},
        "cash_and_equivalents":  {"type": "float"},
        "debt_equity_ratio":     {"type": "float", "derived": True},
        "current_ratio":         {"type": "float", "derived": True},
        "debt_service_coverage": {"type": "float"},
        "working_capital":       {"type": "float", "derived": True},
        "related_party_tx_value":{"type": "float"},
        "capex":                 {"type": "float"},
        "source":                {"type": "str"},
    },
    "interfaces": ["FinancialEntity", "TemporalEntity"],
}
