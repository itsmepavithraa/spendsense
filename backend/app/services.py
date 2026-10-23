"""Business logic shared by the REST endpoint and the bank-feed simulator.

Keeping "create a transaction" in one place means both code paths get the
same ML behaviour (auto-category + anomaly flag) and can't drift apart.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ml.inference import is_anomalous, predict_category
from app.models import Transaction


def create_transaction_for_user(
    db: Session,
    user_id: int,
    merchant: str,
    amount: Decimal,
    category: str | None = None,
    occurred_at: datetime | None = None,
) -> Transaction:
    # ML: fill in the category if the caller didn't send one, then score the amount
    category = category or predict_category(merchant)
    txn = Transaction(
        user_id=user_id,
        amount=amount,
        merchant=merchant,
        category=category,
        is_anomaly=is_anomalous(float(amount), category),
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn
