from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from .models import SchemaVersion
import logging

logger = logging.getLogger(__name__)


class VersionManager:
    async def get_current_version(self, db: AsyncSession) -> str:
        result = await db.execute(
            select(SchemaVersion).where(SchemaVersion.is_current == True).order_by(SchemaVersion.id.desc())
        )
        record = result.scalar_one_or_none()
        if record:
            return record.version
        return "1.0.0"

    async def get_changelog(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(select(SchemaVersion).order_by(SchemaVersion.id.desc()))
        versions = result.scalars().all()
        return [
            {
                "version": v.version,
                "changelog": v.changelog,
                "created_at": str(v.created_at),
                "created_by": v.created_by,
                "is_current": v.is_current,
            }
            for v in versions
        ]

    async def bump_minor(self, db: AsyncSession, changelog: str, actor: str) -> str:
        current = await self.get_current_version(db)
        major, minor, patch = (int(x) for x in current.split("."))
        minor += 1
        patch = 0
        new_version = f"{major}.{minor}.{patch}"
        return await self._create_version(db, major, minor, patch, new_version, changelog, actor)

    async def bump_patch(self, db: AsyncSession, changelog: str, actor: str) -> str:
        current = await self.get_current_version(db)
        major, minor, patch = (int(x) for x in current.split("."))
        patch += 1
        new_version = f"{major}.{minor}.{patch}"
        return await self._create_version(db, major, minor, patch, new_version, changelog, actor)

    async def _create_version(
        self, db: AsyncSession, major: int, minor: int, patch: int,
        version: str, changelog: str, actor: str
    ) -> str:
        await db.execute(update(SchemaVersion).values(is_current=False))
        record = SchemaVersion(
            version=version,
            major=major,
            minor=minor,
            patch=patch,
            changelog=changelog,
            created_by=actor,
            is_current=True,
        )
        db.add(record)
        await db.flush()
        logger.info("Schema version bumped to %s", version)
        return version


version_manager = VersionManager()
