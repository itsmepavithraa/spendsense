"""Transaction CRUD endpoints.

Security: every query is scoped to the logged-in user (user_id == user.id),
and the user comes from the verified JWT, never from the request body. This
prevents user A from reading user B's data by guessing ids (an IDOR bug).
On create, the ML models fill in the category and the anomaly flag.
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Transaction, User
from app.realtime import manager, transaction_events
from app.schemas import TransactionCreate, TransactionOut, TransactionUpdate
from app.services import create_transaction_for_user

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_owned_or_404(db: Session, txn_id: int, user: User) -> Transaction:
    """Fetch a transaction only if it belongs to this user."""
    txn = db.scalar(
        select(Transaction).where(
            Transaction.id == txn_id, Transaction.user_id == user.id
        )
    )
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return txn


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    txn = create_transaction_for_user(
        db,
        user.id,
        payload.merchant,
        payload.amount,
        category=payload.category,
        occurred_at=payload.occurred_at,
    )
    # Push to the user's open tabs *after* the response is sent, so a slow or
    # dead socket can never delay or break the API call itself.
    background.add_task(manager.send_events, user.id, transaction_events(txn))
    return txn


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    category: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if start:
        stmt = stmt.where(Transaction.occurred_at >= start)
    if end:
        stmt = stmt.where(Transaction.occurred_at <= end)
    stmt = stmt.order_by(Transaction.occurred_at.desc()).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _get_owned_or_404(db, txn_id, user)


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    txn = _get_owned_or_404(db, txn_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(txn, field, value)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    txn = _get_owned_or_404(db, txn_id, user)
    db.delete(txn)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
