"""
Tally connector: Live TallyPrime XML server and offline XML export parser.
Supports TallyPrime 3.x and 4.x with version auto-detection.
"""

import io
import logging
import time
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd
from lxml import etree

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig, ConnectionError, ExtractionError,
)

logger = logging.getLogger(__name__)

TALLY_REQUESTS = {
    "company_list": """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>List of Companies</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES></DESC></BODY></ENVELOPE>""",
    "ledger_masters": """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>List of Ledgers</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES></DESC></BODY></ENVELOPE>""",
    "stock_items": """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>List of Stock Items</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES></DESC></BODY></ENVELOPE>""",
    "group_summary": """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>List of Groups</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES></DESC></BODY></ENVELOPE>""",
}

VOUCHER_REQUEST_TEMPLATE = """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>Day Book</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT><SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY><SVFROMDATE>{from_date}</SVFROMDATE><SVTODATE>{to_date}</SVTODATE></STATICVARIABLES></DESC></BODY></ENVELOPE>"""


def _detect_tally_version(xml_text: str) -> str:
    """Detect Tally version from XML response structure."""
    if "TALLYMESSAGE" in xml_text and "xmlns:UDF" in xml_text:
        return "4.x"
    return "3.x"


def _parse_xml_to_records(xml_text: str, entity_type: str) -> list[dict]:
    """Parse Tally XML response into list of dicts."""
    try:
        root = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except etree.XMLSyntaxError:
        logger.warning("Failed to parse Tally XML response")
        return []

    version = _detect_tally_version(xml_text)
    records = []

    # Find records based on entity type
    tag_mapping_3x = {
        "company": ".//COMPANY", "ledger": ".//LEDGER",
        "voucher": ".//VOUCHER", "stock_item": ".//STOCKITEM",
        "group": ".//GROUP",
    }
    tag_mapping_4x = {
        "company": ".//COMPANY", "ledger": ".//LEDGER",
        "voucher": ".//VOUCHER", "stock_item": ".//STOCKITEM",
        "group": ".//GROUP",
    }
    mapping = tag_mapping_4x if version == "4.x" else tag_mapping_3x
    tag = mapping.get(entity_type, f".//{entity_type.upper()}")

    for element in root.iter():
        if element.tag in [t.split("//")[-1] for t in mapping.values()]:
            if element.tag.lower() != entity_type.replace("_", ""):
                continue
            record = _element_to_dict(element)
            record["_tally_version"] = version
            records.append(record)

    # Fallback: extract all TALLYMESSAGE children
    if not records:
        for msg in root.findall(".//TALLYMESSAGE"):
            for child in msg:
                record = _element_to_dict(child)
                record["_entity_type"] = child.tag
                record["_tally_version"] = version
                records.append(record)

    return records


def _element_to_dict(element) -> dict:
    """Convert an XML element and its children to a flat dict."""
    result = {}
    if element.text and element.text.strip():
        result[element.tag] = element.text.strip()
    for attr_name, attr_value in element.attrib.items():
        result[f"{element.tag}_{attr_name}"] = attr_value
    for child in element:
        if len(child) == 0:
            key = child.tag
            value = child.text.strip() if child.text else ""
            if key in result:
                if isinstance(result[key], list):
                    result[key].append(value)
                else:
                    result[key] = [result[key], value]
            else:
                result[key] = value
        else:
            nested = _element_to_dict(child)
            for k, v in nested.items():
                result[f"{child.tag}.{k}"] = v
    return result


