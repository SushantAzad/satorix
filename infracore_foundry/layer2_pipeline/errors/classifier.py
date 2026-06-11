"""
Error classification for Layer 2 pipeline failures.
Three top-level types: source | transform | system
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    SYSTEM = "system"


class ErrorSubtype(str, Enum):
    # Source errors
    FILE_NOT_FOUND = "file_not_found"
    SCHEMA_MISMATCH = "schema_mismatch"
    EMPTY_INPUT = "empty_input"
    CORRUPT_DATA = "corrupt_data"
    ENCODING_ERROR = "encoding_error"

    # Transform errors
    TYPE_CAST_FAILURE = "type_cast_failure"
    DATE_PARSE_FAILURE = "date_parse_failure"
    REGEX_NO_MATCH = "regex_no_match"
    MISSING_COLUMN = "missing_column"
    QUALITY_RULE_VIOLATION = "quality_rule_violation"
    EXPRESSION_EVAL_FAILURE = "expression_eval_failure"
    JOIN_KEY_NOT_FOUND = "join_key_not_found"

    # System errors
    MINIO_READ_FAILURE = "minio_read_failure"
    MINIO_WRITE_FAILURE = "minio_write_failure"
    DB_WRITE_FAILURE = "db_write_failure"
    OUT_OF_MEMORY = "out_of_memory"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    error_type: ErrorType
    error_subtype: ErrorSubtype
    severity: str              # error | warning | info
    message: str
    step_id: Optional[str] = None
    original_exception: Optional[Exception] = None


def classify(
    exc: Exception,
    step_id: Optional[str] = None,
    context_hint: str = "",
) -> ClassifiedError:
    """
    Classify any exception into a structured ClassifiedError.
    Rules are matched by exception type and message content.
    """
    msg = str(exc).lower()
    exc_type = type(exc).__name__

    # Source-level errors
    if "no such file" in msg or "file not found" in msg or "nosuchkey" in msg:
        return ClassifiedError(ErrorType.SOURCE, ErrorSubtype.FILE_NOT_FOUND, "error", str(exc), step_id, exc)

    if "schema" in msg and ("mismatch" in msg or "column" in msg):
        return ClassifiedError(ErrorType.SOURCE, ErrorSubtype.SCHEMA_MISMATCH, "error", str(exc), step_id, exc)

    if "empty" in msg and "dataframe" in msg:
        return ClassifiedError(ErrorType.SOURCE, ErrorSubtype.EMPTY_INPUT, "warning", str(exc), step_id, exc)

    if "encoding" in msg or "codec" in msg or "utf" in msg:
        return ClassifiedError(ErrorType.SOURCE, ErrorSubtype.ENCODING_ERROR, "error", str(exc), step_id, exc)

    # Transform errors
    if "column" in msg and ("not found" in msg or "not in" in msg):
        return ClassifiedError(ErrorType.TRANSFORM, ErrorSubtype.MISSING_COLUMN, "error", str(exc), step_id, exc)

    if "parse" in msg and "date" in msg:
        return ClassifiedError(ErrorType.TRANSFORM, ErrorSubtype.DATE_PARSE_FAILURE, "warning", str(exc), step_id, exc)

    if "quality_rule" in context_hint.lower() or "quality" in msg:
        return ClassifiedError(ErrorType.TRANSFORM, ErrorSubtype.QUALITY_RULE_VIOLATION, "error", str(exc), step_id, exc)

    if "eval" in msg or "expression" in msg:
        return ClassifiedError(ErrorType.TRANSFORM, ErrorSubtype.EXPRESSION_EVAL_FAILURE, "error", str(exc), step_id, exc)

    # System errors
    if "s3error" in exc_type.lower() or "minio" in msg:
        if "get" in msg or "download" in msg or "read" in msg:
            return ClassifiedError(ErrorType.SYSTEM, ErrorSubtype.MINIO_READ_FAILURE, "error", str(exc), step_id, exc)
        return ClassifiedError(ErrorType.SYSTEM, ErrorSubtype.MINIO_WRITE_FAILURE, "error", str(exc), step_id, exc)

    if "memorylimiterror" in exc_type.lower() or "out of memory" in msg or "memoryerror" in exc_type.lower():
        return ClassifiedError(ErrorType.SYSTEM, ErrorSubtype.OUT_OF_MEMORY, "error", str(exc), step_id, exc)

    if "timeout" in msg or "timedout" in msg:
        return ClassifiedError(ErrorType.SYSTEM, ErrorSubtype.TIMEOUT, "error", str(exc), step_id, exc)

    if "sqlalchemy" in exc_type.lower() or "operationalerror" in exc_type.lower():
        return ClassifiedError(ErrorType.SYSTEM, ErrorSubtype.DB_WRITE_FAILURE, "error", str(exc), step_id, exc)

    return ClassifiedError(ErrorType.SYSTEM, ErrorSubtype.UNKNOWN, "error", str(exc), step_id, exc)
