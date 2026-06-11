"""Tally XML response parser with version detection and DataFrame conversion."""

import logging
from lxml import etree
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)


def detect_tally_version(xml_content: str) -> str:
    if "xmlns:UDF" in xml_content or "TALLYMESSAGE xmlns" in xml_content:
        return "4.x"
    return "3.x"


def parse_tally_xml(xml_content: str, entity_filter: Optional[str] = None) -> pd.DataFrame:
    """Parse Tally XML content and return as DataFrame."""
    try:
        if isinstance(xml_content, str):
            xml_content = xml_content.encode("utf-8")
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError as e:
        logger.error("Invalid Tally XML: %s", str(e))
        return pd.DataFrame()

    records = []
    for msg in root.iter("TALLYMESSAGE"):
        for child in msg:
            if entity_filter and child.tag.upper() != entity_filter.upper():
                continue
            record = _flatten_element(child, prefix="")
            record["_entity_type"] = child.tag
            records.append(record)

    if not records:
        for child in root:
            if child.tag in ("HEADER", "BODY"):
                continue
            record = _flatten_element(child, prefix="")
            record["_entity_type"] = child.tag
            records.append(record)

    return pd.DataFrame(records) if records else pd.DataFrame()


def _flatten_element(element, prefix: str = "") -> dict:
    """Recursively flatten an XML element into a dict."""
    result = {}
    key_prefix = f"{prefix}{element.tag}." if prefix else ""

    for attr, val in element.attrib.items():
        result[f"{key_prefix}{attr}"] = val

    if element.text and element.text.strip():
        if len(element) == 0:
            result[element.tag if not prefix else f"{prefix}{element.tag}"] = element.text.strip()
        else:
            result[f"{key_prefix}_text"] = element.text.strip()

    for child in element:
        if len(child) == 0:
            child_key = f"{key_prefix}{child.tag}" if prefix else child.tag
            value = child.text.strip() if child.text else ""
            if child_key in result:
                existing = result[child_key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    result[child_key] = [existing, value]
            else:
                result[child_key] = value
        else:
            nested = _flatten_element(child, prefix=key_prefix)
            result.update(nested)

    return result


def parse_voucher_xml(xml_content: str) -> pd.DataFrame:
    """Parse Tally voucher XML into accounting entry format."""
    return parse_tally_xml(xml_content, entity_filter="VOUCHER")


def parse_ledger_xml(xml_content: str) -> pd.DataFrame:
    """Parse Tally ledger master XML."""
    return parse_tally_xml(xml_content, entity_filter="LEDGER")
