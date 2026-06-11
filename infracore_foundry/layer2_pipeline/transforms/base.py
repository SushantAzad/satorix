"""
Base class for all Layer 2 transforms.
Every transform is a stateless, side-effect-free function:
    apply(df, config, context) -> DataFrame
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext

logger = logging.getLogger(__name__)


class TransformError(Exception):
    """Raised when a transform cannot complete due to a configuration or data error."""


class BaseTransform(ABC):
    """
    All transforms inherit from this class.

    Subclasses must implement `apply()`. The `__call__` interface wraps
    `apply()` with context lifecycle (begin_step / end_step) and error capture.
    """

    # Set in each concrete transform class — used for registry lookup.
    transform_type: str = ""

    def __call__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        context: ExecutionContext,
        step_id: str,
    ) -> pd.DataFrame:
        """Execute the transform; update context metrics regardless of outcome."""
        records_in = len(df)
        context.begin_step(step_id, self.transform_type)

        try:
            result = self.apply(df, config, context, step_id)
            records_out = len(result)
            context.end_step(step_id, records_in, records_out)
            logger.debug(
                "Step %s (%s): %d → %d rows",
                step_id, self.transform_type, records_in, records_out,
            )
            return result
        except TransformError as exc:
            context.end_step(step_id, records_in, 0, records_failed=records_in, error_message=str(exc))
            raise
        except Exception as exc:
            msg = f"Unexpected error in {self.transform_type} step {step_id!r}: {exc}"
            logger.exception(msg)
            context.end_step(step_id, records_in, 0, records_failed=records_in, error_message=msg)
            raise TransformError(msg) from exc

    @abstractmethod
    def apply(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        context: ExecutionContext,
        step_id: str,
    ) -> pd.DataFrame:
        """
        Apply the transform to df.
        Must return a new or mutated DataFrame.
        Must NOT write to the database or MinIO.
        """

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        """
        Return a list of validation error strings, or [] if config is valid.
        Called at pipeline build time, not execution time.
        """
        return []
