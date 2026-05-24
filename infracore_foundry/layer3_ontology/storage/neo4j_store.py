"""
Neo4j store — all graph read/write operations with full client isolation.

Multi-tenancy model
───────────────────
Every node carries a `clientId` property.

  "PLATFORM_GLOBAL"  — public Indian registry data (MCA21, IBBI, RERA, BSE/NSE,
                       GSTN). Every tenant can read this. Written by platform
                       sync jobs that run independently of any client.

  "<client_id>"      — private data the client ingested from their own systems
                       (SAP, Tally, Zoho, CRM…). Invisible to all other clients.

Isolation guarantee
───────────────────
Every Cypher MATCH applies:
    WHERE n.clientId IN [$clientId, 'PLATFORM_GLOBAL']

get_network uses ALL(n IN nodes(path) …) so no cross-client node can ever
appear even as a transit hop in a traversal — the path is simply not returned.

Index strategy
──────────────
Call setup_indexes() once at startup (idempotent). Creates composite indexes
on (label, clientId) and (label, pk, clientId) for O(log n) per-tenant reads.
"""

from typing import Any, Optional
import logging
from core.neo4j_client import neo4j_client
from core.client_context import PLATFORM_GLOBAL

logger = logging.getLogger(__name__)

# ── Label / PK mappings ──────────────────────────────────────────────────────

LABEL_MAP: dict[str, str] = {
    "company": "Company",
    "director": "Director",
    "project": "Project",
    "regulatory_action": "RegulatoryAction",
    "legal_case": "LegalCase",
    "insolvency_proceeding": "InsolvencyProceeding",
    "address": "Address",
    "regulatory_body": "RegulatoryBody",
    "government_entity": "GovernmentEntity",
    "event": "Event",
    "alert": "Alert",
}

PK_FIELD_MAP: dict[str, str] = {
    "company": "cin",
    "director": "din",
    "project": "projectId",
    "regulatory_action": "actionId",
    "legal_case": "caseId",
    "insolvency_proceeding": "cirpId",
    "address": "normalizedAddress",
    "regulatory_body": "bodyId",
    "government_entity": "entityId",
    "event": "eventId",
    "alert": "alertId",
}

# Coalesce expression used in edge result sets — picks whichever PK field exists.
_PK_COALESCE = """coalesce(
    startNode(r).cin, startNode(r).din, startNode(r).projectId,
    startNode(r).actionId, startNode(r).caseId, startNode(r).cirpId,
    startNode(r).normalizedAddress, startNode(r).bodyId,
    startNode(r).entityId, startNode(r).eventId, startNode(r).alertId,
    toString(id(startNode(r)))
)"""
_PK_COALESCE_TGT = _PK_COALESCE.replace("startNode", "endNode")


