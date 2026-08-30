"""Small local uploads through the existing ontology write funnel."""
import os
from sqlalchemy import text
from core.database import AsyncSessionLocal
from storage.object_data_funnel import object_data_funnel
from shared.csv_import import FIELDS, ID


async def process_import(body, client_id):
    if not client_id or client_id == "PLATFORM_GLOBAL":
        raise ValueError("An explicit private tenant is required")
    if os.getenv("LOCAL_SAFE_MODE", "true").lower() != "false" and os.getenv("DEVELOPMENT_MODE") != "true":
        raise PermissionError("Imports require Development or Unrestricted mode")
    kind, rows = body.get("kind"), body.get("rows", [])
    if kind not in FIELDS or not 1 <= len(rows) <= 200:
        raise ValueError("Unsupported kind or row count")
    commit = body.get("commit") is True
    async with AsyncSessionLocal() as db:
        # Serialize import requests per tenant, including concurrent previews.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                         {"key": "csv-import:" + client_id})
        async def existing(kind, key):
            r = await db.execute(text("""
                SELECT properties FROM ontology_objects WHERE object_type=:kind
                  AND primary_key=:key AND client_id=:tenant AND is_deleted=FALSE
            """), dict(kind=kind, key=key, tenant=client_id))
            return r.scalar()
        errors, prepared = [], []
        for row in rows:
            data = row["data"]
            if set(data) - set(FIELDS[kind]):
                raise ValueError("Unsupported fields")
            for field, required in FIELDS[kind].items():
                value = data.get(field, "")
                if not isinstance(value, str) or len(value) > 1000 or (required and not value):
                    raise ValueError("Invalid field")
                if (field == "id" or field.endswith("_id")) and not ID.fullmatch(value):
                    raise ValueError("Invalid identifier")
            if kind == "directorship":
                director = await existing("director", data["director_id"])
                company = await existing("company", data["company_id"])
                if director is None or company is None:
                    errors.append({"row": row["row"], "message": "Referenced director/company not found in your tenant; import entities first"})
                prepared.append((row, None))
            else:
                old = await existing(kind, data["id"])
                prepared.append((row, old))
        if not commit or errors:
            return {"status": "invalid" if errors else "ready", "errors": errors,
                    "rows": len(rows), "existing_entities": sum(old is not None for _, old in prepared)}
        results = []
        for row, old in prepared:
            data = row["data"]
            provenance = {"importSource": body["source"], "importFileSHA256": body["sha256"],
                          "importRow": row["row"]}
            if kind == "directorship":
                props = {**provenance}
                if data.get("appointed_date"):
                    props["appointedDate"] = data["appointed_date"]
                result = await object_data_funnel.write_link(
                    "DIRECTED", "director", data["director_id"], "company", data["company_id"],
                    props, actor=body["actor"], client_id=client_id)
                outcome = "upserted"
            else:
                props = {**(old or {}), **{k: v for k, v in data.items() if k != "id" and v},
                         **provenance, ("cin" if kind == "company" else "din"): data["id"]}
                if old is None:
                    props["synthetic"] = body.get("synthetic", False)
                result = await object_data_funnel.write_object(
                    kind, props, source=body["source"], actor=body["actor"], client_id=client_id)
                outcome = "created" if old is None else ("updated" if result.changes else "unchanged")
            results.append({"row": row["row"], "status": outcome if result.success else "failed",
                            "id": result.object_id})
        failed = sum(r["status"] == "failed" for r in results)
        return {"status": "partial" if failed else "completed", "results": results,
                "accepted": len(results) - failed, "failed": failed,
                "note": ("Rows commit individually. Search and relationships read directly from PostgreSQL."
                         if os.getenv("SATORIX_FOCUSED") == "true" else
                         "Rows commit individually. Search/graph projection failures may require reconciliation; successful storage is not proof of index visibility.")}
