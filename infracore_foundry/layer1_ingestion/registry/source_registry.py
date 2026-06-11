"""
CRUD operations for the data source registry.
Handles creation, retrieval, update, and soft-deletion of data sources.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from layer1_ingestion.core.encryption import encrypt_credential, decrypt_credential
from layer1_ingestion.registry.models import DataSource, SyncState

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Data source registry with encrypted credential storage."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_source(
        self,
        client_id: str,
        source_name: str,
        source_type: str,
        connection_config: dict,
        description: str = "",
        auth_method: str = "none",
        environment: str = "production",
        created_by: str = "system",
    ) -> DataSource:
        """
        Register a new data source with encrypted connection configuration.
        """
        encrypted_config = encrypt_credential(json.dumps(connection_config))

        source = DataSource(
            client_id=client_id,
            source_name=source_name,
            source_type=source_type,
            connection_config=encrypted_config,
            description=description,
            auth_method=auth_method,
            environment=environment,
            status="active",
            created_by=created_by,
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)

        # Initialize sync state for the new source
        sync_state = SyncState(source_id=source.id, status="idle")
        self.db.add(sync_state)
        self.db.commit()

        logger.info(
            "Created data source",
            extra={
                "source_id": str(source.id),
                "source_name": source_name,
                "source_type": source_type,
                "client_id": client_id,
            },
        )
        return source

    def get_source(self, source_id: UUID) -> Optional[DataSource]:
        """Retrieve a data source by ID."""
        return self.db.query(DataSource).filter(DataSource.id == source_id).first()

    def get_source_config(self, source_id: UUID) -> dict:
        """Retrieve and decrypt the connection configuration for a source."""
        source = self.get_source(source_id)
        if source is None:
            raise ValueError(f"Data source not found: {source_id}")
        decrypted = decrypt_credential(source.connection_config)
        return json.loads(decrypted)

    def list_sources(
        self,
        client_id: Optional[str] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[DataSource]:
        """List data sources with optional filters."""
        query = self.db.query(DataSource)
        if client_id:
            query = query.filter(DataSource.client_id == client_id)
        if source_type:
            query = query.filter(DataSource.source_type == source_type)
        if status:
            query = query.filter(DataSource.status == status)
        else:
            query = query.filter(DataSource.status != "archived")
        return query.order_by(DataSource.created_at.desc()).all()

    def update_source(
        self,
        source_id: UUID,
        **kwargs,
    ) -> DataSource:
        """
        Update a data source. If connection_config is provided, it will be encrypted.
        """
        source = self.get_source(source_id)
        if source is None:
            raise ValueError(f"Data source not found: {source_id}")

        if "connection_config" in kwargs:
            kwargs["connection_config"] = encrypt_credential(
                json.dumps(kwargs["connection_config"])
            )

        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)

        source.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(source)

        logger.info(
            "Updated data source",
            extra={"source_id": str(source_id), "fields_updated": list(kwargs.keys())},
        )
        return source

    def delete_source(self, source_id: UUID) -> DataSource:
        """Soft-delete a data source by setting status to archived."""
        source = self.get_source(source_id)
        if source is None:
            raise ValueError(f"Data source not found: {source_id}")

        source.status = "archived"
        source.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(source)

        logger.info("Archived data source", extra={"source_id": str(source_id)})
        return source

    def get_active_sources(self, client_id: Optional[str] = None) -> list[DataSource]:
        """Get all active (non-archived, non-paused) data sources."""
        query = self.db.query(DataSource).filter(DataSource.status == "active")
        if client_id:
            query = query.filter(DataSource.client_id == client_id)
        return query.all()

    def mask_config(self, source: DataSource) -> dict:
        """
        Return the connection config with sensitive values masked.
        Used for API responses where credentials should not be exposed.
        """
        try:
            config = json.loads(decrypt_credential(source.connection_config))
        except Exception:
            return {"error": "Unable to decrypt configuration"}

        sensitive_keys = {"password", "secret", "api_key", "token", "private_key", "secret_key"}
        masked = {}
        for key, value in config.items():
            if any(s in key.lower() for s in sensitive_keys):
                masked[key] = "***MASKED***"
            else:
                masked[key] = value
        return masked
