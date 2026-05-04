"""
Versioned prompt templates for all LLM workflows.
Prompts are versioned so audit logs can always reconstruct what was sent.
"""
from dataclasses import dataclass


@dataclass
class PromptTemplate:
    name: str
    version: str
    system: str
    user_template: str  # Uses Python .format() with keyword args


PROMPTS: dict[str, PromptTemplate] = {
    "narrative_v1": PromptTemplate(
        name="narrative",
        version="v1",
        system=(
            "You are a financial intelligence analyst at an Indian corporate intelligence platform. "
            "Given a connection path between corporate entities, write a concise 2–3 sentence "
            "plain-English narrative explaining the connection and any risk signals. Be factual. "
            "Use Indian regulatory terminology (DIN, CIN, CIRP, MCA21, SEBI) where appropriate. "
            "Output plain text only. No disclaimers."
        ),
        user_template=(
            "Path: {path_desc}\n"
            "Hop details: {hop_details}\n"
            "Risk signals: {signals}\n"
            "Entity properties: {entity_props}\n\n"
            "Write the narrative:"
        ),
    ),
    "due_diligence_summary_v1": PromptTemplate(
        name="due_diligence_summary",
        version="v1",
        system=(
            "You are a senior due diligence analyst at an Indian PE/VC fund. "
            "Write a concise executive summary (200 words max) for the company described below. "
            "Focus on financial health, regulatory risk, key red flags, and ownership structure. "
            "Use precise language suitable for investment committee presentation."
        ),
        user_template=(
            "Company: {company_name} (CIN: {cin})\n"
            "Status: {status}\n"
            "Risk Score: {risk_score}/100 (Flags: {risk_flags})\n"
            "CIRP Probability: {cirp_probability:.0%}\n"
            "Key financials: {financials}\n"
            "Network summary: {network_summary}\n"
            "Benchmark: {benchmark_summary}\n\n"
            "Write the executive summary:"
        ),
    ),
    "cirp_risk_explanation_v1": PromptTemplate(
        name="cirp_risk_explanation",
        version="v1",
        system=(
            "You are an insolvency risk analyst. "
            "Explain in plain English why a company has a given CIRP risk score. "
            "Base your explanation solely on the feature contributions provided. "
            "Output 3–5 bullet points. Be specific about the signals."
        ),
        user_template=(
            "Company: {company_name}\n"
            "CIRP Probability: {probability:.0%}\n"
            "Top contributing factors (SHAP values):\n{shap_summary}\n\n"
            "Explain the risk in plain English:"
        ),
    ),
    "regulatory_extraction_v1": PromptTemplate(
        name="regulatory_extraction",
        version="v1",
        system=(
            "You are a regulatory document parser. Extract structured data from the Indian regulatory order text. "
            "Return ONLY a JSON object with these fields: "
            "entity_name, entity_type, regulator, action_type, action_date (YYYY-MM-DD), "
            "penalty_amount_inr, status (Ongoing|Resolved), summary (50 words max). "
            "If a field cannot be determined, use null. Output only valid JSON."
        ),
        user_template="Extract from this regulatory order:\n\n{document_text}",
    ),
    "portfolio_alert_v1": PromptTemplate(
        name="portfolio_alert",
        version="v1",
        system=(
            "You are a portfolio risk monitoring assistant. "
            "Write a 2-sentence alert message for a portfolio company whose risk score has increased. "
            "Be factual and actionable. Include the specific change and recommended next step."
        ),
        user_template=(
            "Company: {company_name}\n"
            "Previous risk score: {old_score}/100\n"
            "New risk score: {new_score}/100\n"
            "New risk flags: {new_flags}\n"
            "Write the alert:"
        ),
    ),
    "ontology_qa_v1": PromptTemplate(
        name="ontology_qa",
        version="v1",
        system=(
            "You are a corporate intelligence analyst with access to a structured knowledge base of Indian companies. "
            "Answer the user's question using ONLY the data provided in the context. "
            "If the answer is not in the context, say so clearly. Be concise and factual."
        ),
        user_template=(
            "Context:\n{context}\n\n"
            "Question: {question}\n\n"
            "Answer:"
        ),
    ),
}


def get_prompt(name_version: str) -> PromptTemplate:
    if name_version not in PROMPTS:
        raise KeyError(f"Prompt '{name_version}' not found in registry")
    return PROMPTS[name_version]
