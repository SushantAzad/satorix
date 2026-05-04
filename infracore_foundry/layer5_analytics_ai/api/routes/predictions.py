"""Model prediction endpoints."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from models.serving import model_server, MODEL_CIRP_PRECURSOR, MODEL_PROJECT_COMPLETION, MODEL_REGULATORY_LIKELIHOOD

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/cirp/{cin}")
async def predict_cirp(cin: str):
    result = await model_server.predict(MODEL_CIRP_PRECURSOR, "Company", cin)
    return result.to_dict()


@router.get("/project/{project_id}")
async def predict_project_completion(project_id: str):
    result = await model_server.predict(MODEL_PROJECT_COMPLETION, "Project", project_id)
    return result.to_dict()


@router.get("/regulatory/{cin}")
async def predict_regulatory_likelihood(cin: str):
    result = await model_server.predict(MODEL_REGULATORY_LIKELIHOOD, "Company", cin)
    return result.to_dict()


@router.get("/batch/cirp")
async def batch_predict_cirp(
    cins: list[str] = Query(..., description="List of company CINs"),
):
    results = []
    for cin in cins[:50]:
        result = await model_server.predict(MODEL_CIRP_PRECURSOR, "Company", cin, persist=False)
        results.append(result.to_dict())
    return {"predictions": results, "count": len(results)}
