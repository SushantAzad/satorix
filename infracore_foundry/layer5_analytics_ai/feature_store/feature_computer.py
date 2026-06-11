"""
Computes all features for Company and Project entities by reading
Neo4j, PostgreSQL (L3 ontology_objects), and L4 pre-computed tables.
Called by the nightly Airflow DAG and on-demand for single entities.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.neo4j_client import neo4j_client
from core.database import get_pool
from core.config import settings
from feature_store.feature_registry import get_feature_defaults

logger = logging.getLogger(__name__)


class FeatureComputer:

    async def compute_company_features(self, cin: str) -> dict[str, float]:
        """Returns a flat dict of feature_name → float for one Company."""
        feats = get_feature_defaults("Company")

        await self._populate_neo4j_company_features(cin, feats)
        await self._populate_pg_company_features(cin, feats)
        await self._populate_l4_company_features(cin, feats)
        await self._populate_financial_statement_features(cin, feats)
        await self._populate_document_features(cin, feats)
        return feats

    async def compute_project_features(self, project_id: str) -> dict[str, float]:
        feats = get_feature_defaults("Project")
        await self._populate_neo4j_project_features(project_id, feats)
        await self._populate_pg_project_features(project_id, feats)
        return feats

    # ------------------------------------------------------------------ #
    #  Company — Neo4j                                                     #
    # ------------------------------------------------------------------ #

    async def _populate_neo4j_company_features(self, cin: str, feats: dict) -> None:
        try:
            rows = await neo4j_client.run_query(
                """
                MATCH (c:Company {cin: $cin})
                OPTIONAL MATCH (d:Director)-[:DIRECTED]->(c)
                OPTIONAL MATCH (c)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(peer:Company)
                OPTIONAL MATCH (c)-[:SUBJECT_OF]->(ra:RegulatoryAction)
                OPTIONAL MATCH (c)-[:OWNS_PROJECT]->(p:Project)
                OPTIONAL MATCH (c)-[:SUBJECT_OF]->(ip:InsolvencyProceeding)
                OPTIONAL MATCH (c)-[:HAS_LEGAL_CASE]->(lc:LegalCase)
                WITH c,
                     collect(DISTINCT d) AS directors,
                     count(DISTINCT peer) AS addr_cluster_size,
                     collect(DISTINCT ra) AS reg_actions,
                     collect(DISTINCT p) AS projects,
                     count(DISTINCT ip) AS cirp_count,
                     count(DISTINCT lc) AS legal_count
                RETURN
                    c.riskScore AS risk_score,
                    c.status AS status,
                    c.lastFilingDate AS last_filing_date,
                    size(directors) AS dir_count,
                    size([d IN directors WHERE d.isOffshore = true]) AS offshore_count,
                    size([d IN directors WHERE d.disqualificationStatus = 'Disqualified']) AS disq_count,
                    addr_cluster_size,
                    size([ra IN reg_actions WHERE ra.status = 'Ongoing']) AS ongoing_reg,
                    size(projects) AS proj_count,
                    size([p IN projects WHERE p.status = 'Stressed']) AS stressed_proj,
                    reduce(s=0, p IN projects | s + coalesce(toInteger(p.delayMonths), 0)) AS total_delay,
                    cirp_count,
                    legal_count
                """,
                {"cin": cin},
            )
            if not rows:
                return
            r = rows[0]

            dir_count = int(r.get("dir_count") or 0)
            feats["director_count_current"] = float(dir_count)
            offshore = int(r.get("offshore_count") or 0)
            feats["director_offshore_ratio"] = offshore / max(dir_count, 1)
            feats["director_disqualified_count"] = float(r.get("disq_count") or 0)
            feats["address_cluster_size"] = float(max(int(r.get("addr_cluster_size") or 1), 1))
            feats["regulatory_action_ongoing"] = float(r.get("ongoing_reg") or 0)
            proj_count = int(r.get("proj_count") or 0)
            feats["project_count_stressed"] = float(r.get("stressed_proj") or 0)
            total_delay = int(r.get("total_delay") or 0)
            feats["avg_project_delay_months"] = total_delay / max(proj_count, 1)
            feats["is_under_cirp"] = 1.0 if int(r.get("cirp_count") or 0) > 0 else 0.0
            feats["has_legal_case"] = 1.0 if int(r.get("legal_count") or 0) > 0 else 0.0
            feats["layer3_risk_score"] = float(r.get("risk_score") or 0)

            status = str(r.get("status") or "")
            if status == "UnderCIRP":
                feats["is_under_cirp"] = 1.0

            last_filing = r.get("last_filing_date")
            if last_filing:
                try:
                    if isinstance(last_filing, str):
                        filing_dt = datetime.fromisoformat(last_filing)
                    else:
                        filing_dt = last_filing
                    feats["days_since_last_filing"] = float(
                        (datetime.now(timezone.utc) - filing_dt.replace(tzinfo=timezone.utc)).days
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.warning("Neo4j company feature computation failed for %s: %s", cin, exc)

    async def _populate_neo4j_company_reg_12m(self, cin: str, feats: dict) -> None:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
            rows = await neo4j_client.run_query(
                """
                MATCH (c:Company {cin: $cin})-[:SUBJECT_OF]->(ra:RegulatoryAction)
                WHERE ra.date >= $cutoff
                RETURN count(ra) AS count
                """,
                {"cin": cin, "cutoff": cutoff},
            )
            if rows:
                feats["regulatory_action_count_12m"] = float(rows[0].get("count") or 0)
        except Exception as exc:
            logger.warning("Reg 12m query failed for %s: %s", cin, exc)

    # ------------------------------------------------------------------ #
    #  Company — PostgreSQL (ontology_objects + L4 tables)                #
    # ------------------------------------------------------------------ #

    async def _populate_pg_company_features(self, cin: str, feats: dict) -> None:
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT properties
                    FROM ontology_objects
                    WHERE object_type = 'company'
                      AND (properties->>'cin' = $1 OR primary_key = $1)
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    cin,
                )
                if row:
                    import json
                    props = row["properties"] if isinstance(row["properties"], dict) else json.loads(row["properties"] or "{}")
                    # Financial ratios stored in properties
                    if props.get("debtEquityRatio") is not None:
                        feats["debt_equity_ratio"] = float(props["debtEquityRatio"])
                    if props.get("currentRatio") is not None:
                        feats["current_ratio"] = float(props["currentRatio"])
                    if props.get("totalProjectValueCr") is not None:
                        feats["total_project_value_cr"] = float(props["totalProjectValueCr"])
        except Exception as exc:
            logger.warning("PG company feature computation failed for %s: %s", cin, exc)

    async def _populate_l4_company_features(self, cin: str, feats: dict) -> None:
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                # L4 influence scores
                influence_row = await conn.fetchrow(
                    "SELECT betweenness, composite_score FROM l4_influence_scores WHERE entity_id=$1 LIMIT 1",
                    cin,
                )
                if influence_row:
                    feats["betweenness_centrality"] = float(influence_row["betweenness"] or 0)

                # L4 precursor score
                precursor_row = await conn.fetchrow(
                    "SELECT cirp_risk_score FROM l4_precursor_assessments WHERE entity_id=$1 LIMIT 1",
                    cin,
                )
                if precursor_row:
                    feats["l4_precursor_score"] = float(precursor_row["cirp_risk_score"] or 0)

                # Average risk of Louvain cluster members
                cluster_row = await conn.fetchrow(
                    """
                    SELECT cm.cluster_id FROM l4_cluster_memberships cm
                    WHERE cm.entity_id=$1 AND cm.cluster_type='louvain' LIMIT 1
                    """,
                    cin,
                )
                if cluster_row:
                    cluster_id = cluster_row["cluster_id"]
                    avg_row = await conn.fetchrow(
                        """
                        SELECT avg(inf.composite_score) AS avg_risk
                        FROM l4_cluster_memberships cm
                        JOIN l4_influence_scores inf ON inf.entity_id = cm.entity_id
                        WHERE cm.cluster_id=$1 AND cm.cluster_type='louvain' AND cm.entity_id != $2
                        """,
                        cluster_id, cin,
                    )
                    if avg_row and avg_row["avg_risk"] is not None:
                        feats["louvain_cluster_risk_avg"] = float(avg_row["avg_risk"])
        except Exception as exc:
            logger.warning("L4 feature population failed for %s: %s", cin, exc)

    # ------------------------------------------------------------------ #
    #  Project features                                                    #
    # ------------------------------------------------------------------ #

    async def _populate_neo4j_project_features(self, project_id: str, feats: dict) -> None:
        try:
            rows = await neo4j_client.run_query(
                """
                MATCH (p:Project {projectId: $pid})
                OPTIONAL MATCH (c:Company)-[:OWNS_PROJECT]->(p)
                OPTIONAL MATCH (p)<-[:RELATES_TO]-(ra:RegulatoryAction {status: 'Ongoing'})
                RETURN
                    coalesce(p.delayMonths, 0) AS delay_months,
                    coalesce(p.expectedDurationMonths, 0) AS expected_duration,
                    coalesce(p.costOverrunPercent, 0) AS cost_overrun_pct,
                    p.landAcquisitionStatus AS land_status,
                    p.startDate AS start_date,
                    c.riskScore AS owner_risk,
                    c.status AS owner_status,
                    count(ra) AS dispute_count
                """,
                {"pid": project_id},
            )
            if not rows:
                return
            r = rows[0]
            delay = float(r.get("delay_months") or 0)
            expected = float(r.get("expected_duration") or 1)
            feats["delay_ratio"] = delay / max(expected, 1)
            cost_overrun_pct = float(r.get("cost_overrun_pct") or 0)
            feats["cost_overrun_ratio"] = cost_overrun_pct / 100.0
            feats["owner_risk_score"] = float(r.get("owner_risk") or 0)
            feats["owner_cirp_active"] = 1.0 if str(r.get("owner_status") or "") == "UnderCIRP" else 0.0
            feats["regulatory_disputes_count"] = float(r.get("dispute_count") or 0)
            feats["expected_duration_months"] = expected
            land = str(r.get("land_status") or "").lower()
            feats["land_acquisition_complete"] = 0.0 if any(w in land for w in ("incomplete", "pending", "disputed")) else 1.0
            start = r.get("start_date")
            if start:
                try:
                    if isinstance(start, str):
                        start_dt = datetime.fromisoformat(start)
                    else:
                        start_dt = start
                    feats["project_age_months"] = float(
                        (datetime.now(timezone.utc) - start_dt.replace(tzinfo=timezone.utc)).days / 30.44
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("Neo4j project feature computation failed for %s: %s", project_id, exc)

    async def _populate_pg_project_features(self, project_id: str, feats: dict) -> None:
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                import json
                row = await conn.fetchrow(
                    """
                    SELECT properties FROM ontology_objects
                    WHERE object_type = 'project'
                      AND (properties->>'projectId' = $1 OR primary_key = $1)
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    project_id,
                )
                if row:
                    props = row["properties"] if isinstance(row["properties"], dict) else json.loads(row["properties"] or "{}")
                    if props.get("sectorAvgDelayMonths") is not None:
                        feats["sector_avg_delay"] = float(props["sectorAvgDelayMonths"])
        except Exception as exc:
            logger.warning("PG project feature computation failed for %s: %s", project_id, exc)

    # ------------------------------------------------------------------ #
    #  Company — FinancialStatement features (Gap 2 + Gap 5)             #
    # ------------------------------------------------------------------ #

    async def _populate_financial_statement_features(self, cin: str, feats: dict) -> None:
        """Compute business intelligence features from FinancialStatement ontology objects."""
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                import json
                rows = await conn.fetch(
                    """
                    SELECT properties FROM ontology_objects
                    WHERE object_type = 'financial_statement'
                      AND properties->>'cin' = $1
                      AND properties->>'period' = 'annual'
                    ORDER BY properties->>'financial_year' DESC
                    LIMIT 5
                    """,
                    cin,
                )
                if not rows:
                    return

                statements = []
                for row in rows:
                    props = row["properties"] if isinstance(row["properties"], dict) else json.loads(row["properties"] or "{}")
                    statements.append(props)

                feats["financial_statement_years"] = float(len(statements))

                # Most recent statement
                latest = statements[0]
                if latest.get("revenue") is not None:
                    feats["revenue_latest_cr"] = float(latest["revenue"])
                if latest.get("total_debt") is not None:
                    feats["total_debt_latest_cr"] = float(latest["total_debt"])
                if latest.get("ebitda_margin_pct") is not None:
                    feats["ebitda_margin_latest"] = float(latest["ebitda_margin_pct"])
                if latest.get("debt_service_coverage") is not None:
                    feats["debt_service_coverage_latest"] = float(latest["debt_service_coverage"])
                if latest.get("debt_equity_ratio") is not None:
                    feats["debt_equity_ratio"] = float(latest["debt_equity_ratio"])
                if latest.get("current_ratio") is not None:
                    feats["current_ratio"] = float(latest["current_ratio"])

                # Working capital days (working_capital / (revenue / 365))
                wc = latest.get("working_capital")
                rev = latest.get("revenue")
                if wc is not None and rev and rev > 0:
                    feats["working_capital_days"] = round(float(wc) / (float(rev) / 365), 1)

                # Related-party transaction ratio
                rpt = latest.get("related_party_tx_value")
                if rpt is not None and rev and rev > 0:
                    feats["related_party_tx_ratio"] = round(float(rpt) / float(rev) * 100, 2)

                # Revenue CAGR over 3 years
                if len(statements) >= 3:
                    rev_latest = float(statements[0].get("revenue") or 0)
                    rev_oldest = float(statements[2].get("revenue") or 0)
                    if rev_oldest > 0 and rev_latest > 0:
                        cagr = ((rev_latest / rev_oldest) ** (1 / 2) - 1) * 100
                        feats["revenue_cagr_3y"] = round(cagr, 2)
                        feats["revenue_trend_3y"] = round(cagr / 100, 4)

        except Exception as exc:
            logger.warning("Financial statement feature computation failed for %s: %s", cin, exc)

    async def _populate_document_features(self, cin: str, feats: dict) -> None:
        """Count indexed documents for this entity."""
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT count(*) AS cnt FROM ontology_objects
                    WHERE object_type = 'document'
                      AND properties->>'entity_ref_id' = $1
                    """,
                    cin,
                )
                if row:
                    feats["document_count"] = float(row["cnt"] or 0)
        except Exception as exc:
            logger.warning("Document count feature computation failed for %s: %s", cin, exc)


feature_computer = FeatureComputer()
