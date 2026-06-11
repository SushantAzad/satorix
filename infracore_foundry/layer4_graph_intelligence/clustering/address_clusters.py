"""
AddressClusterDetector — groups entities sharing a canonical address.
Uses fuzzy matching on address strings when exact match fails.
This is the Layer 4 read-only analysis pass; canonical address normalization
(the write path) lives in Layer 2.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from rapidfuzz import fuzz

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


class AddressClusterDetector:
    SIMILARITY_THRESHOLD = 85  # rapidfuzz ratio
    CLUSTER_TYPE = "address"

    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running address cluster detection")
        raw_addresses = await self._load_addresses()

        clusters: dict[str, list[dict]] = {}
        canonical_map: dict[str, str] = {}  # address_id → canonical

        for addr in raw_addresses:
            addr_str = addr.get("addressString", "")
            assigned = False
            for canonical, members in clusters.items():
                rep = members[0].get("addressString", "")
                if fuzz.ratio(addr_str.lower(), rep.lower()) >= self.SIMILARITY_THRESHOLD:
                    members.append(addr)
                    canonical_map[addr["id"]] = canonical
                    assigned = True
                    break
            if not assigned:
                canonical_map[addr["id"]] = addr["id"]
                clusters[addr["id"]] = [addr]

        # Only persist clusters with >1 member (shared address = signal)
        multi_member = {c: m for c, m in clusters.items() if len(m) > 1}

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM l4_address_clusters")
            await conn.execute(
                "DELETE FROM l4_cluster_memberships WHERE cluster_type = $1",
                self.CLUSTER_TYPE,
            )
            for canonical_id, members in multi_member.items():
                cluster_id = f"addr-{hashlib.sha256(canonical_id.encode()).hexdigest()[:12]}"
                canonical_str = members[0].get("addressString", canonical_id)
                company_count = sum(1 for m in members if m.get("entityType") == "Company")
                director_count = sum(1 for m in members if m.get("entityType") == "Director")
                risk_signal = min(len(members) * 5.0, 50.0) + (10.0 if company_count > 5 else 0)

                await conn.execute(
                    """
                    INSERT INTO l4_address_clusters
                        (cluster_id, canonical_address, member_count, company_count,
                         director_count, risk_signal, computed_at, batch_run_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (cluster_id) DO UPDATE SET
                        member_count = EXCLUDED.member_count,
                        risk_signal = EXCLUDED.risk_signal,
                        computed_at = EXCLUDED.computed_at
                    """,
                    cluster_id, canonical_str, len(members), company_count,
                    director_count, risk_signal, datetime.now(timezone.utc), batch_run_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO l4_cluster_memberships
                        (entity_id, entity_type, cluster_id, cluster_type, membership_score, computed_at, batch_run_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (entity_id, entity_type, cluster_type) DO UPDATE SET
                        cluster_id = EXCLUDED.cluster_id, computed_at = EXCLUDED.computed_at
                    """,
                    [
                        (m["id"], m.get("entityType", "unknown"), cluster_id, self.CLUSTER_TYPE,
                         1.0, datetime.now(timezone.utc), batch_run_id)
                        for m in members
                    ],
                )

        logger.info("Address clusters: %d multi-member clusters from %d addresses",
                    len(multi_member), len(raw_addresses))
        return {
            "cluster_type": self.CLUSTER_TYPE,
            "addresses_processed": len(raw_addresses),
            "clusters_found": len(multi_member),
        }

    async def _load_addresses(self) -> list[dict[str, Any]]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (a:Address)
                OPTIONAL MATCH (e)-[:REGISTERED_AT]->(a)
                RETURN a.id AS id,
                       a.address AS addressString,
                       labels(e)[0] AS entityType
                ORDER BY a.id
                LIMIT 50000
                """
            )
            return [dict(r) for r in await result.fetch(50000)]
