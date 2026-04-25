from typing import Any
import logging

logger = logging.getLogger(__name__)


class ProjectScorer:
    async def compute_score(self, project_id: str, project_props: dict[str, Any]) -> tuple[int, list[str]]:
        score = 0
        flags: list[str] = []

        status = str(project_props.get("status", "")).strip()
        if status == "Stressed":
            score += 40
            flags.append("PROJECT_STRESSED")

        delay_months = int(project_props.get("delayMonths", 0) or 0)
        if delay_months > 24:
            score += 20
            flags.append("SEVERE_DELAY")
        elif delay_months > 12:
            score += 10
            flags.append("MODERATE_DELAY")

        cost_overrun = float(project_props.get("costOverrunPercent", 0) or 0)
        if cost_overrun > 20:
            score += 15
            flags.append("COST_OVERRUN")

        land_status = str(project_props.get("landAcquisitionStatus", "")).lower()
        if land_status and "incomplete" in land_status:
            score += 15
            flags.append("LAND_ACQUISITION_INCOMPLETE")

        return min(score, 100), flags


project_scorer = ProjectScorer()
