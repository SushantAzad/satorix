from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
from core.database import get_db
from schema_registry.object_type_registry import object_type_registry
from schema_registry.link_type_registry import link_type_registry
from schema_registry.version_manager import version_manager

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/object-types")
async def list_object_types(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    types = await object_type_registry.get_all(db)
    return {
        "count": len(types),
        "object_types": [
            {
                "api_name": t.api_name,
                "display_name": t.display_name,
                "plural_name": t.plural_name,
                "description": t.description,
                "primary_key_field": t.primary_key_field,
                "interfaces": t.interfaces,
            }
            for t in types
        ],
    }


@router.get("/object-types/{api_name}")
async def get_object_type(api_name: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    obj_type = await object_type_registry.get(db, api_name)
    if not obj_type:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Object type '{api_name}' not found")
    return {
        "api_name": obj_type.api_name,
        "display_name": obj_type.display_name,
        "plural_name": obj_type.plural_name,
        "description": obj_type.description,
        "primary_key_field": obj_type.primary_key_field,
        "properties": obj_type.properties,
        "interfaces": obj_type.interfaces,
        "datasource_mapping": obj_type.datasource_mapping,
        "version": obj_type.version,
    }


@router.get("/link-types")
async def list_link_types(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    links = await link_type_registry.get_all(db)
    return {
        "count": len(links),
        "link_types": [
            {
                "api_name": lt.api_name,
                "display_name": lt.display_name,
                "source_object_type": lt.source_object_type,
                "target_object_type": lt.target_object_type,
                "is_inferred": lt.is_inferred,
                "cardinality": lt.cardinality,
            }
            for lt in links
        ],
    }


@router.get("/version")
async def get_schema_version(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    version = await version_manager.get_current_version(db)
    changelog = await version_manager.get_changelog(db)
    return {"current_version": version, "changelog": changelog}


@router.post("/object-types")
async def create_object_type(
    definition: dict[str, Any],
    actor_role: str = Query(default="ontology_designer"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if actor_role not in ("ontology_designer", "platform_administrator"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Only ONTOLOGY_DESIGNER can create object types")
    obj = await object_type_registry.upsert(db, definition)
    await version_manager.bump_minor(db, f"Added object type: {definition.get('api_name')}", actor_role)
    return {"success": True, "api_name": obj.api_name}
