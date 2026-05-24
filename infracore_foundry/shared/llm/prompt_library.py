"""
Satorix centralised prompt library.

All LLM prompts live here. Prompts are tuned to work with both
Anthropic (claude-sonnet-4-6) and smaller local Ollama models:
more explicit instructions, no assumed context, JSON-only outputs
for extraction tasks.
"""

SYSTEM_SATORIX_BASE = """
You are Satorix, an Indian corporate intelligence analyst.
You analyse Indian corporate entities using public data from MCA21,
SEBI, IBBI, RBI, and GeM portals.
You understand: CIN (Corporate Identification Number), DIN (Director
Identification Number), GSTIN, CIRP (Corporate Insolvency Resolution
Process), and Indian corporate governance patterns.
Always respond in English. Be precise and factual.
Do not speculate beyond what the provided data supports.
""".strip()

PROMPT_PATH_NARRATIVE = """
Given this connection path between two Indian corporate entities,
write a clear 2-3 sentence explanation of how they are connected
and why this connection matters for risk assessment.

Path data (JSON):
{path_json}

Write the explanation for a PE analyst or compliance officer.
Be specific about the relationship types and any risk implications.
""".strip()

PROMPT_ENTITY_SUMMARY = """
Given this Indian corporate entity data, write a 3-5 sentence
intelligence summary explaining:
1. What this entity is and what it does
2. The most significant risk signals present
3. Any unusual patterns that warrant attention

Entity data (JSON):
{entity_json}

Write for a PE analyst conducting due diligence.
""".strip()

PROMPT_EXTRACT_REGULATORY_ACTION = """
Extract structured information from this Indian regulatory document.

Return ONLY a valid JSON object with these exact fields:
{{
  "issuing_body": "SEBI | RBI | NHAI | NCLT | MCA | ED | Other",
  "action_type": "Show Cause Notice | Penalty Order | CIRP Admission | Director Disqualification | FEMA Investigation | Other",
  "action_date": "YYYY-MM-DD or null",
  "resolution_date": "YYYY-MM-DD or null",
  "monetary_amount_inr": null,
  "entity_names": ["list of company or individual names mentioned"],
  "violation_summary": "one sentence description of the violation",
  "status": "Ongoing | Resolved | Unknown"
}}

Do not include any explanation or markdown. Return only the JSON object.

Document text:
{document_text}
""".strip()

PROMPT_NL_QUERY = """
Convert this natural language question about Indian corporate entities
into a structured search specification.

Return ONLY a valid JSON object:
{{
  "entity_types": ["Company", "Director", "Project", "RegulatoryAction"],
  "filters": {{}},
  "search_text": "keywords to search",
  "network_depth": 1,
  "sort_by": "riskScore | name | date"
}}

Question: {question}
""".strip()

PROMPT_DUE_DILIGENCE_SECTION = """
Write the {section_name} section of a corporate due diligence report
for {entity_name}.

Data provided:
{section_data_json}

Requirements:
- Write 150-250 words
- Be factual and specific to the provided data
- Highlight the most significant findings
- Write for an investment committee audience
- Do not mention data sources by name
- Do not use bullet points — write in paragraph form
""".strip()
