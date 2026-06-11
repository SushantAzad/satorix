"""
ModelServingEngine — loads champion model artifact and produces predictions
with SHAP explanations and confidence intervals.
"""
import io
import json
import logging
import pickle
from datetime import datetime, timezone
from typing import Optional

from core.database import get_pool
from core.config import settings
from feature_store.feature_store import get_latest_features
from feature_store.feature_registry import get_feature_names, get_feature_defaults
from models.registry import model_registry

logger = logging.getLogger(__name__)

# Model names used throughout Layer 5
MODEL_CIRP_PRECURSOR = "cirp_precursor"
MODEL_PROJECT_COMPLETION = "project_completion"
MODEL_REGULATORY_LIKELIHOOD = "regulatory_likelihood"
MODEL_ENTITY_SIMILARITY = "entity_similarity"
MODEL_FINANCIAL_TRAJECTORY = "financial_trajectory"


class PredictionResult:
    __slots__ = ("entity_id", "entity_type", "model_name", "prediction_value",
                 "confidence_lower", "confidence_upper", "shap_values",
                 "feature_snapshot", "model_version", "model_id")

    def __init__(
        self,
        entity_id: str,
        entity_type: str,
        model_name: str,
        prediction_value: float,
        confidence_lower: Optional[float],
        confidence_upper: Optional[float],
        shap_values: Optional[dict],
        feature_snapshot: dict,
        model_version: str,
        model_id: str,
    ) -> None:
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.model_name = model_name
        self.prediction_value = prediction_value
        self.confidence_lower = confidence_lower
        self.confidence_upper = confidence_upper
        self.shap_values = shap_values
        self.feature_snapshot = feature_snapshot
        self.model_version = model_version
        self.model_id = model_id

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "model_name": self.model_name,
            "prediction_value": self.prediction_value,
            "confidence_lower": self.confidence_lower,
            "confidence_upper": self.confidence_upper,
            "shap_values": self.shap_values,
            "feature_snapshot": self.feature_snapshot,
            "model_version": self.model_version,
            "model_id": self.model_id,
        }


