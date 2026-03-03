"""Connection health monitor with latency tracking."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from layer1_ingestion.registry.models import DataSource, DataSourceHealth

logger = logging.getLogger(__name__)


class ConnectionHealthMonitor:
    """Monitor and track connection health for all data sources."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def check_health(self, source: DataSource, connector) -> DataSourceHealth:
        """Run a health check on a data source connection."""
        start = time.perf_counter()
        try:
            result = connector.test_connection()
            elapsed = (time.perf_counter() - start) * 1000

            health = DataSourceHealth(
                source_id=source.id,
                status="healthy" if result.success else "unhealthy",
                response_time_ms=result.response_time_ms or elapsed,
                error_message=result.error if not result.success else None,
                checked_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            health = DataSourceHealth(
                source_id=source.id,
                status="unreachable",
                response_time_ms=elapsed,
                error_message=str(e),
                checked_at=datetime.now(timezone.utc),
            )

        self.db.add(health)
        self.db.commit()
        self.db.refresh(health)
        return health

    def get_latest_health(self, source_id: UUID) -> Optional[DataSourceHealth]:
        return (
            self.db.query(DataSourceHealth)
            .filter(DataSourceHealth.source_id == source_id)
            .order_by(DataSourceHealth.checked_at.desc())
            .first()
        )

    def get_health_history(self, source_id: UUID, limit: int = 50) -> list[DataSourceHealth]:
        return (
            self.db.query(DataSourceHealth)
            .filter(DataSourceHealth.source_id == source_id)
            .order_by(DataSourceHealth.checked_at.desc())
            .limit(limit)
            .all()
        )

    def get_all_unhealthy(self) -> list[DataSourceHealth]:
        subquery = (
            self.db.query(
                DataSourceHealth.source_id,
                DataSourceHealth.checked_at,
            )
            .distinct(DataSourceHealth.source_id)
            .order_by(DataSourceHealth.source_id, DataSourceHealth.checked_at.desc())
            .subquery()
        )
        return (
            self.db.query(DataSourceHealth)
            .join(subquery, (DataSourceHealth.source_id == subquery.c.source_id) & (DataSourceHealth.checked_at == subquery.c.checked_at))
            .filter(DataSourceHealth.status != "healthy")
            .all()
        )
