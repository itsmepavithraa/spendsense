"""Train the two SpendSense models from the seed CSV.

Run:  python -m app.ml.train
Outputs: app/ml/artifacts/categorizer.joblib, app/ml/artifacts/anomaly.joblib
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

CSV_PATH = Path("data/transactions_seed.csv")
ARTIFACTS = Path(__file__).parent / "artifacts"


def train_categorizer(df: pd.DataFrame) -> None:
    """Merchant name -> category (text classification)."""
    X_train, X_test, y_train, y_test = train_test_split(
        df["merchant"], df["category"], test_size=0.2, random_state=42, stratify=df["category"]
    )
    model = make_pipeline(
        # character n-grams cope with typos and unseen merchant variants
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True),
        LogisticRegression(max_iter=1000),
    )
    model.fit(X_train, y_train)
    print("=== Categorizer (merchant -> category) ===")
    print(classification_report(y_test, model.predict(X_test), digits=3))
    # refit on all data for the saved model
    model.fit(df["merchant"], df["category"])
    joblib.dump(model, ARTIFACTS / "categorizer.joblib")


def train_anomaly(df: pd.DataFrame) -> None:
    """Flag amounts that are unusual *for their category*."""
    df = df.copy()
    df["log_amount"] = np.log1p(df["amount"])

    # per-category statistics of log(amount), using robust median / MAD
    stats = {}
    for cat, g in df.groupby("category"):
        med = float(g["log_amount"].median())
        mad = float((g["log_amount"] - med).abs().median()) or 0.1
        stats[cat] = (med, mad)

    def features(frame: pd.DataFrame) -> np.ndarray:
        z = frame.apply(
            lambda r: (r["log_amount"] - stats[r["category"]][0]) / (1.4826 * stats[r["category"]][1]),
            axis=1,
        )
        return np.column_stack([frame["log_amount"], z])

    X = features(df)
    model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    model.fit(X)

    pred = model.predict(X) == -1          # True = flagged as anomaly
    truth = df["is_anomaly"].to_numpy()
    p, r, f1, _ = precision_recall_fscore_support(truth, pred, average="binary", zero_division=0)
    print("=== Anomaly detector (Isolation Forest) ===")
    print(f"flagged {pred.sum()} of {len(df)}   |   precision {p:.3f}  recall {r:.3f}  f1 {f1:.3f}")

    joblib.dump({"model": model, "stats": stats}, ARTIFACTS / "anomaly.joblib")


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    df = pd.read_csv(CSV_PATH)
    df["is_anomaly"] = df["is_anomaly"].astype(bool)
    train_categorizer(df)
    train_anomaly(df)
    print(f"\nSaved models to {ARTIFACTS}")


if __name__ == "__main__":
    main()