class ModelServingEngine:
    """
    Loads the champion model for each task from MinIO (or local path) and
    serves predictions. Falls back to L4 heuristic scores when no champion exists.
    """

    def __init__(self) -> None:
        self._model_cache: dict[str, object] = {}

    async def predict(
        self,
        model_name: str,
        entity_type: str,
        entity_id: str,
        persist: bool = True,
    ) -> PredictionResult:
        champion = await model_registry.get_champion(model_name)

        features = await get_latest_features(entity_type, entity_id)
        if features is None:
            features = get_feature_defaults(entity_type)

        if champion is None:
            return await self._heuristic_fallback(model_name, entity_type, entity_id, features)

        model_id = str(champion["model_id"])
        artifact_path = champion.get("model_artifact_path")
        clf = await self._load_artifact(model_id, artifact_path)

        if clf is None:
            return await self._heuristic_fallback(model_name, entity_type, entity_id, features)

        feature_names = get_feature_names(entity_type)
        X = [[features.get(f, 0.0) for f in feature_names]]

        try:
            import numpy as np
            X_np = np.array(X, dtype=float)

            if hasattr(clf, "predict_proba"):
                proba = clf.predict_proba(X_np)[0]
                pred_value = float(proba[1]) if len(proba) == 2 else float(proba.max())
                ci_half = 0.05
            else:
                pred_value = float(clf.predict(X_np)[0])
                ci_half = 0.1

            shap_values = await self._compute_shap(clf, X_np, feature_names)
            ci_lower = max(0.0, pred_value - ci_half)
            ci_upper = min(1.0, pred_value + ci_half)

            result = PredictionResult(
                entity_id=entity_id,
                entity_type=entity_type,
                model_name=model_name,
                prediction_value=round(pred_value, 4),
                confidence_lower=round(ci_lower, 4),
                confidence_upper=round(ci_upper, 4),
                shap_values=shap_values,
                feature_snapshot=features,
                model_version=champion["version"],
                model_id=model_id,
            )

            if persist:
                await self._persist_prediction(result, model_id)

            return result

        except Exception as exc:
            logger.error("Model inference failed for %s/%s: %s", model_name, entity_id, exc)
            return await self._heuristic_fallback(model_name, entity_type, entity_id, features)

    async def _load_artifact(self, model_id: str, artifact_path: Optional[str]) -> Optional[object]:
        if model_id in self._model_cache:
            return self._model_cache[model_id]
        if not artifact_path:
            return None
        try:
            if artifact_path.startswith("minio://") or artifact_path.startswith("s3://"):
                return await self._load_from_minio(model_id, artifact_path)
            with open(artifact_path, "rb") as f:
                clf = pickle.load(f)
            self._model_cache[model_id] = clf
            return clf
        except Exception as exc:
            logger.warning("Could not load model artifact %s: %s", artifact_path, exc)
            return None

    async def _load_from_minio(self, model_id: str, path: str) -> Optional[object]:
        try:
            from minio import Minio
            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            bucket = settings.model_artifact_bucket
            object_name = path.split("//", 1)[-1].split("/", 1)[-1]
            data = client.get_object(bucket, object_name)
            clf = pickle.loads(data.read())
            self._model_cache[model_id] = clf
            return clf
        except Exception as exc:
            logger.warning("MinIO artifact load failed: %s", exc)
            return None

    async def _compute_shap(
        self,
        clf: object,
        X_np,
        feature_names: list[str],
    ) -> Optional[dict]:
        try:
            import shap
            explainer = shap.TreeExplainer(clf)
            shap_vals = explainer.shap_values(X_np)
            if isinstance(shap_vals, list):
                vals = shap_vals[1][0]
            else:
                vals = shap_vals[0]
            return {feature_names[i]: round(float(vals[i]), 5) for i in range(len(feature_names))}
        except Exception:
            return None

    async def _heuristic_fallback(
        self,
        model_name: str,
        entity_type: str,
        entity_id: str,
        features: dict,
    ) -> PredictionResult:
        """Use L4 precursor score / L3 risk score as a proxy until a trained model exists."""
        if model_name == MODEL_CIRP_PRECURSOR:
            raw = features.get("l4_precursor_score", features.get("layer3_risk_score", 50.0))
            pred = round(min(raw / 100.0, 1.0), 4)
        elif model_name == MODEL_PROJECT_COMPLETION:
            delay_ratio = features.get("delay_ratio", 0.0)
            pred = round(max(0.0, min(1.0 - delay_ratio * 0.5, 1.0)), 4)
        else:
            pred = 0.5

        return PredictionResult(
            entity_id=entity_id,
            entity_type=entity_type,
            model_name=model_name,
            prediction_value=pred,
            confidence_lower=max(0.0, pred - 0.15),
            confidence_upper=min(1.0, pred + 0.15),
            shap_values=None,
            feature_snapshot=features,
            model_version="heuristic_fallback",
            model_id="",
        )

    async def _persist_prediction(self, result: PredictionResult, model_id: str) -> None:
        pool = get_pool()
        try:
            import uuid as _uuid
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO l5_predictions
                        (model_id, entity_type, entity_id, prediction_value,
                         confidence_lower, confidence_upper, shap_values, feature_snapshot)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                    """,
                    _uuid.UUID(model_id) if model_id else None,
                    result.entity_type, result.entity_id,
                    result.prediction_value,
                    result.confidence_lower, result.confidence_upper,
                    json.dumps(result.shap_values) if result.shap_values else None,
                    json.dumps(result.feature_snapshot),
                )
        except Exception as exc:
            logger.warning("Failed to persist prediction for %s: %s", result.entity_id, exc)


model_server = ModelServingEngine()
