"""
QueryComposer — translates a ParsedQuery into concrete API calls.
Acts as the router between the NL query endpoint and the individual subsystems.
"""
import logging
from typing import Any

from .query_parser import ParsedQuery
from network.network_mapper import NetworkMapper
from pathfinding.shortest_path import ShortestPathFinder
from influence.influence_aggregator import InfluenceAggregator
from temporal.event_correlator import EventCorrelator
from temporal.precursor_model import PrecursorModel

logger = logging.getLogger(__name__)


class QueryComposer:
    def __init__(self) -> None:
        self._mapper = NetworkMapper()
        self._path_finder = ShortestPathFinder()
        self._influence = InfluenceAggregator()
        self._correlator = EventCorrelator()
        self._precursor = PrecursorModel()

    async def execute(self, parsed: ParsedQuery) -> dict[str, Any]:
        intent = parsed.intent
        entities = parsed.entities

        if intent == "network_expand":
            if not entities:
                return {"error": "No entity identified for network expansion"}
            seed = entities[0]
            network = await self._mapper.expand(
                seed_id=seed["id"],
                hops=parsed.hops,
                node_types=parsed.node_types or None,
                rel_types=parsed.rel_types or None,
            )
            return {"intent": intent, "result": network.to_dict()}

        elif intent == "path_find":
            if len(entities) < 2:
                return {"error": "Path finding requires two entities"}
            path = await self._path_finder.find(
                source_id=entities[0]["id"],
                target_id=entities[1]["id"],
            )
            return {"intent": intent, "result": path.to_dict()}

        elif intent == "influence_rank":
            entity_type = entities[0]["type"] if entities else None
            scores = await self._influence.top_k(entity_type=entity_type, k=50)
            return {"intent": intent, "result": scores}

        elif intent == "temporal_query":
            if not entities:
                return {"error": "No entity identified for temporal query"}
            timeline = await self._correlator.get_entity_timeline(entities[0]["id"])
            return {"intent": intent, "result": timeline}

        elif intent == "precursor_risk":
            if not entities:
                return {"error": "No entity identified for risk assessment"}
            assessment = await self._precursor.assess(entities[0]["id"])
            return {"intent": intent, "result": assessment.to_dict()}

        else:
            return {"error": f"Unknown intent: {intent}"}
