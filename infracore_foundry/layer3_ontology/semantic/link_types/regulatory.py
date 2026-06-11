"""Regulatory relationship link type definitions."""

SUBJECT_OF_DEFINITION = {
    "api_name": "SUBJECT_OF",
    "display_name": "Subject Of",
    "source_object_type": "company",
    "target_object_type": "regulatory_action",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A company is subject to a regulatory action",
    "properties": [
        {"name": "role", "type": "str"},
        {"name": "noticeDate", "type": "IndianDate_Type"},
        {"name": "responseDeadline", "type": "IndianDate_Type"},
    ],
}

NAMED_IN_DEFINITION = {
    "api_name": "NAMED_IN",
    "display_name": "Named In",
    "source_object_type": "director",
    "target_object_type": "regulatory_action",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A director is named in a regulatory action",
    "properties": [
        {"name": "role", "type": "str"},
    ],
}

REGULATED_BY_DEFINITION = {
    "api_name": "REGULATED_BY",
    "display_name": "Regulated By",
    "source_object_type": "company",
    "target_object_type": "regulatory_body",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A company is regulated by a regulatory body",
    "properties": [],
}

UNDERGOING_CIRP_DEFINITION = {
    "api_name": "UNDERGOING_CIRP",
    "display_name": "Undergoing CIRP",
    "source_object_type": "company",
    "target_object_type": "insolvency_proceeding",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "one-to-one",
    "description": "A company is undergoing a CIRP insolvency proceeding",
    "properties": [],
}

PARTY_TO_DEFINITION = {
    "api_name": "PARTY_TO",
    "display_name": "Party To",
    "source_object_type": "company",
    "target_object_type": "legal_case",
    "is_directed": True,
    "is_inferred": False,
    "cardinality": "many-to-many",
    "description": "A company is a party to a legal case",
    "properties": [
        {"name": "role", "type": "str"},
    ],
}

REGULATORY_CONTAGION_RISK_DEFINITION = {
    "api_name": "REGULATORY_CONTAGION_RISK",
    "display_name": "Regulatory Contagion Risk",
    "source_object_type": "company",
    "target_object_type": "company",
    "is_directed": True,
    "is_inferred": True,
    "inference_rule": "infer_regulatory_contagion",
    "cardinality": "many-to-many",
    "description": "A CIRP company poses contagion risk to a connected company",
    "properties": [
        {"name": "riskType", "type": "str"},
        {"name": "severity", "type": "str"},
        {"name": "inferredBy", "type": "str"},
        {"name": "inferenceConfidence", "type": "float"},
    ],
}

ALL_REGULATORY_LINKS = [
    SUBJECT_OF_DEFINITION,
    NAMED_IN_DEFINITION,
    REGULATED_BY_DEFINITION,
    UNDERGOING_CIRP_DEFINITION,
    PARTY_TO_DEFINITION,
    REGULATORY_CONTAGION_RISK_DEFINITION,
]
