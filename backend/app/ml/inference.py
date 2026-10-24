"""Load the trained models once and expose simple prediction functions.

If the model files are missing (e.g. a fresh clone before training), the functions
fall back to safe defaults so the API keeps working.

The batch versions (predict_categories, anomaly_flags) exist for statement imports:
scoring thousands of rows in one call is far faster than one call per row.
"""
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

from app.ml.rules import rule_category

ARTIFACTS = Path(__file__).parent / "artifacts"

# Below this confidence the categorizer says "Uncategorized" instead of guessing.
# Measured on real bank text: brands the model knows score 0.74 or more (Swiggy 0.98,
# Ola 0.93, Netflix 0.74), while names it has never seen, such as a person's name, score
# only 0.4 to 0.6. At 0.5 a person was labelled "Transport" and distorted the advice, so
# the bar sits at 0.7. A wrong label is worse than an honest "I don't know".
MIN_CONFIDENCE = 0.7
UNCATEGORIZED = "Uncategorized"


@lru_cache(maxsize=1)
def _categorizer():
    path = ARTIFACTS / "categorizer.joblib"
    return joblib.load(path) if path.exists() else None


@lru_cache(maxsize=1)
def _anomaly():
    path = ARTIFACTS / "anomaly.joblib"
    return joblib.load(path) if path.exists() else None


def predict_categories(merchants: list[str]) -> list[str]:
    """Category for each merchant: keyword rules first, then the model, else 'Uncategorized'."""
    results = [rule_category(m) for m in merchants]  # None where no rule applies
    model = _categorizer()
    undecided = [i for i, category in enumerate(results) if category is None]
    if model is not None and undecided:
        probabilities = model.predict_proba([merchants[i] for i in undecided])
        best = probabilities.argmax(axis=1)
        for row, i in enumerate(undecided):
            if probabilities[row, best[row]] >= MIN_CONFIDENCE:
                results[i] = str(model.classes_[best[row]])
    return [category or UNCATEGORIZED for category in results]


def predict_category(merchant: str) -> str:
    return predict_categories([merchant])[0]


def anomaly_flags(amounts: list[float], categories: list[str]) -> list[bool]:
    """True for each amount that is unusually LARGE for its category.

    Isolation Forest flags outliers in both directions, but a tiny purchase is not
    worth an alert, so only amounts above the category's typical level (z > 0) count.
    """
    flags = [False] * len(amounts)
    bundle = _anomaly()
    if bundle is None:
        return flags

    rows, features = [], []
    for i, (amount, category) in enumerate(zip(amounts, categories)):
        if category not in bundle["stats"]:
            continue  # no baseline for this category, so no judgement
        log_amount = float(np.log1p(amount))
        median, mad = bundle["stats"][category]
        z = (log_amount - median) / (1.4826 * mad)
        if z > 0:
            rows.append(i)
            features.append([log_amount, z])

    if features:
        predictions = bundle["model"].predict(np.array(features))
        for i, prediction in zip(rows, predictions):
            flags[i] = bool(prediction == -1)
    return flags


def is_anomalous(amount: float, category: str) -> bool:
    return anomaly_flags([amount], [category])[0]
