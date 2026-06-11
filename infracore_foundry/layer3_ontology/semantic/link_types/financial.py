"""Financial link type definitions — relationships anchored to FinancialStatement and Document."""

HAS_FINANCIAL_STATEMENT_DEFINITION = {
    "api_name": "HAS_FINANCIAL_STATEMENT",
    "display_name": "Has Financial Statement",
    "source_object_type": "company",
    "target_object_type": "financial_statement",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "one-to-many",
    "description": "Company has a financial statement for a given fiscal period",
    "properties": [
        {"name": "financial_year", "type": "str"},
        {"name": "period", "type": "str"},
        {"name": "filing_date", "type": "datetime"},
    ],
}

HAS_DOCUMENT_DEFINITION = {
    "api_name": "HAS_DOCUMENT",
    "display_name": "Has Document",
    "source_object_type": "company",
    "target_object_type": "document",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "one-to-many",
    "description": "Company has an associated document (annual report, filing, contract, etc.)",
    "properties": [
        {"name": "doc_type", "type": "str"},
        {"name": "filing_date", "type": "datetime"},
    ],
}

DIRECTOR_HAS_DOCUMENT_DEFINITION = {
    "api_name": "DIRECTOR_HAS_DOCUMENT",
    "display_name": "Director Has Document",
    "source_object_type": "director",
    "target_object_type": "document",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "Director is referenced in or authored a document",
    "properties": [
        {"name": "doc_type", "type": "str"},
    ],
}

DOCUMENT_REFERENCES_DEFINITION = {
    "api_name": "DOCUMENT_REFERENCES",
    "display_name": "Document References",
    "source_object_type": "document",
    "target_object_type": "company",
    "is_directed": True,
    "is_inferred": True,
    "cardinality": "many-to-many",
    "description": "Document references a company entity (cross-entity citation)",
    "properties": [
        {"name": "reference_type", "type": "str"},
        {"name": "confidence", "type": "float"},
    ],
}

ALL_FINANCIAL_LINK_TYPES = [
    HAS_FINANCIAL_STATEMENT_DEFINITION,
    HAS_DOCUMENT_DEFINITION,
    DIRECTOR_HAS_DOCUMENT_DEFINITION,
    DOCUMENT_REFERENCES_DEFINITION,
]
