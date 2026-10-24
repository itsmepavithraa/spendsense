"""Teach the app once: 'this merchant is always this category'.

PUT  /merchants/category      remember the choice and fix all existing rows of that merchant
GET  /merchants/uncategorized the user's merchants that still need a category, biggest first

Every query is scoped to the logged-in user, like the rest of the API.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.categories import UNCATEGORIZED, merchant_key
from app.database import get_db
from app.deps import get_current_user
from app.ml.inference import anomaly_flags
from app.models import CategoryOverride, Transaction, User
from app.realtime import manager
from app.schemas import CategoryOverrideIn, CategoryOverrideOut, UncategorizedMerchant

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.put("/category", response_model=CategoryOverrideOut)
def set_merchant_category(
    payload: CategoryOverrideIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    key = merchant_key(payload.merchant)

    # remember the choice (create it, or change an earlier one)
    override = db.scalar(
        select(CategoryOverride).where(
            CategoryOverride.user_id == user.id, CategoryOverride.merchant_key == key
        )
    )
    if override is None:
        db.add(CategoryOverride(user_id=user.id, merchant_key=key, category=payload.category))
    else:
        override.category = payload.category

    # fix every existing row of that merchant. The "unusual charge" flag depends on the
    # category (₹2,000 is huge for tea, normal for groceries), so it is recomputed too.
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user.id,
            func.lower(Transaction.merchant) == key,
        )
    ).all()
    flags = anomaly_flags([float(t.amount) for t in transactions], [payload.category] * len(transactions))
    for transaction, flag in zip(transactions, flags):
        transaction.category = payload.category
        transaction.is_anomaly = flag
    db.commit()

    # any other open tab refreshes by itself
    background.add_task(
        manager.send_events,
        user.id,
        [{"type": "transactions.recategorized", "data": {"merchant": payload.merchant, "category": payload.category, "count": len(transactions)}}],
    )
    return CategoryOverrideOut(merchant=payload.merchant, category=payload.category, updated=len(transactions))


@router.get("/uncategorized", response_model=list[UncategorizedMerchant])
def uncategorized_merchants(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Merchants with at least one Uncategorized row, biggest total spend first, so a few
    corrections clear most of the money."""
    total = func.sum(Transaction.amount)
    rows = db.execute(
        select(func.min(Transaction.merchant), func.count(Transaction.id), total)
        .where(Transaction.user_id == user.id, Transaction.category == UNCATEGORIZED)
        .group_by(func.lower(Transaction.merchant))
        .order_by(total.desc())
        .limit(limit)
    ).all()
    return [UncategorizedMerchant(merchant=m, count=int(c), total=float(t)) for m, c, t in rows]
