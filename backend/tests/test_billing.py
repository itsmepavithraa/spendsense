"""Payment tests. Razorpay's server is faked; the signature math is the real thing."""
import hashlib
import hmac
import json

import pytest

from tests.conftest import register_and_login, requires_postgres

KEY_SECRET = "test_key_secret"
WEBHOOK_SECRET = "test_webhook_secret"


def sign(message: str | bytes, secret: str) -> str:
    if isinstance(message, str):
        message = message.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def fake_razorpay(monkeypatch):
    """Replace the network call with a fixed order id."""
    from app.routers import billing

    monkeypatch.setattr(
        billing, "create_razorpay_order", lambda amount, receipt: {"id": "order_TEST1"}
    )


def start_order(client, headers):
    return client.post("/billing/create-order", headers=headers)


def is_pro(client, headers) -> bool:
    return client.get("/auth/me", headers=headers).json()["is_pro"]


def webhook(client, event: dict, secret: str = WEBHOOK_SECRET):
    raw = json.dumps(event).encode()
    return client.post(
        "/billing/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": sign(raw, secret), "Content-Type": "application/json"},
    )


PAID_EVENT = {
    "event": "payment.captured",
    "payload": {"payment": {"entity": {"id": "pay_TEST1", "order_id": "order_TEST1"}}},
}


def test_server_chooses_the_price(client):
    headers = register_and_login(client)
    body = start_order(client, headers).json()
    assert body["order_id"] == "order_TEST1"
    assert body["amount"] == 19900  # ₹199 in paise, set by the server
    assert body["key_id"] == "rzp_test_key"
    assert "secret" not in json.dumps(body).lower()  # the secret key never leaves the server


def test_valid_signature_upgrades_user(client):
    headers = register_and_login(client)
    start_order(client, headers)
    r = client.post(
        "/billing/verify",
        headers=headers,
        json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_TEST1",
            "razorpay_signature": sign("order_TEST1|pay_TEST1", KEY_SECRET),
        },
    )
    assert r.status_code == 200
    assert is_pro(client, headers)


def test_forged_signature_is_rejected(client):
    headers = register_and_login(client)
    start_order(client, headers)
    r = client.post(
        "/billing/verify",
        headers=headers,
        json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_TEST1",
            "razorpay_signature": sign("order_TEST1|pay_TEST1", "attacker-guess"),
        },
    )
    assert r.status_code == 400
    assert not is_pro(client, headers)


def test_cannot_verify_someone_elses_order(client):
    owner = register_and_login(client, "owner@test.com")
    thief = register_and_login(client, "thief@test.com")
    start_order(client, owner)
    r = client.post(
        "/billing/verify",
        headers=thief,
        json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_TEST1",
            "razorpay_signature": sign("order_TEST1|pay_TEST1", KEY_SECRET),
        },
    )
    assert r.status_code == 404
    assert not is_pro(client, thief)


def test_webhook_upgrades_user_even_if_browser_never_calls_back(client):
    headers = register_and_login(client)
    start_order(client, headers)
    assert webhook(client, PAID_EVENT).status_code == 200
    assert is_pro(client, headers)


def test_webhook_with_bad_signature_is_rejected(client):
    headers = register_and_login(client)
    start_order(client, headers)
    assert webhook(client, PAID_EVENT, secret="wrong").status_code == 400
    assert not is_pro(client, headers)


def test_webhook_and_verify_together_are_harmless(client):
    headers = register_and_login(client)
    start_order(client, headers)
    webhook(client, PAID_EVENT)
    r = client.post(
        "/billing/verify",
        headers=headers,
        json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_TEST1",
            "razorpay_signature": sign("order_TEST1|pay_TEST1", KEY_SECRET),
        },
    )
    assert r.status_code == 200  # second arrival is idempotent
    assert is_pro(client, headers)


def test_pro_users_cannot_buy_again(client):
    headers = register_and_login(client)
    start_order(client, headers)
    webhook(client, PAID_EVENT)
    assert start_order(client, headers).status_code == 409


def test_payments_disabled_without_keys(client, monkeypatch):
    from app.routers import billing

    monkeypatch.setattr(billing.settings, "razorpay_key_id", "")
    headers = register_and_login(client)
    assert start_order(client, headers).status_code == 503


@requires_postgres
def test_csv_export_does_not_leak_database_connections(client):
    """Regression test: the streaming export once reused a closed session, leaving a
    connection 'idle in transaction' (holding locks) after every download."""
    from sqlalchemy import text

    from app.database import engine

    headers = register_and_login(client)
    client.post("/transactions", json={"amount": 420, "merchant": "Swiggy"}, headers=headers)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_pro = true"))

    for _ in range(3):
        assert client.get("/transactions/export", headers=headers).status_code == 200

    with engine.connect() as conn:
        stuck = conn.execute(
            text(
                "SELECT COUNT(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND state = 'idle in transaction' "
                "AND pid <> pg_backend_pid()"
            )
        ).scalar()
    assert stuck == 0


def test_csv_export_is_pro_only(client):
    headers = register_and_login(client)
    client.post("/transactions", json={"amount": 420, "merchant": "Swiggy"}, headers=headers)

    assert client.get("/transactions/export", headers=headers).status_code == 402  # free plan

    start_order(client, headers)
    webhook(client, PAID_EVENT)
    r = client.get("/transactions/export", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "date,merchant,category,amount,unusual"
    assert "Swiggy" in lines[1]
