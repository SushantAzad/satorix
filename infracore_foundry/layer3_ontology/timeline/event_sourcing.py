from storage.event_store import EventStore, OntologyEvent
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional


class EventSourcingService:
    def __init__(self) -> None:
        self._store = EventStore()

    async def emit(self, db: AsyncSession, event: OntologyEvent) -> None:
        await self._store.emit(db, event)

    async def get_events(
        self,
        db: AsyncSession,
        object_type: str,
        object_id: str,
        start: Optional[Any] = None,
        end: Optional[Any] = None,
    ) -> list[dict]:
        return await self._store.get_events(db, object_type, object_id, start, end)


event_sourcing = EventSourcingService()
