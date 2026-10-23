"""Pydantic schemas: the shape of JSON the API accepts and returns.

Kept separate from models.py on purpose: models describe DB tables, schemas
describe the API. For example UserOut has no password field, so a password
hash can never leak in a response.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


# ---------- Transactions ----------
class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    merchant: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=50)
    occurred_at: datetime | None = None


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    merchant: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=50)
    occurred_at: datetime | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    merchant: str
    category: str
    is_anomaly: bool
    occurred_at: datetime
