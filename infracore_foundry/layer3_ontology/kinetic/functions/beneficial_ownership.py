from dataclasses import dataclass
from typing import Any
import logging
from storage.neo4j_store import Neo4jStore

logger = logging.getLogger(__name__)


@dataclass
class OwnershipNode:
    entity_name: str
    entity_type: str
    percentage: float
    isOffshore: bool
    depth: int
    properties: dict[str, Any]


async def computeBeneficialOwnershipChain(
    company_cin: str, max_depth: int = 5
) -> list[OwnershipNode]:
    store = Neo4jStore()
    chain = await store.get_beneficial_ownership_chain(company_cin, max_depth)
    nodes = []
    for item in chain:
        props = item.get("properties", {})
        nodes.append(OwnershipNode(
            entity_name=item.get("entity_name", "Unknown"),
            entity_type=item.get("entity_type", "unknown"),
            percentage=float(props.get("percentageHeld", 0)),
            isOffshore=bool(item.get("isOffshore", False)),
            depth=item.get("depth", 0),
            properties=props,
        ))
    return nodes
