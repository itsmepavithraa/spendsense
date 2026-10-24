"""Business logic shared by the REST endpoint and the bank-feed simulator.

Keeping "create a transaction" in one place means both code paths get the
same ML behaviour (auto-category + anomaly flag) and can't drift apart.
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.categories import merchant_key
from app.config import settings
from app.ml.inference import is_anomalous, predict_category
from app.models import CategoryOverride, Transaction


def ensure_room(db: Session, user_id: int, adding: int) -> None:
    """Refuse to store more than MAX_TRANSACTIONS_PER_USER per account, so one account can't
    fill a small shared database."""
    cap = settings.max_transactions_per_user
    if not cap:
        return
    stored = db.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user_id)) or 0
    if stored + adding > cap:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Account limit reached: at most {cap:,} transactions per account "
            f"(you have {stored:,}). Delete your account data or import a shorter date range.",
        )


def load_overrides(db: Session, user_id: int) -> dict[str, str]:
    """The user's remembered corrections as {merchant_key: category}. One query, so a
    whole imported statement can be checked against it without a query per row."""
    rows = db.execute(
        select(CategoryOverride.merchant_key, CategoryOverride.category).where(
            CategoryOverride.user_id == user_id
        )
    )
    return {key: category for key, category in rows}


def create_transaction_for_user(
    db: Session,
    user_id: int,
    merchant: str,
    amount: Decimal,
    category: str | None = None,
    occurred_at: datetime | None = None,
) -> Transaction:
    ensure_room(db, user_id, 1)
    # Category, strongest first: what the caller chose, what the user taught us earlier,
    # then keyword rules and the ML model. Then score the amount for that category.
    category = (
        category
        or load_overrides(db, user_id).get(merchant_key(merchant))
        or predict_category(merchant)
    )
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
