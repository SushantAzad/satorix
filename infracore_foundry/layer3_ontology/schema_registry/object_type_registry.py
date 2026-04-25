from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional
from .models import ObjectTypeDefinition
import logging

logger = logging.getLogger(__name__)


class ObjectTypeRegistry:
    async def get_all(self, db: AsyncSession) -> list[ObjectTypeDefinition]:
        result = await db.execute(select(ObjectTypeDefinition).where(ObjectTypeDefinition.is_active == True))
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, api_name: str) -> Optional[ObjectTypeDefinition]:
        result = await db.execute(
            select(ObjectTypeDefinition).where(ObjectTypeDefinition.api_name == api_name)
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, definition: dict) -> ObjectTypeDefinition:
        obj = ObjectTypeDefinition(**definition)
        db.add(obj)
        await db.flush()
        logger.info("Registered object type: %s", definition.get("api_name"))
        return obj

    async def upsert(self, db: AsyncSession, definition: dict) -> ObjectTypeDefinition:
        existing = await self.get(db, definition["api_name"])
        if existing:
            for key, value in definition.items():
                setattr(existing, key, value)
            await db.flush()
            return existing
        return await self.create(db, definition)


object_type_registry = ObjectTypeRegistry()
