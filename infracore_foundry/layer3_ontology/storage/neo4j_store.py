from typing import Any, Optional
import logging
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

LABEL_MAP = {
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

PK_FIELD_MAP = {
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


class Neo4jStore:
    async def upsert_node(self, object_type: str, primary_key: str, properties: dict[str, Any]) -> None:
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")

        # Filter out None values and complex objects
        clean_props = {
            k: v for k, v in properties.items()
            if v is not None and not isinstance(v, (list, dict))
        }
        # Store lists as comma-separated strings for Neo4j compatibility
        for k, v in properties.items():
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                clean_props[k] = ",".join(v)

        clean_props[pk_field] = primary_key
        clean_props["object_type"] = object_type

        query = f"""
        MERGE (n:{label} {{{pk_field}: $pk}})
        SET n += $props
        RETURN n
        """
        await neo4j_client.run_write(query, {"pk": primary_key, "props": clean_props})

    async def upsert_relationship(
        self,
        link_type: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        properties: dict[str, Any],
    ) -> None:
        src_label = LABEL_MAP.get(source_type.lower(), source_type.capitalize())
        tgt_label = LABEL_MAP.get(target_type.lower(), target_type.capitalize())
        src_pk = PK_FIELD_MAP.get(source_type.lower(), "id")
        tgt_pk = PK_FIELD_MAP.get(target_type.lower(), "id")

        clean_props = {k: v for k, v in properties.items() if v is not None and not isinstance(v, (list, dict))}

        query = f"""
        MATCH (src:{src_label} {{{src_pk}: $source_id}})
        MATCH (tgt:{tgt_label} {{{tgt_pk}: $target_id}})
        MERGE (src)-[r:{link_type}]->(tgt)
        SET r += $props
        RETURN r
        """
        await neo4j_client.run_write(query, {
            "source_id": source_id,
            "target_id": target_id,
            "props": clean_props,
        })

    async def get_node(self, object_type: str, primary_key: str) -> Optional[dict]:
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")
        results = await neo4j_client.run_query(
            f"MATCH (n:{label} {{{pk_field}: $pk}}) RETURN n",
            {"pk": primary_key},
        )
        if results:
            return dict(results[0]["n"])
        return None

    async def get_network(
        self,
        object_type: str,
        primary_key: str,
        depth: int = 2,
        limit: int = 200,
    ) -> dict[str, list]:
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")

        query = f"""
        MATCH path=(start:{label} {{{pk_field}: $pk}})-[*1..{depth}]-(connected)
        WITH nodes(path) AS ns, relationships(path) AS rs
        UNWIND ns AS n
        WITH DISTINCT n, rs
        RETURN collect(DISTINCT properties(n)) AS nodes,
               [r IN rs | {{
                   type: type(r),
                   source: id(startNode(r)),
                   target: id(endNode(r)),
                   properties: properties(r)
               }}] AS edges
        LIMIT {limit}
        """
        results = await neo4j_client.run_query(query, {"pk": primary_key})
        if not results:
            return {"nodes": [], "edges": []}

        all_nodes: list[dict] = []
        all_edges: list[dict] = []
        seen_nodes: set = set()
        seen_edges: set = set()

        for row in results:
            for node in row.get("nodes", []):
                node_id = node.get("cin") or node.get("din") or node.get("projectId") or str(node)
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    all_nodes.append(node)
            for edge in row.get("edges", []):
                edge_key = f"{edge['source']}-{edge['type']}-{edge['target']}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    all_edges.append(edge)

        return {"nodes": all_nodes, "edges": all_edges}

    async def find_shortest_path(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[list[dict]]:
        src_label = LABEL_MAP.get(source_type.lower(), source_type.capitalize())
        tgt_label = LABEL_MAP.get(target_type.lower(), target_type.capitalize())
        src_pk = PK_FIELD_MAP.get(source_type.lower(), "id")
        tgt_pk = PK_FIELD_MAP.get(target_type.lower(), "id")

        query = f"""
        MATCH (src:{src_label} {{{src_pk}: $source_id}}),
              (tgt:{tgt_label} {{{tgt_pk}: $target_id}})
        MATCH path = shortestPath((src)-[*..{max_depth}]-(tgt))
        RETURN [n IN nodes(path) | properties(n)] AS path_nodes,
               length(path) AS path_length
        """
        results = await neo4j_client.run_query(query, {"source_id": source_id, "target_id": target_id})
        if results:
            return results[0].get("path_nodes", [])
        return None

    async def get_beneficial_ownership_chain(self, company_cin: str, max_depth: int = 5) -> list[dict]:
        query = f"""
        MATCH path=(c:Company {{cin: $cin}})<-[:OWNS*1..{max_depth}]-(owner)
        RETURN owner AS node, length(path) AS depth
        ORDER BY depth
        """
        results = await neo4j_client.run_query(query, {"cin": company_cin})
        chain = []
        for row in results:
            node = dict(row["node"]) if row.get("node") else {}
            chain.append({
                "entity_name": node.get("name", "Unknown"),
                "entity_type": node.get("object_type", "unknown"),
                "depth": row.get("depth", 0),
                "isOffshore": node.get("isOffshore", False),
                "properties": node,
            })
        return chain

    async def delete_node(self, object_type: str, primary_key: str) -> None:
        label = LABEL_MAP.get(object_type.lower(), object_type.capitalize())
        pk_field = PK_FIELD_MAP.get(object_type.lower(), "id")
        await neo4j_client.run_write(
            f"MATCH (n:{label} {{{pk_field}: $pk}}) DETACH DELETE n",
            {"pk": primary_key},
        )
