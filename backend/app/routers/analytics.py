"""Analytics endpoint that feeds the dashboard cards and charts.

All numbers are computed in the database (SUM / COUNT / GROUP BY) rather than
in Python, so it stays fast as a user's history grows. Every query is scoped to
the logged-in user.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, cast, extract, func, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Transaction, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/subscriptions")
def subscriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Recurring monthly charges, detected by the bi_subscriptions SQL view
    (see the migration for the detection rules)."""
    rows = db.execute(
        text(
            "SELECT merchant, amount, charges, avg_gap_days, last_charge, yearly_cost "
            "FROM bi_subscriptions WHERE user_id = :uid ORDER BY yearly_cost DESC"
        ),
        {"uid": user.id},  # bound parameter: never build SQL by string concatenation
    ).mappings()
    return [
        {
            "merchant": r["merchant"],
            "amount": r["amount"],
            "charges": r["charges"],
            "avg_gap_days": r["avg_gap_days"],
            "last_charge": r["last_charge"].isoformat(),
            "yearly_cost": r["yearly_cost"],
        }
        for r in rows
    ]


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    mine = Transaction.user_id == user.id
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # headline numbers
    total, count, anomalies = db.execute(
        select(
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
            # SUM a boolean by casting it to 0/1
            func.coalesce(func.sum(cast(Transaction.is_anomaly, Integer)), 0),
        ).where(mine)
    ).one()
    this_month = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            mine, Transaction.occurred_at >= month_start
        )
    )

    # spend per category (for the donut chart)
    by_category = db.execute(
        select(Transaction.category, func.sum(Transaction.amount).label("total"))
        .where(mine)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    # spend per month, last 12 months (for the trend chart)
    year = extract("year", Transaction.occurred_at)
    month = extract("month", Transaction.occurred_at)
    monthly = db.execute(
        select(year, month, func.sum(Transaction.amount))
        .where(mine)
        .group_by(year, month)
        .order_by(year.desc(), month.desc())
        .limit(12)
    ).all()

    return {
        "total_spend": float(total),
        "this_month_spend": float(this_month),
        "transaction_count": int(count),
        "anomaly_count": int(anomalies),
        "by_category": [{"category": c, "total": float(t)} for c, t in by_category],
        "monthly": [
            {"month": f"{int(y)}-{int(m):02d}", "total": float(t)}
            for y, m, t in reversed(monthly)  # oldest first for the chart
        ],
    }
