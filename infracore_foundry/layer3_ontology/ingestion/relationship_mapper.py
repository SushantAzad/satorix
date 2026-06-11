import pandas as pd
from typing import Any
import logging
from semantic.properties.indian_types import IndianDate_Type

logger = logging.getLogger(__name__)


class RelationshipMapper:
    """Maps Parquet rows to link instances for the Funnel."""

    def map_director_links(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Map director_mappings → DIRECTED relationships."""
        links = []
        for _, row in df.iterrows():
            din = str(row.get("DIN", row.get("din", ""))).strip().zfill(8)
            cin = str(row.get("CIN", row.get("cin", ""))).strip().upper()
            if not din or not cin or din == "00000000":
                continue

            appointed = self._parse_date(row.get("AppointedDate", row.get("appointedDate")))
            cessation = self._parse_date(row.get("CessationDate", row.get("cessationDate")))

            links.append({
                "link_type": "DIRECTED",
                "source_type": "director",
                "source_id": din,
                "target_type": "company",
                "target_id": cin,
                "properties": {
                    "appointedDate": appointed,
                    "cessationDate": cessation,
                    "designation": str(row.get("Designation", row.get("designation", "Director"))),
                    "isCurrent": cessation is None,
                    "appointingBody": str(row.get("AppointingBody", "Board")),
                },
            })
        logger.info("Mapped %d DIRECTED relationships", len(links))
        return links

    def map_ownership_links(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Map shareholding DataFrame → OWNS relationships."""
        links = []
        for _, row in df.iterrows():
            owner_cin = str(row.get("OwnerCIN", row.get("ownerCIN", ""))).strip().upper()
            owned_cin = str(row.get("OwnedCIN", row.get("ownedCIN", ""))).strip().upper()
            if not owner_cin or not owned_cin:
                continue

            links.append({
                "link_type": "OWNS",
                "source_type": "company",
                "source_id": owner_cin,
                "target_type": "company",
                "target_id": owned_cin,
                "properties": {
                    "percentageHeld": float(row.get("PercentageHeld", row.get("percentageHeld", 0))),
                    "holdingType": str(row.get("HoldingType", "direct")),
                    "asOfDate": self._parse_date(row.get("AsOfDate")),
                    "votingRights": float(row.get("VotingRights", row.get("percentageHeld", 0))),
                },
            })
        logger.info("Mapped %d OWNS relationships", len(links))
        return links

    def map_regulatory_links(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Map regulatory_actions → SUBJECT_OF relationships."""
        links = []
        for _, row in df.iterrows():
            action_id = str(row.get("ActionID", row.get("actionId", ""))).strip()
            company_cin = str(row.get("CompanyCIN", row.get("companyCIN", ""))).strip().upper()
            if not action_id or not company_cin:
                continue

            links.append({
                "link_type": "SUBJECT_OF",
                "source_type": "company",
                "source_id": company_cin,
                "target_type": "regulatory_action",
                "target_id": action_id,
                "properties": {
                    "role": str(row.get("Role", "primary respondent")),
                    "noticeDate": self._parse_date(row.get("NoticeDate", row.get("ActionDate"))),
                },
            })
        logger.info("Mapped %d SUBJECT_OF relationships", len(links))
        return links

    def map_project_links(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Map projects → OWNS_PROJECT relationships."""
        links = []
        for _, row in df.iterrows():
            project_id = str(row.get("ProjectID", row.get("projectId", ""))).strip()
            owner_cin = str(row.get("OwnerCIN", row.get("ownerCIN", ""))).strip().upper()
            if not project_id or not owner_cin:
                continue

            links.append({
                "link_type": "OWNS_PROJECT",
                "source_type": "company",
                "source_id": owner_cin,
                "target_type": "project",
                "target_id": project_id,
                "properties": {
                    "ownershipType": str(row.get("OwnershipType", "concession")),
                    "percentageOwned": float(row.get("PercentageOwned", 100.0)),
                    "effectiveDate": self._parse_date(row.get("ContractDate")),
                },
            })
        logger.info("Mapped %d OWNS_PROJECT relationships", len(links))
        return links

    def map_insolvency_links(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Map insolvency → UNDERGOING_CIRP relationships."""
        links = []
        for _, row in df.iterrows():
            cirp_id = str(row.get("CIRPId", row.get("cirpId", ""))).strip()
            company_cin = str(row.get("CompanyCIN", row.get("companyCIN", ""))).strip().upper()
            if not cirp_id or not company_cin:
                continue

            links.append({
                "link_type": "UNDERGOING_CIRP",
                "source_type": "company",
                "source_id": company_cin,
                "target_type": "insolvency_proceeding",
                "target_id": cirp_id,
                "properties": {},
            })
        logger.info("Mapped %d UNDERGOING_CIRP relationships", len(links))
        return links

    def map_address_links(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Map company addresses → REGISTERED_AT relationships."""
        links = []
        for _, row in df.iterrows():
            cin = str(row.get("CIN", row.get("cin", ""))).strip().upper()
            address = str(row.get("NormalizedAddress", row.get("RegisteredAddress", ""))).strip()
            if not cin or not address:
                continue

            links.append({
                "link_type": "REGISTERED_AT",
                "source_type": "company",
                "source_id": cin,
                "target_type": "address",
                "target_id": address,
                "properties": {
                    "registrationType": "registered office",
                },
            })
        return links

    def _parse_date(self, value: Any) -> str | None:
        if value is None:
            return None
        try:
            import pandas as pd
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        try:
            d = IndianDate_Type.validate(str(value).strip())
            return str(d)
        except Exception:
            return None


relationship_mapper = RelationshipMapper()
