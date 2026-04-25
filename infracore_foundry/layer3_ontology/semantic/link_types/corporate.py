"""Corporate relationship link type definitions."""

DIRECTED_DEFINITION = {
    "api_name": "DIRECTED",
    "display_name": "Directed",
    "source_object_type": "director",
    "target_object_type": "company",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A director serves on the board of a company",
    "properties": [
        {"name": "appointedDate", "type": "IndianDate_Type", "required": True},
        {"name": "cessationDate", "type": "IndianDate_Type"},
        {"name": "designation", "type": "str"},
        {"name": "isCurrent", "type": "bool", "derived": True},
        {"name": "appointingBody", "type": "str"},
    ],
}

OWNS_DEFINITION = {
    "api_name": "OWNS",
    "display_name": "Owns",
    "source_object_type": "company",
    "target_object_type": "company",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A company owns a percentage of another company",
    "properties": [
        {"name": "percentageHeld", "type": "float"},
        {"name": "holdingType", "type": "str"},
        {"name": "asOfDate", "type": "IndianDate_Type"},
        {"name": "votingRights", "type": "float"},
    ],
}

SUBSIDIARY_OF_DEFINITION = {
    "api_name": "SUBSIDIARY_OF",
    "display_name": "Subsidiary Of",
    "source_object_type": "company",
    "target_object_type": "company",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-one",
    "description": "A company is a subsidiary of another company",
    "properties": [
        {"name": "percentageOwned", "type": "float"},
        {"name": "effectiveDate", "type": "IndianDate_Type"},
    ],
}

REGISTERED_AT_DEFINITION = {
    "api_name": "REGISTERED_AT",
    "display_name": "Registered At",
    "source_object_type": "company",
    "target_object_type": "address",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-one",
    "description": "A company is registered at an address",
    "properties": [
        {"name": "registrationType", "type": "str"},
        {"name": "since", "type": "IndianDate_Type"},
    ],
}

SHARES_DIRECTOR_WITH_DEFINITION = {
    "api_name": "SHARES_DIRECTOR_WITH",
    "display_name": "Shares Director With",
    "source_object_type": "company",
    "target_object_type": "company",
    "is_directed": False,
    "is_inferred": True,
    "inference_rule": "infer_shares_director_with",
    "cardinality": "many-to-many",
    "description": "Two companies share a common director",
    "properties": [
        {"name": "sharedDirectorDin", "type": "str"},
        {"name": "sharedDirectorName", "type": "str"},
        {"name": "overlapPeriod", "type": "str"},
        {"name": "inferredBy", "type": "str"},
        {"name": "inferenceConfidence", "type": "float"},
    ],
}

SHARES_ADDRESS_WITH_DEFINITION = {
    "api_name": "SHARES_ADDRESS_WITH",
    "display_name": "Shares Address With",
    "source_object_type": "company",
    "target_object_type": "company",
    "is_directed": False,
    "is_inferred": True,
    "inference_rule": "infer_shares_address_with",
    "cardinality": "many-to-many",
    "description": "Two companies share a registered address",
    "properties": [
        {"name": "sharedAddress", "type": "str"},
        {"name": "inferredBy", "type": "str"},
        {"name": "inferenceConfidence", "type": "float"},
    ],
}

COMMON_BENEFICIAL_OWNER_DEFINITION = {
    "api_name": "COMMON_BENEFICIAL_OWNER",
    "display_name": "Common Beneficial Owner",
    "source_object_type": "company",
    "target_object_type": "company",
    "is_directed": False,
    "is_inferred": True,
    "inference_rule": "infer_common_beneficial_owner",
    "cardinality": "many-to-many",
    "description": "Two companies share the same ultimate beneficial owner",
    "properties": [
        {"name": "commonOwnerName", "type": "str"},
        {"name": "inferenceConfidence", "type": "float"},
        {"name": "inferredBy", "type": "str"},
    ],
}

HAS_EVENT_DEFINITION = {
    "api_name": "HAS_EVENT",
    "display_name": "Has Event",
    "source_object_type": "company",
    "target_object_type": "event",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "one-to-many",
    "description": "A company has an associated event",
    "properties": [],
}

ALL_CORPORATE_LINKS = [
    DIRECTED_DEFINITION,
    OWNS_DEFINITION,
    SUBSIDIARY_OF_DEFINITION,
    REGISTERED_AT_DEFINITION,
    SHARES_DIRECTOR_WITH_DEFINITION,
    SHARES_ADDRESS_WITH_DEFINITION,
    COMMON_BENEFICIAL_OWNER_DEFINITION,
    HAS_EVENT_DEFINITION,
]
