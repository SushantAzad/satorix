import re
import datetime
from typing import Annotated, Any
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

# Indian state code → full name lookup
INDIAN_STATE_CODES: dict[str, str] = {
    "AN": "Andaman and Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CH": "Chandigarh",
    "CG": "Chhattisgarh",
    "DN": "Dadra and Nagar Haveli and Daman and Diu",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "HP": "Himachal Pradesh",
    "JK": "Jammu and Kashmir",
    "JH": "Jharkhand",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MP": "Madhya Pradesh",
    "MH": "Maharashtra",
    "MN": "Manipur",
    "ML": "Meghalaya",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OR": "Odisha",
    "PY": "Puducherry",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TS": "Telangana",
    "TR": "Tripura",
    "UP": "Uttar Pradesh",
    "UT": "Uttarakhand",
    "WB": "West Bengal",
}

# GST state codes (2-digit numbers)
GST_STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh",
}

CIN_PATTERN = re.compile(r'^[UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$')
DIN_PATTERN = re.compile(r'^[0-9]{8}$')
GST_PATTERN = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')

INDIAN_DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y",
    "%d %B %Y", "%B %d, %Y", "%d-%b-%y", "%d %b %Y",
    "%d/%m/%y",
]


class CIN_Type(str):
    """Corporate Identity Number — 21-character Indian company identifier."""

    @classmethod
    def validate(cls, value: Any) -> "CIN_Type":
        if not isinstance(value, str):
            raise ValueError(f"CIN must be a string, got {type(value)}")
        normalized = value.strip().upper()
        if not CIN_PATTERN.match(normalized):
            raise ValueError(f"Invalid CIN format: {value!r}")
        return cls(normalized)

    def extract_components(self) -> dict[str, str]:
        return {
            "listing_status": self[0],          # U=Unlisted, L=Listed
            "nic_code": self[1:6],              # 5-digit NIC code
            "state_code": self[6:8],            # 2-letter state code
            "year": self[8:12],                 # 4-digit year
            "company_type": self[12:15],        # PLC, PTC, etc.
            "seq_number": self[15:21],          # 6-digit sequence
        }

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class DIN_Type(str):
    """Director Identification Number — 8-digit Indian director identifier."""

    @classmethod
    def validate(cls, value: Any) -> "DIN_Type":
        if not isinstance(value, (str, int)):
            raise ValueError(f"DIN must be string or int, got {type(value)}")
        normalized = str(value).strip().zfill(8)
        if not DIN_PATTERN.match(normalized):
            raise ValueError(f"Invalid DIN format: {value!r}")
        return cls(normalized)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class GST_Type(str):
    """Goods and Services Tax Identification Number — 15-character identifier."""

    @classmethod
    def validate(cls, value: Any) -> "GST_Type":
        if not isinstance(value, str):
            raise ValueError(f"GST must be a string, got {type(value)}")
        normalized = value.strip().upper()
        if not GST_PATTERN.match(normalized):
            raise ValueError(f"Invalid GST format: {value!r}")
        return cls(normalized)

    def get_state_name(self) -> str:
        state_code = self[:2]
        return GST_STATE_CODES.get(state_code, "Unknown")

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class Currency_INR(float):
    """Indian Rupee monetary value — always stored as float in rupees."""

    @classmethod
    def validate(cls, value: Any) -> "Currency_INR":
        try:
            amount = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Currency_INR must be numeric, got {value!r}")
        if amount < 0:
            raise ValueError(f"Currency_INR cannot be negative: {amount}")
        return cls(amount)

    def to_lakhs(self) -> float:
        return self / 100_000

    def to_crores(self) -> float:
        return self / 10_000_000

    def display(self) -> str:
        """Format in Indian lakh notation: ₹X,XX,XXX"""
        amount = int(self)
        if amount == 0:
            return "₹0"
        s = str(amount)
        if len(s) <= 3:
            return f"₹{s}"
        result = s[-3:]
        s = s[:-3]
        while len(s) > 2:
            result = s[-2:] + "," + result
            s = s[:-2]
        if s:
            result = s + "," + result
        return f"₹{result}"

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.float_ser_schema(),
        )


class IndianDate_Type(datetime.date):
    """Indian date — parses multiple formats, stores as ISO 8601."""

    @classmethod
    def validate(cls, value: Any) -> "IndianDate_Type":
        if isinstance(value, cls):
            return value
        if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
            return cls(value.year, value.month, value.day)
        if isinstance(value, datetime.datetime):
            return cls(value.year, value.month, value.day)
        if not isinstance(value, str):
            raise ValueError(f"IndianDate_Type requires string or date, got {type(value)}")
        value = value.strip()
        for fmt in INDIAN_DATE_FORMATS:
            try:
                parsed = datetime.datetime.strptime(value, fmt)
                return cls(parsed.year, parsed.month, parsed.day)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: {value!r}. Supported formats: DD/MM/YYYY, YYYY-MM-DD, etc.")

    def financial_year(self) -> str:
        if self.month >= 4:
            return f"FY{self.year + 1}"
        return f"FY{self.year}"

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class RiskScore_Type(int):
    """Risk score 0–100. 0–39 = LOW (green), 40–69 = MEDIUM (orange), 70–100 = HIGH (red)."""

    @classmethod
    def validate(cls, value: Any) -> "RiskScore_Type":
        try:
            score = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"RiskScore must be integer, got {value!r}")
        if not (0 <= score <= 100):
            raise ValueError(f"RiskScore must be 0–100, got {score}")
        return cls(score)

    def get_band(self) -> str:
        if self <= 39:
            return "LOW"
        if self <= 69:
            return "MEDIUM"
        return "HIGH"

    def get_color(self) -> str:
        band = self.get_band()
        return {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}[band]

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.int_ser_schema(),
        )


def normalize_state(value: str) -> str:
    """Normalize state code or abbreviation to full name."""
    if not value:
        return value
    upper = value.strip().upper()
    if upper in INDIAN_STATE_CODES:
        return INDIAN_STATE_CODES[upper]
    # Check if it's already a full name (case-insensitive match)
    for full_name in INDIAN_STATE_CODES.values():
        if full_name.upper() == upper:
            return full_name
    return value.strip().title()
