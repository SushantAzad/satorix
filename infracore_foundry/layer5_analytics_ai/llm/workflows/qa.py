"""
Natural-language Q&A on ontology data.
Builds context from L3/L4, then answers the question using the LLM.
"""
from llm.orchestrator import llm_orchestrator
from llm.context_builder import build_company_context, format_context_for_prompt


async def answer_question(
    question: str,
    context_cin: str | None = None,
    additional_context: dict | None = None,
    actor_id: str = "system",
    actor_role: str = "Analyst",
) -> str:
    ctx: dict = additional_context or {}
    objects_accessed: list[str] = []

    if context_cin:
        company_ctx = await build_company_context(context_cin, actor_role=actor_role)
        ctx.update(company_ctx)
        objects_accessed = ctx.pop("_objects_accessed", [f"Company:{context_cin}"])

    context_str = format_context_for_prompt(ctx)

    return await llm_orchestrator.run(
        prompt_key="ontology_qa_v1",
        format_kwargs={"context": context_str, "question": question},
        actor_id=actor_id,
        actor_role=actor_role,
        objects_accessed=objects_accessed,
        output_disposition="returned",
        max_tokens=512,
        workflow_type="qa",
    )
