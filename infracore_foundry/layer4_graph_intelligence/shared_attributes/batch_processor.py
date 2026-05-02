"""
SharedAttributeBatchProcessor — orchestrates all shared-attribute detection
and writes inferred links (SHARES_ADDRESS_WITH, SHARES_DIRECTOR_WITH,
COMMON_BENEFICIAL_OWNER) back through the ObjectDataFunnel.
"""
import logging
import sys
import os
from typing import Any

# Layer 3 funnel import (write-back path)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../layer3_ontology"))
from storage.object_data_funnel import ObjectDataFunnel

from .address_detector import SharedAddressDetector
from .director_detector import SharedDirectorDetector
from .owner_detector import SharedOwnerDetector

logger = logging.getLogger(__name__)


class SharedAttributeBatchProcessor:
    def __init__(self) -> None:
        self._address = SharedAddressDetector()
        self._director = SharedDirectorDetector()
        self._owner = SharedOwnerDetector()
        self._funnel = ObjectDataFunnel()

    async def run(self, batch_run_id: str) -> dict[str, int]:
        stats: dict[str, int] = {}

        address_pairs = await self._address.detect_bulk(limit=50_000)
        stats["address_pairs"] = len(address_pairs)
        for pair in address_pairs:
            await self._funnel.write_link(
                source_id=pair["entity1"],
                source_type=pair["type1"],
                target_id=pair["entity2"],
                target_type=pair["type2"],
                link_type="SHARES_ADDRESS_WITH",
                properties={"sharedAddressId": pair["addressId"], "computedBy": "l4_batch"},
            )

        director_pairs = await self._director.detect_bulk(min_shared=2, limit=50_000)
        stats["director_pairs"] = len(director_pairs)
        for pair in director_pairs:
            await self._funnel.write_link(
                source_id=pair["entity1"],
                source_type="Company",
                target_id=pair["entity2"],
                target_type="Company",
                link_type="SHARES_DIRECTOR_WITH",
                properties={
                    "sharedDirectors": pair["sharedDirectors"],
                    "sharedCount": pair["sharedCount"],
                    "computedBy": "l4_batch",
                },
            )

        circular = await self._owner.detect_circular_ownership(limit=100)
        stats["circular_ownership"] = len(circular)

        logger.info("SharedAttributeBatch complete: %s", stats)
        return stats
