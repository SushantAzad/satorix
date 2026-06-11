"""OCR parser using Tesseract with Indian language support and post-processing."""

import io
import logging
import re
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

COMMON_OCR_FIXES = {
    r"\bRs\.?\s*": "₹",
    r"\bINR\s*": "₹",
    r"(?<=\d)O(?=\d)": "0",
    r"(?<=\d)l(?=\d)": "1",
    r"(?<=\d)I(?=\d)": "1",
    r"(?<=\d)S(?=\d)": "5",
    r"(?<=\d)B(?=\d)": "8",
}


def ocr_page_to_text(image, language: str = "eng+hin") -> str:
    """Run Tesseract OCR on an image with Indian language support."""
    import pytesseract
    try:
        text = pytesseract.image_to_string(image, lang=language)
        return _post_process_ocr(text)
    except Exception as e:
        logger.error("OCR failed: %s", str(e))
        return ""


def ocr_pdf_pages(pdf_path: str, pages: Optional[list[int]] = None, language: str = "eng+hin") -> list[str]:
    """OCR all (or selected) pages of a PDF."""
    import fitz
    from PIL import Image

    doc = fitz.open(pdf_path)
    results = []
    target = pages if pages else range(len(doc))

    for idx in target:
        if idx >= len(doc):
            continue
        page = doc[idx]
        mat = fitz.Matrix(3.0, 3.0)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = ocr_page_to_text(img, language)
        results.append(text)

    doc.close()
    return results


def _post_process_ocr(text: str) -> str:
    """Fix common OCR errors in Indian business documents."""
    for pattern, replacement in COMMON_OCR_FIXES.items():
        text = re.sub(pattern, replacement, text)
    # Fix broken lines in the middle of words
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Normalize whitespace
    text = re.sub(r" +", " ", text)
    return text.strip()


def extract_structured_data(ocr_text: str) -> dict:
    """Extract key-value pairs from OCR text (common in Indian forms)."""
    result = {}
    patterns = [
        (r"CIN\s*[:\-]?\s*([A-Z0-9]+)", "cin"),
        (r"PAN\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])", "pan"),
        (r"GST(?:IN)?\s*[:\-]?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z[A-Z\d])", "gstin"),
        (r"DIN\s*[:\-]?\s*(\d{8})", "din"),
        (r"Date\s*[:\-]?\s*(\d{2}[/\-.]\d{2}[/\-.]\d{4})", "date"),
        (r"(?:Amount|Total)\s*[:\-]?\s*₹?\s*([\d,]+(?:\.\d{2})?)", "amount"),
    ]
    for pattern, key in patterns:
        match = re.search(pattern, ocr_text, re.IGNORECASE)
        if match:
            result[key] = match.group(1)
    return result
