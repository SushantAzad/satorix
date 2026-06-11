import pandas as pd
from typing import Any, Optional
import logging
from semantic.properties.indian_types import (
    CIN_Type, DIN_Type, Currency_INR, IndianDate_Type, RiskScore_Type, normalize_state
)

logger = logging.getLogger(__name__)

SOURCE_COLUMN_MAPPINGS: dict[str, dict] = {
    "company_master": {
        "object_type": "company",
        "primary_key_field": "cin",
        "columns": {
            "CIN": "cin",
            "CompanyName": "name",
            "IncorporationDate": "incorporationDate",
            "RegisteredState": "registeredState",
            "CompanyType": "companyType",
            "Industry": "industry",
            "AuthorizedCapital": "authorizedCapital",
            "PaidUpCapital": "paidUpCapital",
            "Status": "status",
            "ListedStatus": "listedStatus",
            "RegisteredAddress": "registeredAddress",
            "PIN": "pin",
        },
    },
    "directors": {
        "object_type": "director",
        "primary_key_field": "din",
        "columns": {
            "DIN": "din",
            "DirectorName": "name",
            "Nationality": "nationality",
            "City": "city",
            "DisqualificationStatus": "disqualificationStatus",
            "CurrentDirectorships": "currentDirectorships",
            "HistoricalDirectorships": "historicalDirectorships",
        },
    },
    "projects": {
        "object_type": "project",
        "primary_key_field": "projectId",
        "columns": {
            "ProjectID": "projectId",
            "ProjectName": "name",
            "ProjectType": "projectType",
            "State": "state",
            "ContractedBy": "contractedBy",
            "ContractDate": "contractDate",
            "ExpectedCompletion": "expectedCompletionDate",
            "ActualCompletion": "actualCompletionDate",
            "Status": "status",
            "TotalCost": "totalCost",
            "DebtComponent": "debtComponent",
            "EquityComponent": "equityComponent",
            "ConcessionYears": "concessionYears",
            "RevenueModel": "revenueModel",
            "CurrentRevenue": "currentAnnualRevenue",
            "DelayMonths": "delayMonths",
            "CostOverrun": "costOverrunPercent",
            "EnvironmentalClearance": "environmentalClearance",
            "LandAcquisition": "landAcquisitionStatus",
            "KeyRisk": "keyRisk",
        },
    },
    "regulatory_actions": {
        "object_type": "regulatory_action",
        "primary_key_field": "actionId",
        "columns": {
            "ActionID": "actionId",
            "IssuingBody": "issuingBody",
            "ActionType": "actionType",
            "ActionDate": "actionDate",
            "ResolutionDate": "resolutionDate",
            "MonetaryAmount": "monetaryAmount",
            "Status": "status",
            "Description": "description",
        },
    },
    "insolvency": {
        "object_type": "insolvency_proceeding",
        "primary_key_field": "cirpId",
        "columns": {
            "CIRPId": "cirpId",
            "AdmissionDate": "admissionDate",
            "ResolutionProfessional": "resolutionProfessional",
            "TotalAdmittedClaims": "totalAdmittedClaims",
            "Status": "status",
            "ResolutionApplicant": "resolutionApplicant",
            "HaircutPercent": "haircutPercent",
        },
    },
}

# Fuzzy-match source names to mapping keys
SOURCE_NAME_ALIASES: dict[str, str] = {
    "company_master": "company_master",
    "companies": "company_master",
    "company": "company_master",
    "director": "directors",
    "director_mapping": "directors",
    "director_mappings": "directors",
    "projects": "projects",
    "project": "projects",
    "regulatory_actions": "regulatory_actions",
    "regulatory": "regulatory_actions",
    "insolvency": "insolvency",
    "cirp": "insolvency",
}


class ObjectMapper:
    def resolve_source(self, source_name: str) -> Optional[dict]:
        key = source_name.lower()
        mapping_key = SOURCE_NAME_ALIASES.get(key, key)
        return SOURCE_COLUMN_MAPPINGS.get(mapping_key)

    def map_dataframe(self, source_name: str, df: pd.DataFrame) -> list[dict[str, Any]]:
        mapping = self.resolve_source(source_name)
        if not mapping:
            logger.warning("No mapping found for source: %s", source_name)
            return []

        column_map = mapping["columns"]
        object_type = mapping["object_type"]
        records = []

        for _, row in df.iterrows():
            obj: dict[str, Any] = {"_object_type": object_type}
            for src_col, dst_field in column_map.items():
                # Accept case-insensitive column matching
                value = None
                for col in df.columns:
                    if col.lower() == src_col.lower():
                        value = row.get(col)
                        break
                if value is None:
                    continue
                # Skip NaN
                if pd.isna(value) if not isinstance(value, (list, dict)) else False:
                    continue
                coerced = self._coerce(dst_field, value, object_type)
                if coerced is not None:
                    obj[dst_field] = coerced

            if obj.get(mapping["primary_key_field"]):
                records.append(obj)

        logger.info("Mapped %d records from %s → %s", len(records), source_name, object_type)
        return records

    def _coerce(self, field: str, value: Any, object_type: str) -> Any:
        try:
            str_value = str(value).strip()
            if not str_value or str_value.lower() in ("nan", "none", "null", ""):
                return None

            if field == "cin":
                return str(CIN_Type.validate(str_value))
            if field == "din":
                return str(DIN_Type.validate(str_value))
            if field in ("authorizedCapital", "paidUpCapital", "totalCost", "debtComponent",
                         "equityComponent", "currentAnnualRevenue", "monetaryAmount", "totalAdmittedClaims"):
                return float(Currency_INR.validate(float(str_value)))
            if field in ("incorporationDate", "contractDate", "expectedCompletionDate",
                         "actualCompletionDate", "actionDate", "resolutionDate", "admissionDate"):
                d = IndianDate_Type.validate(str_value)
                return str(d)
            if field == "registeredState":
                return normalize_state(str_value)
            if field in ("currentDirectorships", "historicalDirectorships", "concessionYears", "delayMonths"):
                return int(float(str_value))
            if field in ("costOverrunPercent", "haircutPercent"):
                return float(str_value)
            return str_value
        except Exception as e:
            logger.debug("Coercion failed for field %s=%r: %s", field, value, e)
            return None


object_mapper = ObjectMapper()
