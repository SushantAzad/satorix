"""PDF table extraction and reconstruction utilities."""

import logging
import re
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)


def extract_tables_from_pdf(file_path: str, pages: Optional[list[int]] = None) -> list[pd.DataFrame]:
    """Extract all tables from a PDF using pdfplumber."""
    import pdfplumber
    results = []
    with pdfplumber.open(file_path) as pdf:
        target = pages if pages else range(len(pdf.pages))
        for idx in target:
            if idx >= len(pdf.pages):
                continue
            page = pdf.pages[idx]
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                headers = [str(h).strip() if h else f"Col_{i}" for i, h in enumerate(table[0])]
                data = [[str(c).strip() if c else None for c in row] for row in table[1:]]
                for row in data:
                    while len(row) < len(headers):
                        row.append(None)
                df = pd.DataFrame(data, columns=headers)
                df = df.dropna(how="all").reset_index(drop=True)
                if not df.empty:
                    df["_page"] = idx + 1
                    results.append(df)
    return results


def reconstruct_table_from_text(text: str) -> Optional[pd.DataFrame]:
    """Attempt table reconstruction from OCR text using whitespace analysis."""
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return None
    rows = [re.split(r"\s{2,}", line.strip()) for line in lines]
    max_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append(None)
    headers = [h or f"Col_{i}" for i, h in enumerate(rows[0])]
    df = pd.DataFrame(rows[1:], columns=headers[:max_cols])
    return df.dropna(how="all").reset_index(drop=True)
