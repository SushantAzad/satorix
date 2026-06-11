"""
SubgraphTemplates — pre-defined extraction templates for common intelligence patterns.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SubgraphTemplate:
    name: str
    description: str
    hops: int
    node_types: list[str]
    edge_types: list[str]
    filters: dict


TEMPLATES: dict[str, SubgraphTemplate] = {
    "due_diligence": SubgraphTemplate(
        name="due_diligence",
        description="Full corporate network for due diligence — directors, subsidiaries, addresses, legal cases",
        hops=3,
        node_types=["Company", "Director", "Address", "LegalCase", "RegulatoryAction"],
        edge_types=["DIRECTED", "OWNS", "SUBSIDIARY_OF", "REGISTERED_AT", "HAS_LEGAL_CASE", "HAS_REGULATORY_ACTION"],
        filters={},
    ),
    "ownership_chain": SubgraphTemplate(
        name="ownership_chain",
        description="Beneficial ownership chain — upstream and downstream holding structure",
        hops=5,
        node_types=["Company", "Director"],
        edge_types=["OWNS", "SUBSIDIARY_OF", "COMMON_BENEFICIAL_OWNER"],
        filters={},
    ),
    "director_network": SubgraphTemplate(
        name="director_network",
        description="All companies connected through shared directors",
        hops=2,
        node_types=["Company", "Director"],
        edge_types=["DIRECTED", "SHARES_DIRECTOR_WITH"],
        filters={},
    ),
    "regulatory_exposure": SubgraphTemplate(
        name="regulatory_exposure",
        description="Regulatory and legal risk neighborhood",
        hops=2,
        node_types=["Company", "Director", "RegulatoryAction", "LegalCase", "GovernmentEntity"],
        edge_types=["HAS_REGULATORY_ACTION", "HAS_LEGAL_CASE", "DIRECTED"],
        filters={},
    ),
    "address_cluster": SubgraphTemplate(
        name="address_cluster",
        description="All entities at the same address — shell company detection",
        hops=1,
        node_types=["Company", "Director", "Address"],
        edge_types=["REGISTERED_AT", "SHARES_ADDRESS_WITH"],
        filters={},
    ),
}


def get_template(name: str) -> Optional[SubgraphTemplate]:
    return TEMPLATES.get(name)


def list_templates() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "hops": t.hops}
        for t in TEMPLATES.values()
    ]
