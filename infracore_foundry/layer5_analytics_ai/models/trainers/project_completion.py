"""
XGBoost Project Completion Probability Model.
Replaces Layer 3's heuristic v0.3 (project_probability.py).
Target: probability that a project completes within 6 months of revised date.
"""
import logging
import os
import pickle
import tempfile
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "project_completion"


async def train(
    labeled_projects: list[dict],  # each: {project_id, completed_on_time: bool}
    artifact_dir: Optional[str] = None,
) -> dict:
    from feature_store.feature_store import get_latest_features
    from feature_store.feature_registry import get_feature_names
    from models.registry import model_registry
    from models.evaluator import compare
    from models.calibrator import calibrate, brier_score

    feature_names = get_feature_names("Project")
    X, y = [], []
    for item in labeled_projects:
        feats = await get_latest_features("Project", item["project_id"])
        if feats is None:
            continue
        X.append([feats.get(f, 0.0) for f in feature_names])
        y.append(1 if item["completed_on_time"] else 0)

    if len(X) < 20:
        logger.warning("Insufficient project completion training data (%d samples)", len(X))
        return {"status": "skipped", "reason": "insufficient_data"}

    try:
        import numpy as np
        from xgboost import XGBClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score

        X_np = np.array(X, dtype=float)
        y_np = np.array(y)
        X_tr, X_te, y_tr, y_te = train_test_split(X_np, y_np, test_size=0.2, random_state=42)

        clf = XGBClassifier(
            max_depth=4, learning_rate=0.05, n_estimators=150,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="logloss", random_state=42,
        )
        clf.fit(X_tr, y_tr)

        y_prob = clf.predict_proba(X_te)[:, 1]
        metrics = {
            "auc_roc": float(roc_auc_score(y_te, y_prob)),
            "brier_score": brier_score(y_te, y_prob),
            "n_train": len(X_tr),
            "n_test": len(X_te),
        }

        clf = calibrate(clf, X_te, y_te)

        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if artifact_dir is None:
            artifact_dir = tempfile.gettempdir()
        artifact_path = os.path.join(artifact_dir, f"{MODEL_NAME}_{version}.pkl")
        with open(artifact_path, "wb") as f:
            pickle.dump(clf, f)

        champion = await model_registry.get_champion(MODEL_NAME)
        eval_result = compare(MODEL_NAME, champion["evaluation_metrics"] if champion else None, metrics)
        status = "champion" if eval_result.should_promote else "challenger"

        model_id = await model_registry.register(
            model_name=MODEL_NAME,
            model_type="XGBClassifier",
            version=version,
            evaluation_metrics=metrics,
            artifact_path=artifact_path,
            training_sample_size=len(X),
            status=status,
        )
        if eval_result.should_promote:
            await model_registry.promote_to_champion(model_id, MODEL_NAME)

        return {"model_id": model_id, "metrics": metrics, "promoted": eval_result.should_promote}

    except ImportError:
        return {"status": "skipped", "reason": "xgboost_not_installed"}
