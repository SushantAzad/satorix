from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from .models import LinkTypeDefinition
import logging

logger = logging.getLogger(__name__)


class LinkTypeRegistry:
    async def get_all(self, db: AsyncSession) -> list[LinkTypeDefinition]:
        result = await db.execute(select(LinkTypeDefinition))
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, api_name: str) -> Optional[LinkTypeDefinition]:
        result = await db.execute(
            select(LinkTypeDefinition).where(LinkTypeDefinition.api_name == api_name)
        )
        return result.scalar_one_or_none()

    async def upsert(self, db: AsyncSession, definition: dict) -> LinkTypeDefinition:
        existing = await self.get(db, definition["api_name"])
        if existing:
            for key, value in definition.items():
                setattr(existing, key, value)
            await db.flush()
            return existing
        link = LinkTypeDefinition(**definition)
        db.add(link)
        await db.flush()
        logger.info("Registered link type: %s", definition.get("api_name"))
        return link


link_type_registry = LinkTypeRegistry()
