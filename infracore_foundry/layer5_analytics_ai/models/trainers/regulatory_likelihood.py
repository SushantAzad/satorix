"""
Multi-class XGBoost classifier predicting which regulatory body
is most likely to take action against a company in the next 12 months.
Classes: SEBI | RBI | ED | NHAI | NCLT | None
"""
import logging
import os
import pickle
import tempfile
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "regulatory_likelihood"
CLASSES = ["None", "SEBI", "RBI", "ED", "NHAI", "NCLT"]


async def train(
    labeled_companies: list[dict],  # each: {cin, target_body: str (one of CLASSES)}
    artifact_dir: Optional[str] = None,
) -> dict:
    from feature_store.feature_store import get_latest_features
    from feature_store.feature_registry import get_feature_names
    from models.registry import model_registry

    feature_names = get_feature_names("Company")
    X, y = [], []
    for item in labeled_companies:
        feats = await get_latest_features("Company", item["cin"])
        if feats is None:
            continue
        X.append([feats.get(f, 0.0) for f in feature_names])
        y.append(CLASSES.index(item.get("target_body", "None")))

    if len(X) < 30:
        return {"status": "skipped", "reason": "insufficient_data"}

    try:
        import numpy as np
        from xgboost import XGBClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import f1_score

        X_np = np.array(X, dtype=float)
        y_np = np.array(y)
        X_tr, X_te, y_tr, y_te = train_test_split(X_np, y_np, test_size=0.2, random_state=42)

        clf = XGBClassifier(
            objective="multi:softprob",
            num_class=len(CLASSES),
            max_depth=4, learning_rate=0.05, n_estimators=150,
            use_label_encoder=False, eval_metric="mlogloss", random_state=42,
        )
        clf.fit(X_tr, y_tr)

        y_pred = clf.predict(X_te)
        metrics = {
            "f1_macro": float(f1_score(y_te, y_pred, average="macro", zero_division=0)),
            "n_train": len(X_tr),
        }

        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if artifact_dir is None:
            artifact_dir = tempfile.gettempdir()
        artifact_path = os.path.join(artifact_dir, f"{MODEL_NAME}_{version}.pkl")
        with open(artifact_path, "wb") as f:
            pickle.dump({"clf": clf, "classes": CLASSES}, f)

        model_id = await model_registry.register(
            model_name=MODEL_NAME,
            model_type="XGBClassifier_multiclass",
            version=version,
            evaluation_metrics=metrics,
            artifact_path=artifact_path,
            training_sample_size=len(X),
            status="champion",
        )
        await model_registry.promote_to_champion(model_id, MODEL_NAME)
        return {"model_id": model_id, "metrics": metrics}

    except ImportError:
        return {"status": "skipped", "reason": "xgboost_not_installed"}
