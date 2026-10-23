"""Pro-plan payments with Razorpay.

The flow, and why each step exists:

1. POST /billing/create-order   The SERVER asks Razorpay to create an order for the
   price it chooses. The browser never decides the amount, so it can't pay ₹1.
2. (browser)                    Razorpay Checkout opens, the user pays. Razorpay
   returns order_id, payment_id and a signature to the browser.
3. POST /billing/verify         The browser sends those three values to us. We
   recompute the signature with our secret key. Only Razorpay (who knows the secret)
   can produce a matching one, so a match proves the payment is real. Then we
   upgrade the user.
4. POST /billing/webhook        Razorpay ALSO tells us directly, server-to-server.
   This is the safety net: if the user closes the tab right after paying, step 3
   never happens, but the webhook still upgrades them. Both paths are idempotent,
   so whichever arrives first wins and the second is harmless.

Signatures are HMAC-SHA256 and are compared in constant time (hmac.compare_digest)
so an attacker can't guess one byte at a time by measuring response times.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Payment, User
from app.schemas import OrderOut, VerifyPaymentIn

router = APIRouter(prefix="/billing", tags=["billing"])

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"


def _sign(message: bytes | str, secret: str) -> str:
    if isinstance(message, str):
        message = message.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def create_razorpay_order(amount_paise: int, receipt: str) -> dict:
    """Call Razorpay's API (basic auth = key id + secret). Isolated in its own
    function so tests can replace it without touching the network."""
    response = httpx.post(
        RAZORPAY_ORDERS_URL,
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        json={"amount": amount_paise, "currency": "INR", "receipt": receipt},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _mark_paid(db: Session, payment: Payment, razorpay_payment_id: str) -> None:
    """Idempotent: safe to call twice for the same payment."""
    if payment.status != "paid":
        payment.status = "paid"
        payment.razorpay_payment_id = razorpay_payment_id
        payment.paid_at = datetime.now(timezone.utc)
    user = db.get(User, payment.user_id)
    if user is not None:
        user.is_pro = True
    db.commit()


@router.post("/create-order", response_model=OrderOut)
def create_order(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.is_pro:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already on the Pro plan")
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are not configured")

    amount = settings.pro_price_paise  # decided here, on the server
    try:
        order = create_razorpay_order(amount, receipt=f"pro-user-{user.id}")
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Payment provider is unavailable")

    db.add(Payment(user_id=user.id, razorpay_order_id=order["id"], amount_paise=amount))
    db.commit()
    return OrderOut(
        order_id=order["id"],
        key_id=settings.razorpay_key_id,
        amount=amount,
        currency="INR",
    )


@router.post("/verify")
def verify_payment(
    payload: VerifyPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # the order must exist AND belong to the logged-in user
    payment = db.scalar(
        select(Payment).where(
            Payment.razorpay_order_id == payload.razorpay_order_id,
            Payment.user_id == user.id,
        )
    )
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    # Razorpay's rule: signature = HMAC_SHA256(order_id + "|" + payment_id, key_secret)
    expected = _sign(
        f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}",
        settings.razorpay_key_secret,
    )
    if not hmac.compare_digest(expected, payload.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payment signature")

    _mark_paid(db, payment, payload.razorpay_payment_id)
    return {"is_pro": True}


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    # Webhooks are called by Razorpay, not by a logged-in user, so there is no JWT.
    # The signature (over the RAW request body) is the only proof of who is calling.
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook is not configured")

    raw_body = await request.body()  # must be the exact bytes Razorpay signed
    expected = _sign(raw_body, settings.razorpay_webhook_secret)
    if not hmac.compare_digest(expected, x_razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")

    event = json.loads(raw_body)
    if event.get("event") in ("payment.captured", "order.paid"):
        entity = event["payload"]["payment"]["entity"]
        payment = db.scalar(
            select(Payment).where(Payment.razorpay_order_id == entity["order_id"])
        )
        if payment is not None:
            _mark_paid(db, payment, entity["id"])

    # always answer 200 for valid events, otherwise Razorpay keeps retrying
    return {"status": "ok"}