class TallyConnector(BaseConnector):
    """Tally connector for live XML server and offline XML export."""

    REQUIRED_CONFIG_FIELDS = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.mode: str = config.get("mode", "live")  # live, offline
        self.host: str = config.get("host", "localhost")
        self.port: int = config.get("port", 9000)
        self.company_name: str = config.get("company_name", "")
        self.xml_file_path: Optional[str] = config.get("xml_file_path")
        self.entity_types: list[str] = config.get(
            "entity_types", ["ledger_masters", "stock_items", "group_summary"]
        )

    def _tally_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _send_xml_request(self, xml_body: str) -> str:
        """Send XML request to TallyPrime server."""
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    self._tally_url(),
                    content=xml_body,
                    headers={"Content-Type": "text/xml"},
                )
                resp.raise_for_status()
                return resp.text
        except httpx.ConnectError as e:
            raise ConnectionError(self.source_id, f"Cannot reach Tally at {self._tally_url()}: {e}")
        except Exception as e:
            raise ExtractionError(self.source_id, f"Tally request failed: {e}") from e

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            if self.mode == "offline":
                import os
                if self.xml_file_path and os.path.exists(self.xml_file_path):
                    elapsed = (time.perf_counter() - start) * 1000
                    return ConnectionTestResult(
                        success=True, message=f"XML file found: {self.xml_file_path}",
                        response_time_ms=elapsed,
                    )
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=False, message="XML file not found",
                    response_time_ms=elapsed, error="FileNotFoundError",
                )
            xml_resp = self._send_xml_request(TALLY_REQUESTS["company_list"])
            elapsed = (time.perf_counter() - start) * 1000
            version = _detect_tally_version(xml_resp)
            return ConnectionTestResult(
                success=True,
                message=f"Tally reachable (version {version})",
                response_time_ms=elapsed,
                schema_detected={"tally_version": version},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(e),
                response_time_ms=elapsed, error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        columns = [
            {"name": "NAME", "type": "string", "nullable": False, "sample_values": []},
            {"name": "PARENT", "type": "string", "nullable": True, "sample_values": []},
            {"name": "OPENINGBALANCE", "type": "string", "nullable": True, "sample_values": []},
            {"name": "CLOSINGBALANCE", "type": "string", "nullable": True, "sample_values": []},
            {"name": "_entity_type", "type": "string", "nullable": False, "sample_values": ["LEDGER"]},
            {"name": "_tally_version", "type": "string", "nullable": False, "sample_values": ["4.x"]},
        ]
        return SchemaDetectionResult(columns=columns, total_columns=len(columns))

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_records = []
            if self.mode == "offline":
                all_records = self._extract_offline()
            else:
                for entity_type in self.entity_types:
                    xml_body = TALLY_REQUESTS.get(entity_type)
                    if not xml_body:
                        continue
                    xml_resp = self._send_xml_request(xml_body)
                    entity_key = entity_type.replace("_masters", "").replace("_items", "")
                    records = _parse_xml_to_records(xml_resp, entity_key)
                    all_records.extend(records)

            df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, 0)
            return df
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"Tally extraction failed: {e}") from e

    def extract_vouchers(self, from_date: str, to_date: str) -> pd.DataFrame:
        """Extract vouchers (transactions) for a date range."""
        xml_body = VOUCHER_REQUEST_TEMPLATE.format(
            company=self.company_name, from_date=from_date, to_date=to_date,
        )
        xml_resp = self._send_xml_request(xml_body)
        records = _parse_xml_to_records(xml_resp, "voucher")
        return pd.DataFrame(records) if records else pd.DataFrame()

    def _extract_offline(self) -> list[dict]:
        """Parse offline Tally XML export file."""
        import os
        if not self.xml_file_path or not os.path.exists(self.xml_file_path):
            raise ExtractionError(self.source_id, f"XML file not found: {self.xml_file_path}")
        with open(self.xml_file_path, "r", encoding="utf-8") as f:
            xml_text = f.read()
        version = _detect_tally_version(xml_text)
        all_records = []
        for entity_type in ["ledger", "voucher", "stock_item", "group", "company"]:
            records = _parse_xml_to_records(xml_text, entity_type)
            all_records.extend(records)
        return all_records

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """For live mode, extract vouchers since last sync date."""
        if self.mode == "live" and config.last_extracted_at:
            from_date = config.last_extracted_at.strftime("%d-%b-%Y")
            to_date = datetime.now().strftime("%d-%b-%Y")
            return self.extract_vouchers(from_date, to_date)
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return 0
