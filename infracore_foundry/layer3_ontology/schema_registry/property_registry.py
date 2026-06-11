from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from .models import PropertyDefinition
import logging

logger = logging.getLogger(__name__)


class PropertyRegistry:
    async def get_for_type(self, db: AsyncSession, object_type: str) -> list[PropertyDefinition]:
        result = await db.execute(
            select(PropertyDefinition).where(PropertyDefinition.object_type == object_type)
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, object_type: str, property_name: str) -> Optional[PropertyDefinition]:
        result = await db.execute(
            select(PropertyDefinition).where(
                PropertyDefinition.object_type == object_type,
                PropertyDefinition.property_name == property_name,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, db: AsyncSession, definition: dict) -> PropertyDefinition:
        existing = await self.get(db, definition["object_type"], definition["property_name"])
        if existing:
            for key, value in definition.items():
                setattr(existing, key, value)
            await db.flush()
            return existing
        prop = PropertyDefinition(**definition)
        db.add(prop)
        await db.flush()
        return prop


property_registry = PropertyRegistry()