def _serialize(val: Any) -> Any:
    """Recursively convert Neo4j native types to JSON-serialisable Python types."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _serialize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_serialize(v) for v in val]
    return val


def _clean_props(properties: dict[str, Any]) -> dict[str, Any]:
    """Strip None values and complex objects; serialise simple lists."""
    clean: dict[str, Any] = {
        k: v for k, v in properties.items()
        if v is not None and not isinstance(v, (list, dict))
    }
    for k, v in properties.items():
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            clean[k] = ",".join(v)
    return clean


class Neo4jStore:

    # ------------------------------------------------------------------
    # Schema bootstrap — call once at startup
    # ------------------------------------------------------------------

    async def setup_indexes(self) -> None:
        """Create clientId indexes for all known labels. Idempotent."""
        stmts: list[str] = []
        for obj_type, label in LABEL_MAP.items():
            pk = PK_FIELD_MAP[obj_type]
            stmts.append(
                f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.clientId)"
            )
            stmts.append(
                f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{pk}, n.clientId)"
            )
        for stmt in stmts:
            try:
                await neo4j_client.run_write(stmt, {})
            except Exception as exc:
                logger.debug("Index stmt skipped (%s…): %s", stmt[:60], exc)
        logger.info("Neo4j clientId indexes ensured for %d labels", len(LABEL_MAP))

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upsert_node(
        self,
        object_type: str,
        primary_key: str,
        properties: dict[str, Any],
        client_id: str = PLATFORM_GLOBAL,
    ) -> None:
        """
        Write or update a node.  MERGE on (pk, clientId) so that:
          - PLATFORM_GLOBAL nodes are shared across all tenants.
          - Per-client nodes are isolated within the same label.
        """
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")

        props = _clean_props(properties)
        props[pk_field] = primary_key
        props["object_type"] = object_type
        props["clientId"] = client_id

        query = f"""
        MERGE (n:{label} {{{pk_field}: $pk, clientId: $clientId}})
        SET n += $props
        RETURN n
        """
        await neo4j_client.run_write(
            query, {"pk": primary_key, "clientId": client_id, "props": props}
        )

    async def upsert_relationship(
        self,
        link_type: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        properties: dict[str, Any],
        client_id: str = PLATFORM_GLOBAL,
    ) -> None:
        """
        Create or update a relationship between two nodes.
        Both endpoints must be visible to the caller (own or global).
        """
        src_label = LABEL_MAP.get(source_type.lower(), source_type.capitalize())
        tgt_label = LABEL_MAP.get(target_type.lower(), target_type.capitalize())
        src_pk = PK_FIELD_MAP.get(source_type.lower(), "id")
        tgt_pk = PK_FIELD_MAP.get(target_type.lower(), "id")

        props = _clean_props(properties)
        props["clientId"] = client_id

        query = f"""
        MATCH (src:{src_label} {{{src_pk}: $source_id}})
        WHERE src.clientId IN [$clientId, '{PLATFORM_GLOBAL}']
        MATCH (tgt:{tgt_label} {{{tgt_pk}: $target_id}})
        WHERE tgt.clientId IN [$clientId, '{PLATFORM_GLOBAL}']
        MERGE (src)-[r:{link_type}]->(tgt)
        SET r += $props
        RETURN r
        """
        await neo4j_client.run_write(query, {
            "source_id": source_id,
            "target_id": target_id,
            "clientId": client_id,
            "props": props,
        })

    async def delete_node(
        self,
        object_type: str,
        primary_key: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> None:
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")
        await neo4j_client.run_write(
            f"MATCH (n:{label} {{{pk_field}: $pk}}) "
            f"WHERE n.clientId IN [$clientId, '{PLATFORM_GLOBAL}'] "
            "DETACH DELETE n",
            {"pk": primary_key, "clientId": client_id},
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_node(
        self,
        object_type: str,
        primary_key: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[dict]:
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")
        results = await neo4j_client.run_query(
            f"MATCH (n:{label} {{{pk_field}: $pk}}) "
            f"WHERE n.clientId IN [$clientId, '{PLATFORM_GLOBAL}'] "
            "RETURN n LIMIT 1",
            {"pk": primary_key, "clientId": client_id},
        )
        if results:
            return _serialize(dict(results[0]["n"]))
        return None

    async def get_network(
        self,
        object_type: str,
        primary_key: str,
        depth: int = 2,
        limit: int = 200,
        client_id: str = PLATFORM_GLOBAL,
    ) -> dict[str, list]:
        """
        Return a subgraph up to `depth` hops from the root node.
        ALL(n IN nodes(path) …) guarantees that Client B data never appears
        in Client A's traversal — not even as an intermediate hop.
        """
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")

        query = f"""
        MATCH path=(start:{label} {{{pk_field}: $pk}})-[*1..{depth}]-(connected)
        WHERE start.clientId IN [$clientId, '{PLATFORM_GLOBAL}']
          AND ALL(n IN nodes(path)
                  WHERE n.clientId IN [$clientId, '{PLATFORM_GLOBAL}'])
        WITH nodes(path) AS ns, relationships(path) AS rs
        UNWIND ns AS n
        WITH DISTINCT n, rs
        RETURN collect(DISTINCT properties(n)) AS nodes,
               [r IN rs | {{
                   type: type(r),
                   sourceLabel: head(labels(startNode(r))),
                   sourcePK: {_PK_COALESCE},
                   targetLabel: head(labels(endNode(r))),
                   targetPK: {_PK_COALESCE_TGT},
                   properties: properties(r)
               }}] AS edges
        LIMIT {limit}
        """
        results = await neo4j_client.run_query(
            query, {"pk": primary_key, "clientId": client_id}
        )
        if not results:
            return {"nodes": [], "edges": []}

        all_nodes: list[dict] = []
        all_edges: list[dict] = []
        seen_nodes: set[str] = set()
        seen_edges: set[str] = set()

        for row in results:
            for node in row.get("nodes", []):
                clean = _serialize(dict(node) if not isinstance(node, dict) else node)
                node_id = (
                    clean.get("cin") or clean.get("din") or clean.get("projectId")
                    or clean.get("cirpId") or str(id(clean))
                )
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    all_nodes.append(clean)
            for edge in row.get("edges", []):
                e = _serialize(dict(edge) if not isinstance(edge, dict) else edge)
                key = f"{e.get('sourcePK')}-{e.get('type')}-{e.get('targetPK')}"
                if key not in seen_edges:
                    seen_edges.add(key)
                    all_edges.append(e)

        return {"nodes": all_nodes, "edges": all_edges}

    async def find_shortest_path(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_depth: int = 5,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[list[dict]]:
        src_label = LABEL_MAP.get(source_type.lower(), source_type.capitalize())
        tgt_label = LABEL_MAP.get(target_type.lower(), target_type.capitalize())
        src_pk = PK_FIELD_MAP.get(source_type.lower(), "id")
        tgt_pk = PK_FIELD_MAP.get(target_type.lower(), "id")

        query = f"""
        MATCH (src:{src_label} {{{src_pk}: $source_id}}),
              (tgt:{tgt_label} {{{tgt_pk}: $target_id}})
        WHERE src.clientId IN [$clientId, '{PLATFORM_GLOBAL}']
          AND tgt.clientId IN [$clientId, '{PLATFORM_GLOBAL}']
        MATCH path = shortestPath((src)-[*..{max_depth}]-(tgt))
        WHERE ALL(n IN nodes(path)
                  WHERE n.clientId IN [$clientId, '{PLATFORM_GLOBAL}'])
        RETURN [n IN nodes(path) | properties(n)] AS path_nodes,
               length(path) AS path_length
        """
        results = await neo4j_client.run_query(
            query,
            {"source_id": source_id, "target_id": target_id, "clientId": client_id},
        )
        if results:
            return _serialize(results[0].get("path_nodes", []))
        return None

    async def get_beneficial_ownership_chain(
        self,
        company_cin: str,
        max_depth: int = 5,
        client_id: str = PLATFORM_GLOBAL,
    ) -> list[dict]:
        query = f"""
        MATCH path=(c:Company {{cin: $cin}})
              <-[:OWNS*1..{max_depth}]-(owner)
        WHERE c.clientId IN [$clientId, '{PLATFORM_GLOBAL}']
          AND ALL(n IN nodes(path)
                  WHERE n.clientId IN [$clientId, '{PLATFORM_GLOBAL}'])
        RETURN owner AS node, length(path) AS depth
        ORDER BY depth
        """
        results = await neo4j_client.run_query(
            query, {"cin": company_cin, "clientId": client_id}
        )
        chain = []
        for row in results:
            node = _serialize(dict(row["node"])) if row.get("node") else {}
            chain.append({
                "entity_name": node.get("name", "Unknown"),
                "entity_type": node.get("object_type", "unknown"),
                "depth": row.get("depth", 0),
                "isOffshore": node.get("isOffshore", False),
                "properties": node,
            })
        return chain
