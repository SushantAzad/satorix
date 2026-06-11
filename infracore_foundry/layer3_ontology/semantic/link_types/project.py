"""Project relationship link type definitions."""

OWNS_PROJECT_DEFINITION = {
    "api_name": "OWNS_PROJECT",
    "display_name": "Owns Project",
    "source_object_type": "company",
    "target_object_type": "project",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A company owns or has a stake in an infrastructure project",
    "properties": [
        {"name": "ownershipType", "type": "str"},
        {"name": "percentageOwned", "type": "float"},
        {"name": "effectiveDate", "type": "IndianDate_Type"},
    ],
}

CONTRACTS_WITH_DEFINITION = {
    "api_name": "CONTRACTS_WITH",
    "display_name": "Contracts With",
    "source_object_type": "company",
    "target_object_type": "government_entity",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A company has a contract with a government entity",
    "properties": [
        {"name": "contractType", "type": "str"},
        {"name": "contractDate", "type": "IndianDate_Type"},
        {"name": "contractValue", "type": "float"},
    ],
}

ALL_PROJECT_LINKS = [
    OWNS_PROJECT_DEFINITION,
    CONTRACTS_WITH_DEFINITION,
]
