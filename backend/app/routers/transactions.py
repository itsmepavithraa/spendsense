"""Transaction CRUD endpoints.

Security: every query is scoped to the logged-in user (user_id == user.id),
and the user comes from the verified JWT, never from the request body. This
prevents user A from reading user B's data by guessing ids (an IDOR bug).
On create, the ML models fill in the category and the anomaly flag.
"""
import csv
import io
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.categories import merchant_key
from app.importer import MAX_FILE_BYTES, StatementError, parse_statement
from app.ml.inference import UNCATEGORIZED, anomaly_flags, predict_categories
from app.models import Transaction, User
from app.realtime import manager, transaction_events
from app.schemas import (
    ImportPreviewRow,
    ImportResult,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services import create_transaction_for_user, load_overrides

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _spreadsheet_safe(value: str) -> str:
    """Stop 'CSV injection': Excel and Sheets run any cell that starts with = + - @ as a
    formula. Merchant names come from outside (imported statements), so a malicious one
    like =HYPERLINK(...) must be defanged before it lands in a downloadable file."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


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


@router.post("/import", response_model=ImportResult)
def import_statement(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a bank statement CSV: spending rows only, categorised and scored by the models.

    Safe to repeat: rows already in the account are skipped, so uploading the same
    statement twice (or an overlapping one) never creates duplicates.
    """
    content = file.file.read(MAX_FILE_BYTES + 1)  # read one byte past the limit to detect oversize
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large (limit 2 MB)")
    try:
        parsed = parse_statement(content)
    except StatementError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))

    # One import per user at a time. Without this, two uploads of the same file arriving
    # together (a double click, two tabs) would both pass the duplicate check below before
    # either had saved, and every row would be stored twice. The lock lasts until this
    # transaction commits, so the second request waits, then sees the first one's rows.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:namespace, :user_id)"), {"namespace": 7001, "user_id": user.id})

    # What does this user already have in the same date range? Counted, not just checked,
    # because two identical purchases on one day (two coffees) are legitimately separate.
    already_stored: Counter = Counter()
    if parsed.rows:
        first = min(r.occurred_at for r in parsed.rows) - timedelta(days=1)
        last = max(r.occurred_at for r in parsed.rows) + timedelta(days=1)
        stored = db.execute(
            select(Transaction.occurred_at, Transaction.merchant, Transaction.amount).where(
                Transaction.user_id == user.id,
                Transaction.occurred_at >= first,
                Transaction.occurred_at <= last,
            )
        )
        for occurred_at, merchant, amount in stored:
            already_stored[(occurred_at.date(), merchant.lower(), Decimal(amount).quantize(Decimal("0.01")))] += 1

    fresh, duplicates = [], 0
    for row in parsed.rows:
        key = (row.occurred_at.date(), row.merchant.lower(), row.amount)
        if already_stored[key] > 0:
            already_stored[key] -= 1
            duplicates += 1
        else:
            fresh.append(row)

    # one batch call each for the models: far faster than scoring row by row
    categories = predict_categories([r.merchant for r in fresh])
    remembered = load_overrides(db, user.id)  # the user's own corrections beat rules and model
    categories = [remembered.get(merchant_key(r.merchant), c) for r, c in zip(fresh, categories)]
    flags = anomaly_flags([float(r.amount) for r in fresh], categories)
    db.add_all(
        Transaction(
            user_id=user.id,
            amount=row.amount,
            merchant=row.merchant,
            category=category,
            is_anomaly=flag,
            occurred_at=row.occurred_at,
        )
        for row, category, flag in zip(fresh, categories, flags)
    )
    db.commit()

    if fresh:  # tell the user's open tabs so the dashboard refreshes by itself
        background.add_task(
            manager.send_events,
            user.id,
            [{"type": "transactions.imported", "data": {"count": len(fresh), "unusual": sum(flags)}}],
        )

    dates = [r.occurred_at.date().isoformat() for r in fresh]  # ISO dates sort correctly as text
    return ImportResult(
        imported=len(fresh),
        duplicates_skipped=duplicates,
        credits_ignored=parsed.credits_ignored,
        invalid_rows=len(parsed.invalid),
        problems=parsed.invalid[:10],
        uncategorized=categories.count(UNCATEGORIZED),
        unusual=sum(flags),
        date_from=min(dates, default=None),
        date_to=max(dates, default=None),
        columns=parsed.columns,
        assumed_all_expenses=parsed.assumed_all_expenses,
        preview=[
            ImportPreviewRow(
                date=row.occurred_at.date().isoformat(),
                merchant=row.merchant,
                amount=str(row.amount),
                category=category,
                is_anomaly=flag,
            )
            for row, category, flag in list(zip(fresh, categories, flags))[:5]
        ],
    )


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


# NOTE: this route must stay ABOVE "/{txn_id}", or FastAPI would try to parse
# the word "export" as a transaction id and answer 422.
@router.get("/export")
def export_csv(user: User = Depends(get_current_user)):
    """Download all of the user's transactions as CSV. A Pro-plan feature."""
    if not user.is_pro:
        # 402 Payment Required: the request is fine, the plan isn't
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "CSV export is a Pro feature")

    user_id = user.id  # read now: the request's own DB session is closed before streaming starts

    def rows():
        # The streaming body runs AFTER FastAPI has closed the request's session, so
        # this generator opens (and always closes) its own. Reusing the closed one
        # leaked a connection per export, left idle in a transaction holding locks.
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "merchant", "category", "amount", "unusual"])
        yield buffer.getvalue()
        with SessionLocal() as stream_db:
            stmt = (
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.occurred_at.desc())
                .execution_options(yield_per=1000)  # stream in chunks, don't load everything
            )
            for t in stream_db.scalars(stmt):
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow(
                    [
                        t.occurred_at.isoformat(),
                        _spreadsheet_safe(t.merchant),
                        _spreadsheet_safe(t.category),
                        t.amount,
                        t.is_anomaly,
                    ]
                )
                yield buffer.getvalue()

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="spendsense-transactions.csv"'},
    )


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
