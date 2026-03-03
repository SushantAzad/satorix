"""Alert manager for connection failures and pipeline anomalies."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from layer1_ingestion.registry.models import Alert

logger = logging.getLogger(__name__)


class AlertManager:
    """Manage alerts for data source health and pipeline issues."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_alert(
        self,
        source_id: UUID,
        alert_type: str,
        severity: str,
        message: str,
        details: Optional[dict] = None,
    ) -> Alert:
        alert = Alert(
            source_id=source_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details or {},
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        logger.warning(
            "Alert created: %s — %s",
            alert_type, message,
            extra={"source_id": str(source_id), "severity": severity},
        )
        return alert

    def acknowledge_alert(self, alert_id: UUID) -> Optional[Alert]:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.status = "acknowledged"
            alert.acknowledged_at = datetime.now(timezone.utc)
            self.db.commit()
        return alert

    def resolve_alert(self, alert_id: UUID) -> Optional[Alert]:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.status = "resolved"
            alert.resolved_at = datetime.now(timezone.utc)
            self.db.commit()
        return alert

    def get_open_alerts(self, source_id: Optional[UUID] = None) -> list[Alert]:
        q = self.db.query(Alert).filter(Alert.status == "open")
        if source_id:
            q = q.filter(Alert.source_id == source_id)
        return q.order_by(Alert.created_at.desc()).all()

    def get_alerts_history(self, source_id: UUID, limit: int = 100) -> list[Alert]:
        return (
            self.db.query(Alert)
            .filter(Alert.source_id == source_id)
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .all()
        )

    def check_and_alert_on_health(self, source_id: UUID, status: str, error_message: Optional[str] = None) -> None:
        """Automatically create alerts based on health check results."""
        if status == "unhealthy":
            self.create_alert(
                source_id=source_id,
                alert_type="connection_failure",
                severity="warning",
                message=f"Connection unhealthy: {error_message or 'Unknown error'}",
            )
        elif status == "unreachable":
            self.create_alert(
                source_id=source_id,
                alert_type="connection_unreachable",
                severity="critical",
                message=f"Connection unreachable: {error_message or 'Unknown error'}",
            )

    def check_and_alert_on_sync(self, source_id: UUID, status: str, error: Optional[str] = None, records: int = 0) -> None:
        """Automatically create alerts based on sync results."""
        if status == "failed":
            self.create_alert(
                source_id=source_id,
                alert_type="sync_failure",
                severity="critical",
                message=f"Sync failed: {error or 'Unknown error'}",
            )
        elif records == 0 and status == "completed":
            self.create_alert(
                source_id=source_id,
                alert_type="empty_extraction",
                severity="info",
                message="Sync completed but extracted 0 records",
            )
