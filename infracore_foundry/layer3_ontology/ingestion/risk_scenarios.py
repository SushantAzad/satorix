import os
from shared.fixture_operation import CLIENT_ID, require_runtime_guard, require_safe_mode
from shared.risk_scenarios import VERSION, build_risk_scenarios
from storage.object_data_funnel import object_data_funnel


async def load_risk_scenarios():
    require_safe_mode()
    require_runtime_guard()
    if os.environ.get("DEVELOPMENT_MODE") != "true":
        raise PermissionError("Risk scenarios require contained Development mode")
    objects, links = build_risk_scenarios()
    changed = 0
    for kind, data in objects:
        result = await object_data_funnel.write_object(kind, data, source=VERSION,
            actor="synthetic_scenario_loader", client_id=CLIENT_ID)
        if not result.success:
            raise RuntimeError("Scenario object write failed")
        changed += bool(result.changes)
    for link in links:
        result = await object_data_funnel.write_link(**link, actor="synthetic_scenario_loader", client_id=CLIENT_ID)
        if not result.success:
            raise RuntimeError("Scenario relationship write failed")
    return {"dataset": VERSION, "objects": len(objects), "relationships": len(links),
        "objects_changed": changed, "client_id": CLIENT_ID}
