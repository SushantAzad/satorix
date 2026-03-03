"""Batch processor for large data extraction with configurable batch sizes."""

import logging
import math
from typing import Generator
import pandas as pd

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process large DataFrames in configurable batches."""

    def __init__(self, batch_size: int = 10000) -> None:
        self.batch_size = batch_size

    def split_into_batches(self, df: pd.DataFrame) -> Generator[pd.DataFrame, None, None]:
        """Split a DataFrame into batches of configured size."""
        total = len(df)
        num_batches = math.ceil(total / self.batch_size)
        logger.info("Splitting %d records into %d batches of %d", total, num_batches, self.batch_size)
        for i in range(0, total, self.batch_size):
            batch = df.iloc[i:i + self.batch_size].copy()
            yield batch

    def process_in_batches(self, df: pd.DataFrame, processor_fn, **kwargs) -> list:
        """Apply a processor function to each batch and collect results."""
        results = []
        for batch_idx, batch in enumerate(self.split_into_batches(df)):
            try:
                result = processor_fn(batch, batch_index=batch_idx, **kwargs)
                results.append(result)
                logger.debug("Batch %d processed: %d records", batch_idx, len(batch))
            except Exception as e:
                logger.error("Batch %d failed: %s", batch_idx, str(e))
                results.append({"batch_index": batch_idx, "error": str(e), "records": len(batch)})
        return results
