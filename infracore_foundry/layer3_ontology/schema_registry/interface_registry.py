from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from .models import InterfaceDefinition
import logging

logger = logging.getLogger(__name__)

INTERFACE_DEFINITIONS = [
    {
        "api_name": "RegulatableEntity",
        "display_name": "Regulatable Entity",
        "implementing_types": ["Company", "Director"],
        "shared_properties": ["name", "status", "riskScore", "riskFlags"],
        "description": "Any entity subject to regulatory oversight",
    },
    {
        "api_name": "FinancialEntity",
        "display_name": "Financial Entity",
        "implementing_types": ["Company", "Project"],
        "shared_properties": ["totalDebt", "revenue", "currentRatio", "debtToEquity"],
        "description": "Any entity with financial metrics",
    },
    {
        "api_name": "GeographicEntity",
        "display_name": "Geographic Entity",
        "implementing_types": ["Company", "Project", "Address"],
        "shared_properties": ["state", "pin", "city"],
        "description": "Any entity with a geographic location",
    },
    {
        "api_name": "TemporalEntity",
        "display_name": "Temporal Entity",
        "implementing_types": [
            "Company", "Director", "Project", "RegulatoryAction",
            "LegalCase", "InsolvencyProceeding", "Address",
            "RegulatoryBody", "GovernmentEntity", "Event", "Alert",
        ],
        "shared_properties": ["lastUpdated"],
        "description": "Any entity that can be queried at a point in time",
    },
]


class InterfaceRegistry:
    async def get_all(self, db: AsyncSession) -> list[InterfaceDefinition]:
        result = await db.execute(select(InterfaceDefinition))
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, api_name: str) -> Optional[InterfaceDefinition]:
        result = await db.execute(
            select(InterfaceDefinition).where(InterfaceDefinition.api_name == api_name)
        )
        return result.scalar_one_or_none()

    async def seed_interfaces(self, db: AsyncSession) -> None:
        for defn in INTERFACE_DEFINITIONS:
            existing = await self.get(db, defn["api_name"])
            if not existing:
                iface = InterfaceDefinition(**defn)
                db.add(iface)
        await db.flush()
        logger.info("Interface definitions seeded")


interface_registry = InterfaceRegistry()
