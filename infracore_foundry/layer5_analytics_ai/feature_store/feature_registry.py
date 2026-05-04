"""Defines all features for each entity type."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FeatureDef:
    name: str
    entity_type: str
    description: str
    dtype: str  # float | bool | int
    default: Optional[float] = None


COMPANY_FEATURES: list[FeatureDef] = [
    FeatureDef("director_count_current", "Company", "Current active directors", "int", 0.0),
    FeatureDef("director_offshore_ratio", "Company", "Offshore directors / total directors", "float", 0.0),
    FeatureDef("director_disqualified_count", "Company", "Directors with disqualification", "int", 0.0),
    FeatureDef("director_turnover_12m", "Company", "Director changes in last 12 months", "int", 0.0),
    FeatureDef("regulatory_action_count_12m", "Company", "Regulatory actions in last 12 months", "int", 0.0),
    FeatureDef("regulatory_action_ongoing", "Company", "Count of ongoing regulatory actions", "int", 0.0),
    FeatureDef("avg_project_delay_months", "Company", "Average project delay across owned projects", "float", 0.0),
    FeatureDef("project_count_stressed", "Company", "Count of stressed projects", "int", 0.0),
    FeatureDef("debt_equity_ratio", "Company", "Debt-to-equity ratio from latest filing", "float", None),
    FeatureDef("current_ratio", "Company", "Current ratio from latest filing", "float", None),
    FeatureDef("address_cluster_size", "Company", "Companies sharing registered address", "int", 1.0),
    FeatureDef("betweenness_centrality", "Company", "Neo4j betweenness centrality from L4", "float", 0.0),
    FeatureDef("louvain_cluster_risk_avg", "Company", "Average risk of Louvain cluster members", "float", 0.0),
    FeatureDef("days_since_last_filing", "Company", "Days since last MCA annual return", "float", 365.0),
    FeatureDef("revenue_trend_3y", "Company", "Slope of 3-year revenue series (normalised)", "float", 0.0),
    FeatureDef("layer3_risk_score", "Company", "Risk score from Layer 3 heuristic engine", "float", 0.0),
    FeatureDef("l4_precursor_score", "Company", "CIRP precursor score from Layer 4 rules", "float", 0.0),
    FeatureDef("is_under_cirp", "Company", "1 if company is currently under CIRP", "bool", 0.0),
    FeatureDef("has_legal_case", "Company", "1 if active legal case exists", "bool", 0.0),
    FeatureDef("total_project_value_cr", "Company", "Total project portfolio value in Cr INR", "float", 0.0),
]

PROJECT_FEATURES: list[FeatureDef] = [
    FeatureDef("delay_ratio", "Project", "delayMonths / expectedDurationMonths", "float", 0.0),
    FeatureDef("cost_overrun_ratio", "Project", "actualCost/budgetCost - 1", "float", 0.0),
    FeatureDef("owner_risk_score", "Project", "Parent company Layer3 risk score", "float", 0.0),
    FeatureDef("owner_cirp_active", "Project", "1 if owner company is under CIRP", "bool", 0.0),
    FeatureDef("contractor_historical_delays", "Project", "Avg delays across contractor projects", "float", 0.0),
    FeatureDef("land_acquisition_complete", "Project", "1 if land acquisition is complete", "bool", 0.0),
    FeatureDef("regulatory_disputes_count", "Project", "Active regulatory disputes on project", "int", 0.0),
    FeatureDef("sector_avg_delay", "Project", "Average delay months for this project type in India", "float", 0.0),
    FeatureDef("project_age_months", "Project", "Months since project start date", "float", 0.0),
    FeatureDef("expected_duration_months", "Project", "Originally planned duration in months", "float", 0.0),
]

ALL_FEATURES: list[FeatureDef] = COMPANY_FEATURES + PROJECT_FEATURES


def get_feature_names(entity_type: str) -> list[str]:
    return [f.name for f in ALL_FEATURES if f.entity_type == entity_type]


def get_feature_defaults(entity_type: str) -> dict[str, float]:
    return {f.name: (f.default or 0.0) for f in ALL_FEATURES if f.entity_type == entity_type}
