from intelligence.risk_scoring.group_scorer import group_scorer, GroupRiskAssessment


async def computeGroupRiskScore(company_cin: str) -> GroupRiskAssessment:
    return await group_scorer.compute_group_risk(company_cin)
