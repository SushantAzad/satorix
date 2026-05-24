"""
DocumentEmbedder — chunks a Document's content and stores embeddings in pgvector.

Table: l5_document_embeddings
  doc_id TEXT, chunk_index INT, chunk_text TEXT,
  embedding VECTOR(1536), entity_ref_id TEXT, entity_ref_type TEXT,
  doc_type TEXT, created_at TIMESTAMPTZ

Uses the shared LLM provider's embed() method.
Falls back gracefully when pgvector is unavailable.
"""
import logging
import re
from typing import Optional

from core.database import get_pool
from core.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800       # characters
CHUNK_OVERLAP = 100    # characters
EMBED_DIM = 1536       # Anthropic text-embedding-3-small / Ollama nomic-embed-text


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by character count, breaking at sentence boundaries."""
    text = re.sub(r"\s+", " ", text).strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            # Try to break at the last sentence-ending punctuation in the window
            boundary = max(
                text.rfind(". ", start, end),
                text.rfind(".\n", start, end),
                text.rfind("? ", start, end),
                text.rfind("! ", start, end),
            )
            if boundary > start + size // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


async def _get_embedding(text: str) -> Optional[list[float]]:
    """Call the LLM provider's embed method."""
    try:
        from shared.llm.provider import get_llm_provider
        provider = get_llm_provider()
        if hasattr(provider, "embed"):
            return await provider.embed(text)
        # Fallback: Anthropic embeddings via raw API if provider doesn't have embed
        if settings.anthropic_api_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return resp.data[0].embedding
    except Exception as exc:
        logger.warning("Embedding call failed: %s", exc)
    return None


async def embed_document(doc_id: str, content_text: str, entity_ref_id: str,
                         entity_ref_type: str = "company", doc_type: str = "other") -> int:
    """
    Chunk and embed a document. Returns the number of chunks stored.
    Idempotent: deletes existing chunks for doc_id before re-inserting.
    """
    pool = get_pool()
    if not content_text or not content_text.strip():
        return 0

    chunks = _chunk_text(content_text)
    stored = 0

    try:
        async with pool.acquire() as conn:
            # Ensure pgvector extension and table exist
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS l5_document_embeddings (
                    doc_id TEXT NOT NULL,
                    chunk_index INT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding VECTOR(1536),
                    entity_ref_id TEXT,
                    entity_ref_type TEXT,
                    doc_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (doc_id, chunk_index)
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_embed_entity ON l5_document_embeddings(entity_ref_id)"
            )

            # Remove stale embeddings for this doc
            await conn.execute("DELETE FROM l5_document_embeddings WHERE doc_id = $1", doc_id)

            for idx, chunk in enumerate(chunks):
                embedding = await _get_embedding(chunk)
                if embedding is None:
                    # Store without embedding — still searchable via keyword
                    await conn.execute(
                        """INSERT INTO l5_document_embeddings
                           (doc_id, chunk_index, chunk_text, entity_ref_id, entity_ref_type, doc_type)
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        doc_id, idx, chunk, entity_ref_id, entity_ref_type, doc_type,
                    )
                else:
                    await conn.execute(
                        """INSERT INTO l5_document_embeddings
                           (doc_id, chunk_index, chunk_text, embedding, entity_ref_id, entity_ref_type, doc_type)
                           VALUES ($1, $2, $3, $4::vector, $5, $6, $7)""",
                        doc_id, idx, chunk, str(embedding), entity_ref_id, entity_ref_type, doc_type,
                    )
                stored += 1

    except Exception as exc:
        logger.error("embed_document failed for doc_id=%s: %s", doc_id, exc)

    return stored
