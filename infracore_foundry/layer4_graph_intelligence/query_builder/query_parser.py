"""
QueryParser — parses natural language queries into structured graph query specs.
Uses claude-sonnet-4-6 with prompt caching for entity/intent extraction.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from core.config import settings
from core.redis_client import cache_key, cache_get, cache_set

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a graph query parser for an Indian corporate intelligence platform.
Convert natural language questions into a JSON query specification.

Output ONLY valid JSON with this schema:
{
  "intent": "network_expand | path_find | cluster_query | influence_rank | temporal_query | precursor_risk",
  "entities": [{"id": "...", "type": "Company|Director|Address|..."}],
  "hops": 2,
  "rel_types": [],
  "node_types": [],
  "filters": {},
  "time_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
}

Rules:
- CIN format: L/U + 5digits + 2letters + 4digits + 3letters + 6digits
- DIN format: 8 digits
- If entity not identified, set entities to []
- Default hops: 2
- Default intent: network_expand"""


@dataclass
class ParsedQuery:
    intent: str
    entities: list[dict[str, str]] = field(default_factory=list)
    hops: int = 2
    rel_types: list[str] = field(default_factory=list)
    node_types: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    time_range: Optional[dict[str, str]] = None
    raw_query: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "entities": self.entities,
            "hops": self.hops,
            "rel_types": self.rel_types,
            "node_types": self.node_types,
            "filters": self.filters,
            "time_range": self.time_range,
        }


class QueryParser:
    def __init__(self) -> None:
        if settings.anthropic_api_key:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        else:
            self._client = None

    async def parse(self, natural_language_query: str) -> ParsedQuery:
        ck = cache_key("query_parse", q=natural_language_query)
        cached = await cache_get(ck)
        if cached:
            return ParsedQuery(**cached, raw_query=natural_language_query)

        if not self._client:
            return self._heuristic_parse(natural_language_query)

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": natural_language_query}],
            )
            raw = response.content[0].text.strip()
            spec = json.loads(raw)
            result = ParsedQuery(
                intent=spec.get("intent", "network_expand"),
                entities=spec.get("entities", []),
                hops=spec.get("hops", 2),
                rel_types=spec.get("rel_types", []),
                node_types=spec.get("node_types", []),
                filters=spec.get("filters", {}),
                time_range=spec.get("time_range"),
                raw_query=natural_language_query,
            )
            await cache_set(ck, result.to_dict(), settings.redis_ttl_long)
            return result
        except Exception as exc:
            logger.error("Query parsing failed: %s", exc)
            return self._heuristic_parse(natural_language_query)

    def _heuristic_parse(self, query: str) -> ParsedQuery:
        import re
        intent = "network_expand"
        if any(w in query.lower() for w in ["path", "connection", "between", "link"]):
            intent = "path_find"
        elif any(w in query.lower() for w in ["cluster", "group", "network"]):
            intent = "cluster_query"
        elif any(w in query.lower() for w in ["rank", "influence", "central"]):
            intent = "influence_rank"
        elif any(w in query.lower() for w in ["history", "timeline", "when", "change"]):
            intent = "temporal_query"
        elif any(w in query.lower() for w in ["risk", "cirp", "insolvency", "bankrupt"]):
            intent = "precursor_risk"

        entities = []
        cin_matches = re.findall(r"[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}", query)
        for cin in cin_matches:
            entities.append({"id": cin, "type": "Company"})
        din_matches = re.findall(r"\b\d{8}\b", query)
        for din in din_matches:
            entities.append({"id": din, "type": "Director"})

        return ParsedQuery(intent=intent, entities=entities, raw_query=query)
