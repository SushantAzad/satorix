"""
MongoDB connector using pymongo.

Covers use-cases where companies store operational data, CRM records, or
log events in MongoDB (Atlas or self-hosted). Handles BSON type serialization
(ObjectId → str, datetime preserved).

config keys:
  uri               : str   MongoDB connection URI (mongodb:// or mongodb+srv://)
  database          : str
  collection        : str   (mutually exclusive with pipeline)
  pipeline          : list  aggregation pipeline as JSON list
  filter_query      : dict  simple find filter (JSON)
  projection        : dict  field projection (JSON)
  sort_field        : str   field for incremental sort
  sort_direction    : int   1 (asc) or -1 (desc), default 1
  batch_size        : int   cursor batch_size, default 1000
  timestamp_field   : str   ISO date field for incremental — default "updatedAt"
  id_field          : str   ObjectId field — default "_id"
  tls               : bool  enable TLS — default False
  tls_ca_file       : str   path to CA file for Atlas / TLS
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    AuthenticationError,
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)


def _bson_serialize(obj):
    """Convert BSON-specific types to JSON-serializable Python types."""
    try:
        from bson import ObjectId
        from bson.decimal128 import Decimal128
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, Decimal128):
            return float(obj.to_decimal())
    except ImportError:
        pass
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def _flatten_doc(doc: dict, prefix: str = "", sep: str = ".") -> dict:
    """Flatten one level of nested MongoDB document for DataFrame-friendliness."""
    flat: dict = {}
    for k, v in doc.items():
        key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict) and len(v) <= 5:
            flat.update(_flatten_doc(v, prefix=key, sep=sep))
        elif isinstance(v, (list, dict)):
            flat[key] = json.dumps(v, default=_bson_serialize)
        else:
            flat[key] = _bson_serialize(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
    return flat


class MongoDBConnector(BaseConnector):
    """MongoDB connector with aggregation pipeline and incremental support."""

    REQUIRED_CONFIG_FIELDS = ["uri", "database", "collection"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.uri: str = config.get("uri", "")
        self.database: str = config.get("database", "")
        self.collection: str = config.get("collection", "")
        self.pipeline: Optional[list] = config.get("pipeline")
        self.filter_query: dict = config.get("filter_query", {})
        self.projection: Optional[dict] = config.get("projection")
        self.sort_field: str = config.get("sort_field", "")
        self.sort_direction: int = int(config.get("sort_direction", 1))
        self.cursor_batch_size: int = int(config.get("batch_size", 1000))
        self.timestamp_field: str = config.get("timestamp_field", "updatedAt")
        self.id_field: str = config.get("id_field", "_id")
        self.tls: bool = bool(config.get("tls", False))
        self.tls_ca_file: Optional[str] = config.get("tls_ca_file")

    def _get_client(self):
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise ImportError("pymongo not installed. Run: pip install pymongo") from exc

        kwargs: dict = {}
        if self.tls:
            kwargs["tls"] = True
            if self.tls_ca_file:
                kwargs["tlsCAFile"] = self.tls_ca_file

        return MongoClient(self.uri, **kwargs)

    def _get_collection(self, client):
        return client[self.database][self.collection]

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            client = self._get_client()
            db = client[self.database]
            # ping command is the canonical connection test
            db.command("ping")
            stats = db.command("collstats", self.collection)
            count = stats.get("count", 0)
            client.close()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Connected to {self.database}.{self.collection} ({count:,} docs)",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            err = str(exc)
            if "authentication" in err.lower() or "auth" in err.lower():
                raise AuthenticationError(self.source_id, err)
            return ConnectionTestResult(
                success=False, message=err,
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("mongodb_schema_detection"):
            client = self._get_client()
            try:
                coll = self._get_collection(client)
                samples = list(coll.find(self.filter_query, limit=20))
                if not samples:
                    return SchemaDetectionResult(columns=[], total_columns=0)

                # Infer schema from sample documents
                field_types: dict[str, set] = {}
                field_samples: dict[str, list] = {}
                for doc in samples:
                    flat = _flatten_doc(doc)
                    for k, v in flat.items():
                        field_types.setdefault(k, set()).add(type(v).__name__)
                        if v is not None and len(field_samples.get(k, [])) < 3:
                            field_samples.setdefault(k, []).append(v)

                columns = [
                    {
                        "name": k,
                        "type": "/".join(sorted(v)),
                        "nullable": True,
                        "sample_values": field_samples.get(k, []),
                    }
                    for k, v in field_types.items()
                ]
                count = coll.count_documents(self.filter_query)
                return SchemaDetectionResult(
                    columns=columns,
                    total_columns=len(columns),
                    detected_primary_key=self.id_field,
                    timestamp_columns=[
                        c["name"] for c in columns
                        if "datetime" in c["type"].lower()
                    ],
                    record_count_estimate=count,
                )
            finally:
                client.close()

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            client = self._get_client()
            coll = self._get_collection(client)
            docs: list[dict] = []

            if self.pipeline:
                cursor = coll.aggregate(self.pipeline, batchSize=self.cursor_batch_size)
            else:
                cursor = coll.find(
                    self.filter_query,
                    projection=self.projection,
                    batch_size=self.cursor_batch_size,
                )
                if self.sort_field:
                    cursor = cursor.sort(self.sort_field, self.sort_direction)

            for doc in cursor:
                docs.append(_flatten_doc(doc))

            client.close()
            df = pd.DataFrame(docs) if docs else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"MongoDB extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            client = self._get_client()
            coll = self._get_collection(client)
            query = dict(self.filter_query)

            if config.strategy == "timestamp" and config.last_extracted_at:
                query[self.timestamp_field] = {"$gt": config.last_extracted_at}
            elif config.strategy == "sequence" and config.last_extracted_id:
                try:
                    from bson import ObjectId
                    query[self.id_field] = {"$gt": ObjectId(config.last_extracted_id)}
                except Exception:
                    query[self.id_field] = {"$gt": config.last_extracted_id}
            else:
                client.close()
                return self.extract_full(config)

            cursor = coll.find(
                query,
                projection=self.projection,
                batch_size=self.cursor_batch_size,
            )
            if self.sort_field:
                cursor = cursor.sort(self.sort_field, self.sort_direction)

            docs = [_flatten_doc(d) for d in cursor]
            client.close()
            df = pd.DataFrame(docs) if docs else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"MongoDB incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        client = self._get_client()
        try:
            coll = self._get_collection(client)
            return coll.count_documents(self.filter_query)
        finally:
            client.close()
