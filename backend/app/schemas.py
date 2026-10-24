"""Pydantic schemas: the shape of JSON the API accepts and returns.

Kept separate from models.py on purpose: models describe DB tables, schemas
describe the API. For example UserOut has no password field, so a password
hash can never leak in a response.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.categories import ALLOWED_CATEGORIES


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=72)  # bcrypt limit is 72 bytes


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    is_pro: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Billing ----------
class OrderOut(BaseModel):
    """What the browser needs to open Razorpay Checkout."""

    order_id: str
    key_id: str  # the PUBLIC key id; the secret never leaves the server
    amount: int  # paise
    currency: str


class VerifyPaymentIn(BaseModel):
    """The three values Razorpay Checkout hands back after a successful payment."""

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ---------- Category corrections ----------
class CategoryOverrideIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=120)
    category: str

    @field_validator("category")
    @classmethod
    def must_be_a_known_category(cls, value: str) -> str:
        if value not in ALLOWED_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(ALLOWED_CATEGORIES)}")
        return value


class CategoryOverrideOut(BaseModel):
    merchant: str
    category: str
    updated: int  # how many existing transactions were changed


class UncategorizedMerchant(BaseModel):
    merchant: str
    count: int
    total: float


# ---------- Statement import ----------
class ImportPreviewRow(BaseModel):
    date: str
    merchant: str
    amount: str
    category: str
    is_anomaly: bool


class ImportResult(BaseModel):
    """What happened to an uploaded statement: shown to the user, nothing hidden."""

    imported: int
    duplicates_skipped: int  # already in the account from an earlier upload
    credits_ignored: int  # money in (salary, refunds): not spending
    invalid_rows: int
    problems: list[str]  # first few unreadable rows, with line numbers
    uncategorized: int  # rows the model wasn't confident about
    unusual: int  # rows flagged as unusually large
    date_from: str | None
    date_to: str | None
    columns: dict[str, str]  # the columns we detected, so the user can sanity-check
    assumed_all_expenses: bool  # true when the file gave no way to tell spending from deposits
    preview: list[ImportPreviewRow]


# ---------- Transactions ----------
def _tidy_merchant(value: str | None) -> str | None:
    """Store merchant names with single spaces and no padding, so 'Sri  Store ' and
    'Sri Store' are one shop everywhere (corrections, grouping, de-duplication)."""
    if value is None:
        return None
    tidy = " ".join(value.split())
    if not tidy:
        raise ValueError("merchant must not be blank")
    return tidy


class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    merchant: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=50)
    occurred_at: datetime | None = None

    _tidy = field_validator("merchant")(_tidy_merchant)


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    merchant: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=50)
    occurred_at: datetime | None = None

    _tidy = field_validator("merchant")(_tidy_merchant)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    merchant: str
    category: str
    is_anomaly: bool
    occurred_at: datetime
