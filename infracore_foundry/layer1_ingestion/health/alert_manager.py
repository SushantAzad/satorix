"""Alert manager for connection failures and pipeline anomalies."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
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
    ) -> Optional[Alert]:
        """
        Create an alert. Returns None if an identical open alert already exists
        (deduplication via unique index on source_id + alert_type WHERE status='open').
        """
        source_id_str = str(source_id)
        alert = Alert(
            source_id=source_id_str,
            alert_type=alert_type,
            severity=severity,
            title=f"{alert_type.replace('_', ' ').title()} — {source_id_str[:8]}",
            message=message,
            details=details or {},
            status="open",
            created_at=datetime.now(timezone.utc),
        )
        try:
            self.db.add(alert)
            self.db.flush()   # catch unique violation before commit
            self.db.commit()
            self.db.refresh(alert)
            logger.warning(
                "Alert created: %s — %s",
                alert_type, message,
                extra={"source_id": source_id_str, "severity": severity},
            )
            return alert
        except IntegrityError:
            self.db.rollback()
            logger.debug(
                "Duplicate alert suppressed: source=%s type=%s",
                source_id_str, alert_type,
            )
            return None

    def acknowledge_alert(self, alert_id: UUID) -> Optional[Alert]:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert and alert.status == "open":
            alert.status = "acknowledged"
            alert.acknowledged_at = datetime.now(timezone.utc)
            self.db.commit()
        return alert

    def resolve_alert(self, alert_id: UUID, resolved_by: str = "system", note: str = "") -> Optional[Alert]:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert and alert.status in ("open", "acknowledged"):
            alert.status = "resolved"
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by = resolved_by
            alert.resolution_note = note or None
            self.db.commit()
        return alert

    def resolve_alerts_for_source(self, source_id: UUID, alert_type: str) -> int:
        """Auto-resolve open alerts when the underlying condition clears."""
        source_id_str = str(source_id)
        rows = (
            self.db.query(Alert)
            .filter(
                Alert.source_id == source_id_str,
                Alert.alert_type == alert_type,
                Alert.status.in_(["open", "acknowledged"]),
            )
            .all()
        )
        for alert in rows:
            alert.status = "resolved"
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by = "system"
            alert.resolution_note = "Auto-resolved: condition cleared"
        if rows:
            self.db.commit()
        return len(rows)

    def get_open_alerts(self, source_id: Optional[UUID] = None) -> list[Alert]:
        q = self.db.query(Alert).filter(Alert.status == "open")
        if source_id:
            q = q.filter(Alert.source_id == str(source_id))
        return q.order_by(Alert.created_at.desc()).all()

    def get_alerts_history(self, source_id: UUID, limit: int = 100) -> list[Alert]:
        return (
            self.db.query(Alert)
            .filter(Alert.source_id == str(source_id))
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .all()
        )

    def check_and_alert_on_health(
        self,
        source_id: UUID,
        is_reachable: bool,
        error_message: Optional[str] = None,
        schema_drift: bool = False,
    ) -> None:
        """Create or auto-resolve alerts based on health check result."""
        if not is_reachable:
            self.create_alert(
                source_id=source_id,
                alert_type="connection_unreachable",
                severity="critical",
                message=f"Connection unreachable: {error_message or 'No error detail'}",
                details={"error": error_message},
            )
        else:
            # Source recovered — resolve any existing unreachable alert
            self.resolve_alerts_for_source(source_id, "connection_unreachable")

        if schema_drift:
            self.create_alert(
                source_id=source_id,
                alert_type="schema_drift",
                severity="high",
                message="Source schema changed since last extraction",
            )

    def check_and_alert_on_sync(
        self,
        source_id: UUID,
        status: str,
        error: Optional[str] = None,
        records: int = 0,
    ) -> None:
        """Create or resolve alerts based on sync run outcome."""
        if status == "failed":
            self.create_alert(
                source_id=source_id,
                alert_type="sync_failure",
                severity="critical",
                message=f"Sync failed: {error or 'Unknown error'}",
                details={"error": error},
            )
        elif status == "completed":
            # Successful sync clears any prior sync_failure alert
            self.resolve_alerts_for_source(source_id, "sync_failure")
            if records == 0:
                self.create_alert(
                    source_id=source_id,
                    alert_type="empty_extraction",
                    severity="warning",
                    message="Sync completed but extracted 0 records — verify source has data",
                )
