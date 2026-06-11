"""Connection health monitor with latency tracking, circuit breaker, and schema drift detection."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from layer1_ingestion.registry.models import DataSource, DataSourceHealth

logger = logging.getLogger(__name__)

# Open circuit after this many consecutive failures
CIRCUIT_BREAKER_THRESHOLD = 5
# Recover circuit after this many consecutive successes
CIRCUIT_RECOVERY_THRESHOLD = 2


class ConnectionHealthMonitor:
    """Monitor and track connection health for all data sources."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def check_health(
        self,
        source: DataSource,
        connector,
        previous_schema_fingerprint: Optional[str] = None,
    ) -> DataSourceHealth:
        """
        Run a health check on a data source connection.

        Updates the source's circuit-breaker state on consecutive failures.
        Detects schema drift if a previous fingerprint is provided.
        """
        start = time.perf_counter()
        is_reachable = False
        error_msg: Optional[str] = None
        schema_matches: Optional[bool] = None
        current_fingerprint: Optional[str] = None

        if source.circuit_open:
            # Circuit is open: probe for recovery using a fast test
            logger.info(
                "Circuit open for source %s — running recovery probe", source.id,
            )

        try:
            result = connector.test_connection()
            elapsed_ms = (time.perf_counter() - start) * 1000
            is_reachable = result.success
            error_msg = result.error if not result.success else None

            if result.success:
                # Schema drift detection
                if previous_schema_fingerprint is not None:
                    try:
                        schema_result = connector.extract_schema()
                        import hashlib
                        schema_str = ",".join(
                            f"{c['name']}:{c['type']}"
                            for c in sorted(schema_result.columns, key=lambda x: x["name"])
                        )
                        current_fingerprint = hashlib.sha256(schema_str.encode()).hexdigest()[:16]
                        schema_matches = (current_fingerprint == previous_schema_fingerprint)
                        if not schema_matches:
                            logger.warning(
                                "Schema drift detected for source %s: %s → %s",
                                source.id, previous_schema_fingerprint, current_fingerprint,
                            )
                    except Exception as schema_exc:
                        logger.warning(
                            "Schema check failed for source %s: %s",
                            source.id, str(schema_exc),
                        )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            is_reachable = False
            error_msg = str(exc)

        # --- Circuit breaker state update ---
        self._update_circuit_breaker(source, is_reachable)

        health = DataSourceHealth(
            source_id=source.id,
            checked_at=datetime.now(timezone.utc),
            is_reachable=is_reachable,
            response_time_ms=elapsed_ms,
            error_message=error_msg,
            schema_matches=schema_matches,
            schema_fingerprint=current_fingerprint,
        )
        self.db.add(health)
        self.db.commit()
        self.db.refresh(health)
        return health

    def _update_circuit_breaker(self, source: DataSource, is_reachable: bool) -> None:
        if is_reachable:
            if source.consecutive_failures > 0:
                source.consecutive_failures = max(
                    0, source.consecutive_failures - CIRCUIT_RECOVERY_THRESHOLD
                )
            if source.circuit_open and source.consecutive_failures == 0:
                source.circuit_open = False
                logger.info("Circuit closed (recovered) for source %s", source.id)
        else:
            source.consecutive_failures += 1
            if (not source.circuit_open
                    and source.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD):
                source.circuit_open = True
                logger.error(
                    "Circuit opened for source %s after %d consecutive failures",
                    source.id, source.consecutive_failures,
                )
        self.db.add(source)
        # Caller commits

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
        """Return the most recent health record for every unhealthy source."""
        sql = text("""
            SELECT DISTINCT ON (source_id)
                id, source_id, checked_at, is_reachable,
                response_time_ms, error_message, schema_matches,
                schema_fingerprint, freshness_score, volume_anomaly,
                alert_sent, alert_type
            FROM data_source_health
            WHERE is_reachable = FALSE
            ORDER BY source_id, checked_at DESC
        """)
        rows = self.db.execute(sql).mappings().all()
        return [
            DataSourceHealth(**{k: v for k, v in row.items()})
            for row in rows
        ]
