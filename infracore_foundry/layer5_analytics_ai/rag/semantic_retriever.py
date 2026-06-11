"""
SemanticRetriever — given a natural-language query, retrieve the most relevant
document chunks from pgvector for a specific entity (or globally).

Used by the GraphIntelligenceAgent to ground LLM responses in actual documents.
Falls back to keyword-based full-text search when embeddings are not available.
"""
import logging
from typing import Optional

from core.database import get_pool
from rag.document_embedder import _get_embedding

logger = logging.getLogger(__name__)


async def retrieve(
    query: str,
    entity_ref_id: Optional[str] = None,
    entity_ref_type: str = "company",
    top_k: int = 5,
    doc_types: Optional[list[str]] = None,
) -> list[dict]:
    """
    Retrieve the top-k most relevant document chunks for the given query.

    Returns a list of dicts:
      {"doc_id", "chunk_index", "chunk_text", "doc_type", "similarity"}
    """
    pool = get_pool()
    results: list[dict] = []

    query_embedding = await _get_embedding(query)

    try:
        async with pool.acquire() as conn:
            # Check if table and extension exist
            table_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='l5_document_embeddings')"
            )
            if not table_exists:
                logger.info("l5_document_embeddings table not yet created — no documents indexed")
                return []

            params: list = []
            conditions: list[str] = []

            if entity_ref_id:
                params.append(entity_ref_id)
                conditions.append(f"entity_ref_id = ${len(params)}")
            if doc_types:
                params.append(doc_types)
                conditions.append(f"doc_type = ANY(${len(params)})")

            where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            if query_embedding is not None:
                # Vector similarity search (cosine distance via pgvector <=>)
                params.append(str(query_embedding))
                rows = await conn.fetch(
                    f"""
                    SELECT doc_id, chunk_index, chunk_text, doc_type,
                           1 - (embedding <=> ${len(params)}::vector) AS similarity
                    FROM l5_document_embeddings
                    {where_clause}
                      {"AND" if where_clause else "WHERE"} embedding IS NOT NULL
                    ORDER BY embedding <=> ${len(params)}::vector
                    LIMIT {top_k}
                    """,
                    *params,
                )
            else:
                # Fallback: full-text search using PostgreSQL ts_rank
                params.append(query)
                rows = await conn.fetch(
                    f"""
                    SELECT doc_id, chunk_index, chunk_text, doc_type,
                           ts_rank(to_tsvector('english', chunk_text),
                                   plainto_tsquery('english', ${len(params)})) AS similarity
                    FROM l5_document_embeddings
                    {where_clause}
                    ORDER BY similarity DESC
                    LIMIT {top_k}
                    """,
                    *params,
                )

            for row in rows:
                results.append({
                    "doc_id": row["doc_id"],
                    "chunk_index": row["chunk_index"],
                    "chunk_text": row["chunk_text"],
                    "doc_type": row["doc_type"],
                    "similarity": float(row["similarity"] or 0),
                })

    except Exception as exc:
        logger.warning("SemanticRetriever failed for query='%s': %s", query[:80], exc)

    return results


async def build_rag_context(
    query: str,
    entity_ref_id: Optional[str] = None,
    top_k: int = 4,
    max_chars: int = 3000,
) -> str:
    """
    Build a formatted context block from retrieved document chunks.
    Used as additional context in LLM prompts.
    """
    chunks = await retrieve(query, entity_ref_id=entity_ref_id, top_k=top_k)
    if not chunks:
        return ""

    lines = ["[Retrieved Document Context]"]
    total_chars = 0
    for i, chunk in enumerate(chunks):
        snippet = chunk["chunk_text"]
        if total_chars + len(snippet) > max_chars:
            snippet = snippet[:max_chars - total_chars]
        lines.append(f"\n[Source {i+1} | {chunk['doc_type']} | relevance={chunk['similarity']:.2f}]")
        lines.append(snippet)
        total_chars += len(snippet)
        if total_chars >= max_chars:
            break

    return "\n".join(lines)
