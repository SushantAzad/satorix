from core.neo4j_client import neo4j_client
import logging

logger = logging.getLogger(__name__)


class InfluenceScorer:
    async def compute_centrality(self, object_type: str, primary_key: str) -> dict:
        pk_field = {"company": "cin", "director": "din"}.get(object_type.lower(), "id")
        label = object_type.capitalize()
        results = await neo4j_client.run_query(
            f"""
            MATCH (n:{label} {{{pk_field}: $pk}})-[r]-(other)
            RETURN count(r) AS degree_centrality,
                   count(DISTINCT other) AS unique_neighbors,
                   count(DISTINCT type(r)) AS relationship_types
            """,
            {"pk": primary_key},
        )
        if results:
            row = results[0]
            degree = row.get("degree_centrality", 0)
            return {
                "degree_centrality": degree,
                "unique_neighbors": row.get("unique_neighbors", 0),
                "relationship_types": row.get("relationship_types", 0),
                "influence_percentile": min(100, degree * 5),
            }
        return {"degree_centrality": 0, "unique_neighbors": 0, "relationship_types": 0, "influence_percentile": 0}


influence_scorer = InfluenceScorer()
