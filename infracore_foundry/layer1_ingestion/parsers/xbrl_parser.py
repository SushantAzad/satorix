"""XBRL financial report parser for Indian corporate filings."""

import logging
import re
from typing import Optional
from lxml import etree
import pandas as pd

logger = logging.getLogger(__name__)

XBRL_NAMESPACES = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "link": "http://www.xbrl.org/2003/linkbase",
    "in-gaap": "http://www.mca.gov.in/xbrl/taxonomy",
}


def parse_xbrl_file(file_path: str) -> pd.DataFrame:
    """Parse an XBRL file and extract all facts into a DataFrame."""
    try:
        tree = etree.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        logger.error("Failed to parse XBRL file: %s", str(e))
        return pd.DataFrame()

    nsmap = root.nsmap
    records = []

    for element in root.iter():
        tag = element.tag
        if "}" in tag:
            ns, local = tag.split("}", 1)
            ns = ns.lstrip("{")
        else:
            local = tag
            ns = ""

        if element.text and element.text.strip():
            record = {
                "concept": local,
                "namespace": ns,
                "value": element.text.strip(),
                "context_ref": element.get("contextRef", ""),
                "unit_ref": element.get("unitRef", ""),
                "decimals": element.get("decimals", ""),
            }
            records.append(record)

    df = pd.DataFrame(records) if records else pd.DataFrame()
    if not df.empty:
        # Convert numeric values
        df["numeric_value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def extract_financial_statements(xbrl_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Group XBRL facts into financial statement categories."""
    categories = {
        "balance_sheet": ["Assets", "Liabilities", "Equity", "Capital", "Reserve"],
        "income_statement": ["Revenue", "Expense", "Income", "Profit", "Loss", "EBITDA"],
        "cash_flow": ["CashFlow", "Operating", "Investing", "Financing"],
    }
    result = {}
    for cat_name, keywords in categories.items():
        mask = xbrl_df["concept"].str.contains("|".join(keywords), case=False, na=False)
        filtered = xbrl_df[mask].copy()
        if not filtered.empty:
            result[cat_name] = filtered
    return result
