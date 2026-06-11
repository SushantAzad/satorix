"""
Financial Stress Trajectory — predicts a company's current ratio 2 quarters ahead.
Uses a simple gradient-boosted regressor on rolling window of financial ratios.
Full LSTM training is the Phase 2 upgrade path when sufficient time-series data exists.
"""
import logging
import os
import pickle
import tempfile
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "financial_trajectory"


async def train(
    time_series_samples: list[dict],  # each: {cin, quarters: [float], target_ratio: float}
    artifact_dir: Optional[str] = None,
) -> dict:
    from models.registry import model_registry

    if len(time_series_samples) < 30:
        return {"status": "skipped", "reason": "insufficient_data"}

    X, y = [], []
    for s in time_series_samples:
        quarters = s.get("quarters", [])
        if len(quarters) < 4:
            continue
        # Use last 8 quarters (pad with 0 if fewer)
        window = (quarters[-8:] if len(quarters) >= 8 else [0.0] * (8 - len(quarters)) + quarters)
        X.append(window)
        y.append(float(s["target_ratio"]))

    if len(X) < 20:
        return {"status": "skipped", "reason": "insufficient_windowed_data"}

    try:
        import numpy as np
        from xgboost import XGBRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_squared_error

        X_np = np.array(X, dtype=float)
        y_np = np.array(y)
        X_tr, X_te, y_tr, y_te = train_test_split(X_np, y_np, test_size=0.2, random_state=42)

        reg = XGBRegressor(
            max_depth=4, learning_rate=0.05, n_estimators=100,
            subsample=0.8, random_state=42,
        )
        reg.fit(X_tr, y_tr)

        y_pred = reg.predict(X_te)
        rmse = float(mean_squared_error(y_te, y_pred) ** 0.5)
        metrics = {"rmse": rmse, "n_train": len(X_tr), "n_test": len(X_te)}

        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if artifact_dir is None:
            artifact_dir = tempfile.gettempdir()
        artifact_path = os.path.join(artifact_dir, f"{MODEL_NAME}_{version}.pkl")
        with open(artifact_path, "wb") as f:
            pickle.dump(reg, f)

        model_id = await model_registry.register(
            model_name=MODEL_NAME,
            model_type="XGBRegressor_timeseries",
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
