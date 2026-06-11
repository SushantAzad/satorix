from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase

# Document types meaningful for medium-enterprise intelligence
VALID_DOC_TYPES = {
    "annual_report",
    "board_minutes",
    "regulatory_filing",
    "court_order",
    "contract",
    "audit_report",
    "credit_rating_report",
    "press_release",
    "mca_filing",
    "sebi_order",
    "other",
}


class Document(OntologyObjectBase):
    """
    A document associated with a corporate entity.
    Serves as the anchor for the RAG pipeline — chunk text is indexed
    separately in pgvector (l5_document_embeddings table).
    """

    doc_id: str                          # UUID or deterministic hash
    doc_type: str = "other"             # one of VALID_DOC_TYPES
    title: str
    filing_date: Optional[datetime] = None

    # Entity this document belongs to
    entity_ref_type: str = "company"    # company | director | project
    entity_ref_id: str = ""             # CIN / DIN / projectId

    # Content
    content_text: Optional[str] = None  # raw text (may be large)
    summary: Optional[str] = None       # LLM-generated summary
    file_path: Optional[str] = None     # MinIO path for original file
    page_count: Optional[int] = None
    language: str = "en"

    # RAG status
    is_embedded: bool = False           # True once indexed in pgvector
    chunk_count: Optional[int] = None

    # Source
    source: Optional[str] = None        # connector_id or system

    def primary_key_value(self) -> str:
        return self.doc_id

    def compute_data_quality_score(self) -> float:
        critical = ["doc_id", "title", "doc_type", "entity_ref_id", "filing_date"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "document"
        display_name = "Document"
        plural_name = "Documents"
        description = "A regulatory filing, annual report, or strategic document"
        primary_key_field = "doc_id"
        critical_properties = ["doc_id", "title", "doc_type", "entity_ref_id"]


DOCUMENT_DEFINITION = {
    "api_name": "document",
    "display_name": "Document",
    "plural_name": "Documents",
    "description": "A regulatory filing, annual report, contract, or strategic document linked to a corporate entity",
    "primary_key_field": "doc_id",
    "properties": {
        "doc_id":          {"type": "str", "required": True, "immutable": True},
        "doc_type":        {"type": "str"},
        "title":           {"type": "str", "required": True},
        "filing_date":     {"type": "datetime"},
        "entity_ref_type": {"type": "str"},
        "entity_ref_id":   {"type": "str"},
        "content_text":    {"type": "str"},
        "summary":         {"type": "str"},
        "file_path":       {"type": "str"},
        "page_count":      {"type": "int"},
        "language":        {"type": "str"},
        "is_embedded":     {"type": "bool"},
        "chunk_count":     {"type": "int"},
        "source":          {"type": "str"},
    },
    "interfaces": ["TemporalEntity"],
}
