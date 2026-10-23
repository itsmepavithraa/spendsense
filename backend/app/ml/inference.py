"""Load the trained models once and expose two simple functions.

If the model files are missing (e.g. a fresh clone before training), both
functions fall back to safe defaults so the API keeps working.
"""
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

ARTIFACTS = Path(__file__).parent / "artifacts"


@lru_cache(maxsize=1)
def _categorizer():
    path = ARTIFACTS / "categorizer.joblib"
    return joblib.load(path) if path.exists() else None


@lru_cache(maxsize=1)
def _anomaly():
    path = ARTIFACTS / "anomaly.joblib"
    return joblib.load(path) if path.exists() else None


def predict_category(merchant: str) -> str:
    model = _categorizer()
    if model is None:
        return "Uncategorized"
    return str(model.predict([merchant])[0])


def is_anomalous(amount: float, category: str) -> bool:
    bundle = _anomaly()
    if bundle is None or category not in bundle["stats"]:
        return False
    log_amount = float(np.log1p(amount))
    med, mad = bundle["stats"][category]
    z = (log_amount - med) / (1.4826 * mad)
    return bool(bundle["model"].predict([[log_amount, z]])[0] == -1)
