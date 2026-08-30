"""PostgreSQL-only search and bounded relationship traversal for focused mode."""
from sqlalchemy import text
from fastapi import HTTPException
from core.database import AsyncSessionLocal


async def search(q, size, client_id, object_types=None, filters=None):
    filters = filters or {}
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT object_type, primary_key, properties FROM ontology_objects
            WHERE NOT is_deleted AND client_id IN (:tenant, 'PLATFORM_GLOBAL')
              AND (strpos(lower(primary_key), lower(:q)) > 0
                   OR strpos(lower(COALESCE(properties->>'name','')), lower(:q)) > 0)
            ORDER BY object_type, primary_key LIMIT 5001
        """), {"tenant": client_id, "q": q})
        rows = result.fetchall()
    if len(rows) > 5000:
        raise HTTPException(422, "Search too broad; refine your query")
    hits = []
    for row in rows:
        p = row.properties
        if object_types and row.object_type not in object_types:
            continue
        if any(p.get(k) != v for k, v in filters.items() if k != "riskScore_min"):
            continue
        if "riskScore_min" in filters and (p.get("riskScore") is None or p["riskScore"] < filters["riskScore_min"]):
            continue
        hits.append({"entityType": row.object_type, "entityId": row.primary_key, "properties": p})
    return hits[:size]


async def network(kind, key, depth, client_id):
    async with AsyncSessionLocal() as db:
        objects = (await db.execute(text("""
            SELECT object_type, primary_key, properties FROM ontology_objects
            WHERE NOT is_deleted AND client_id IN (:tenant, 'PLATFORM_GLOBAL')
            ORDER BY CASE WHEN client_id=:tenant THEN 0 ELSE 1 END LIMIT 5001
        """), {"tenant": client_id})).fetchall()
        links = (await db.execute(text("""
            SELECT * FROM ontology_links
            WHERE client_id IN (:tenant, 'PLATFORM_GLOBAL') LIMIT 10001
        """), {"tenant": client_id})).fetchall()
    if len(objects) > 5000 or len(links) > 10000:
        raise HTTPException(422, "Focused graph limit exceeded (5000 entities / 10000 relationships)")
    nodes = {}
    for r in objects:
        nodes.setdefault((r.object_type, r.primary_key),
                         {**r.properties, "entityId": r.primary_key, "object_type": r.object_type})
    root = (kind, key)
    if root not in nodes:
        raise HTTPException(404, "Entity not found")
    edges = {}
    for r in links:
        src, dst = (r.source_type, r.source_id), (r.target_type, r.target_id)
        if src in nodes and dst in nodes:
            edges[(src, dst, r.link_type)] = {
                "sourceLabel": r.source_type, "sourcePK": r.source_id,
                "targetLabel": r.target_type, "targetPK": r.target_id,
                "type": r.link_type, "properties": r.properties, "isInferred": r.is_inferred,
            }
    reached = {root}
    for _ in range(depth):
        addition = set()
        for src, dst, _ in edges:
            if src in reached: addition.add(dst)
            if dst in reached: addition.add(src)
        reached.update(addition)
    return {"nodes": [nodes[k] for k in sorted(reached)],
            "edges": [e for (s, t, _), e in edges.items() if s in reached and t in reached],
            "depth": depth, "storage": "postgresql"}
