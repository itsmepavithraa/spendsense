"""Accounts: register, login (returns a JWT), the user's own data, and account deletion.

This site accepts sign-ups from the public, so the safeguards matter:
* sign-up and login are rate limited per visitor address, and repeated wrong passwords for one
  email lock further attempts for a while (see ratelimit.py);
* sign-ups can be closed instantly (ALLOW_REGISTRATION) or capped (MAX_USERS);
* every user can download all their data and permanently delete their account.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import CategoryOverride, Payment, Transaction, User
from app.ratelimit import FAILED_LOGINS, limit_by_address, too_many
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# The most common passwords: attackers try these first, so they are refused outright.
COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "12345678", "123456789", "1234567890",
    "qwerty123", "qwertyuiop", "iloveyou", "admin123", "welcome1", "welcome123", "abc12345",
    "11111111", "00000000", "letmein123", "passw0rd", "p@ssw0rd", "demo12345", "spendsense",
}


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[limit_by_address("register", limit=5, window=3600)],  # 5 sign-ups an hour per address
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "New sign-ups are closed right now.")
    if settings.max_users and db.scalar(select(func.count(User.id))) >= settings.max_users:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SpendSense is full for now. Please try again later.")
    if settings.password_blocklist_enabled and payload.password.lower() in COMMON_PASSWORDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That password is too common. Please choose a less guessable one.")

    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    dependencies=[limit_by_address("login", limit=20, window=60)],  # 20 attempts a minute per address
)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    # OAuth2 forms call the field "username"; we use it for the email.
    email = form.username.lower()
    if settings.rate_limit_enabled and FAILED_LOGINS.blocked(email):
        raise too_many(FAILED_LOGINS.retry_after(email))  # locked after 5 wrong passwords in 15 minutes

    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(form.password, user.hashed_password):
        FAILED_LOGINS.record(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    FAILED_LOGINS.reset(email)  # a correct password clears the count
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# ------------------------------------------------------------ your data, your choice
@router.get("/me/export")
def export_my_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Everything the app stores about you, as one JSON file."""
    transactions = db.scalars(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.occurred_at)
    ).all()
    corrections = db.scalars(select(CategoryOverride).where(CategoryOverride.user_id == user.id)).all()
    payments = db.scalars(select(Payment).where(Payment.user_id == user.id)).all()
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "email": user.email,
            "full_name": user.full_name,
            "is_pro": user.is_pro,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "transactions": [
            {
                "date": t.occurred_at.isoformat(),
                "merchant": t.merchant,
                "category": t.category,
                "amount": str(t.amount),  # exact, as a string
                "flagged_unusual": t.is_anomaly,
            }
            for t in transactions
        ],
        "category_corrections": [{"merchant": c.merchant_key, "category": c.category} for c in corrections],
        "payments": [
            {"order_id": p.razorpay_order_id, "status": p.status, "amount_paise": p.amount_paise, "paid_at": p.paid_at.isoformat() if p.paid_at else None}
            for p in payments
        ],
    }
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="spendsense-my-data.json"'})


class DeleteAccountIn(BaseModel):
    password: str


@router.post(
    "/delete-account",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[limit_by_address("delete-account", limit=10, window=3600)],
)
def delete_account(
    payload: DeleteAccountIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently erase the account and everything in it. Needs the password, so a stolen
    session alone can't wipe someone's data. Child rows are deleted explicitly instead of
    relying on database cascades, so it works the same on every database."""
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password")
    for model in (Transaction, CategoryOverride, Payment):
        db.execute(delete(model).where(model.user_id == user.id))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
