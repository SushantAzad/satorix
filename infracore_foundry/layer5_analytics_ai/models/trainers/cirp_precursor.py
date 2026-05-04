"""
XGBoost CIRP Precursor Classifier.
Trains on historical company feature vectors with binary label:
  1 = company entered CIRP within 18 months of feature snapshot
  0 = company did not enter CIRP

Ground truth: IBBI records (cin + cirp_admission_date).
Training data assembled by feature_store.get_features_at_time() queried
18 months before each known CIRP event.
"""
import io
import json
import logging
import os
import pickle
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "cirp_precursor"
FEATURE_SCHEMA_VERSION = "v1.0"

# Training cut-off for temporal split
TRAIN_CUTOFF = datetime(2022, 1, 1, tzinfo=timezone.utc)


async def train(
    positive_examples: list[tuple[str, datetime]],  # (cin, cirp_admission_date)
    negative_cins: list[str],
    artifact_dir: Optional[str] = None,
) -> dict:
    """
    Returns dict with model_id, metrics, artifact_path.
    Registers model in registry after training.
    """
    from feature_store.feature_store import get_features_at_time, get_latest_features
    from feature_store.feature_registry import get_feature_names
    from models.registry import model_registry
    from models.evaluator import compare
    from models.calibrator import calibrate, brier_score

    feature_names = get_feature_names("Company")

    X_train, y_train = [], []
    X_test, y_test = [], []

    for cin, cirp_date in positive_examples:
        snapshot_date = cirp_date - timedelta(days=548)  # 18 months before
        feats = await get_features_at_time("Company", cin, snapshot_date)
        if feats is None:
            continue
        row = [feats.get(f, 0.0) for f in feature_names]
        if cirp_date < TRAIN_CUTOFF:
            X_train.append(row)
            y_train.append(1)
        else:
            X_test.append(row)
            y_test.append(1)

    for cin in negative_cins:
        feats = await get_latest_features("Company", cin)
        if feats is None:
            continue
        row = [feats.get(f, 0.0) for f in feature_names]
        X_train.append(row)
        y_train.append(0)

    if len(X_train) < 20:
        logger.warning("Insufficient training data for CIRP precursor (%d samples)", len(X_train))
        return {"status": "skipped", "reason": "insufficient_data", "n_train": len(X_train)}

    try:
        import numpy as np
        from xgboost import XGBClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.metrics import roc_auc_score, precision_score, recall_score

        X_tr = np.array(X_train, dtype=float)
        y_tr = np.array(y_train)

        clf = XGBClassifier(
            max_depth=4,
            learning_rate=0.05,
            n_estimators=200,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
        clf.fit(X_tr, y_tr)

        # Evaluate
        metrics: dict = {}
        if len(X_test) >= 10:
            X_te = np.array(X_test, dtype=float)
            y_te = np.array(y_test)
            y_prob = clf.predict_proba(X_te)[:, 1]
            metrics["auc_roc"] = float(roc_auc_score(y_te, y_prob))
            metrics["brier_score"] = brier_score(y_te, y_prob)
            y_pred = (y_prob >= 0.5).astype(int)
            metrics["precision"] = float(precision_score(y_te, y_pred, zero_division=0))
            metrics["recall"] = float(recall_score(y_te, y_pred, zero_division=0))
        else:
            cv_auc = cross_val_score(clf, X_tr, y_tr, cv=3, scoring="roc_auc")
            metrics["auc_roc"] = float(cv_auc.mean())

        metrics["n_train"] = len(X_train)
        metrics["n_test"] = len(X_test)

        # Calibrate
        if len(X_test) >= 10:
            clf = calibrate(clf, np.array(X_test, dtype=float), np.array(y_test))

        # Save artifact
        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if artifact_dir is None:
            artifact_dir = tempfile.gettempdir()
        artifact_path = os.path.join(artifact_dir, f"{MODEL_NAME}_{version}.pkl")
        with open(artifact_path, "wb") as f:
            pickle.dump(clf, f)

        champion = await model_registry.get_champion(MODEL_NAME)
        champion_metrics = champion["evaluation_metrics"] if champion else None

        eval_result = compare(MODEL_NAME, champion_metrics, metrics)
        status = "champion" if eval_result.should_promote else "challenger"

        model_id = await model_registry.register(
            model_name=MODEL_NAME,
            model_type="XGBClassifier",
            version=version,
            evaluation_metrics=metrics,
            artifact_path=artifact_path,
            hyperparameters=clf.get_params() if hasattr(clf, "get_params") else {},
            training_sample_size=len(X_train),
            status=status,
        )

        if eval_result.should_promote:
            await model_registry.promote_to_champion(model_id, MODEL_NAME)

        logger.info("CIRP precursor training complete: %s, promote=%s", metrics, eval_result.should_promote)
        return {"model_id": model_id, "metrics": metrics, "promoted": eval_result.should_promote, "reason": eval_result.reason}

    except ImportError:
        logger.warning("XGBoost not installed — CIRP precursor training skipped")
        return {"status": "skipped", "reason": "xgboost_not_installed"}
