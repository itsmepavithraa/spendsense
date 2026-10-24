"""What a site open to the public needs: abuse limits, sign-up controls, data deletion and export."""
import logging

import pytest

from app.config import settings
from app.ratelimit import SlidingWindow
from tests.conftest import register_and_login
from tests.test_import_api import upload

STRONG = "Sunrise-Tea-42!"


@pytest.fixture()
def strict(monkeypatch):
    """Switch the abuse protection ON (the other tests run with it off)."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "password_blocklist_enabled", True)


def sign_up(client, email, password=STRONG, **headers):
    return client.post("/auth/register", json={"email": email, "full_name": "T", "password": password}, headers=headers)


# --------------------------------------------------------------- the limiter itself
class FakeClock:
    now = 1000.0

    def __call__(self):
        return self.now


def test_a_window_allows_its_limit_then_blocks_then_recovers():
    clock = FakeClock()
    window = SlidingWindow(limit=3, window=60, clock=clock)
    assert [window.allow("a") for _ in range(4)] == [True, True, True, False]
    assert window.allow("b") is True  # another visitor is unaffected
    clock.now += 61  # a minute later the old hits no longer count
    assert window.allow("a") is True


def test_blocked_does_not_count_as_a_hit_and_retry_after_is_sensible():
    clock = FakeClock()
    window = SlidingWindow(limit=2, window=60, clock=clock)
    window.record("k"); window.record("k")
    assert window.blocked("k") is True and window.blocked("k") is True  # asking does not extend the block
    clock.now += 20
    assert 39 <= window.retry_after("k") <= 42
    window.reset("k")
    assert window.blocked("k") is False


def test_idle_keys_are_forgotten_so_memory_cannot_grow_forever():
    clock = FakeClock()
    window = SlidingWindow(limit=1, window=10, clock=clock)
    for i in range(500):
        window.allow(f"visitor-{i}")
    assert len(window._hits) == 500  # all recent, all remembered
    clock.now += 11  # they all go quiet
    for _ in range(SlidingWindow.SWEEP_EVERY):  # ordinary traffic from one visitor...
        window.allow("someone-new")
    assert len(window._hits) <= 2  # ...is enough to sweep the 500 stale entries away


# ------------------------------------------------------------ rate limits via the API
def test_signups_are_limited_per_address(client, strict):
    results = [sign_up(client, f"user{i}@test.com").status_code for i in range(6)]
    assert results == [201] * 5 + [429]
    blocked = sign_up(client, "another@test.com")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_forwarded_addresses_are_ignored_unless_the_proxy_is_trusted(client, strict, monkeypatch):
    # not trusted: a faked X-Forwarded-For must not buy a fresh allowance
    codes = [sign_up(client, f"a{i}@test.com", **{"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(6)]
    assert codes[-1] == 429
    # trusted (running behind Render's proxy): the real visitor address is the first entry
    monkeypatch.setattr(settings, "trust_proxy", True)
    assert sign_up(client, "b0@test.com", **{"X-Forwarded-For": "7.7.7.7, 10.0.0.1"}).status_code == 201


def test_five_wrong_passwords_lock_the_account_for_a_while(client, strict):
    sign_up(client, "target@test.com")
    wrong = {"username": "target@test.com", "password": "not-the-password"}
    assert [client.post("/auth/login", data=wrong).status_code for _ in range(5)] == [401] * 5
    locked = client.post("/auth/login", data={"username": "target@test.com", "password": STRONG})
    assert locked.status_code == 429  # even the right password waits: this is what stops guessing
    assert "Retry-After" in locked.headers


def test_a_correct_login_clears_the_failed_attempts(client, strict):
    sign_up(client, "careful@test.com")
    bad = {"username": "careful@test.com", "password": "nope-nope-nope"}
    for _ in range(4):
        client.post("/auth/login", data=bad)
    ok = client.post("/auth/login", data={"username": "careful@test.com", "password": STRONG})
    assert ok.status_code == 200
    for _ in range(4):  # the earlier four no longer count against the next batch
        assert client.post("/auth/login", data=bad).status_code == 401


def test_the_lockout_follows_the_email_not_the_address(client, strict, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy", True)
    sign_up(client, "victim@test.com")
    for i in range(5):  # a guesser rotating through addresses
        client.post("/auth/login", data={"username": "victim@test.com", "password": "guess"}, headers={"X-Forwarded-For": f"5.5.5.{i}"})
    again = client.post("/auth/login", data={"username": "victim@test.com", "password": "guess"}, headers={"X-Forwarded-For": "6.6.6.6"})
    assert again.status_code == 429


# -------------------------------------------------------------- sign-up controls
def test_signups_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)
    assert sign_up(client, "late@test.com").status_code == 403
    assert client.get("/config").json()["registration_open"] is False


def test_signups_stop_at_the_user_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "max_users", 2)
    assert sign_up(client, "one@test.com").status_code == 201
    assert client.get("/config").json()["registration_open"] is True
    assert sign_up(client, "two@test.com").status_code == 201
    full = sign_up(client, "three@test.com")
    assert full.status_code == 403 and "full" in full.json()["detail"]
    assert client.get("/config").json()["registration_open"] is False


def test_the_most_common_passwords_are_refused(client, strict):
    for weak in ("Password123", "12345678", "qwerty123"):
        assert sign_up(client, "weak@test.com", password=weak).status_code == 422
    assert sign_up(client, "strong@test.com").status_code == 201


def test_config_is_public_and_reports_what_is_switched_on(client):
    body = client.get("/config").json()  # no login needed
    assert body["payments_enabled"] is True  # the tests run with Razorpay test keys
    assert body["demo_email"] == "demo@spendsense.com"
    assert body["max_transactions_per_user"] == settings.max_transactions_per_user


def test_csv_export_is_free_when_payments_are_off(client, monkeypatch):
    headers = register_and_login(client)
    client.post("/transactions", json={"amount": 10, "merchant": "Swiggy"}, headers=headers)
    assert client.get("/transactions/export", headers=headers).status_code == 402  # payments on: Pro only
    monkeypatch.setattr(settings, "razorpay_key_id", "")  # payments off: nobody could ever unlock it
    assert client.get("/transactions/export", headers=headers).status_code == 200


# ---------------------------------------------------------------- storage limits
def test_an_account_cannot_exceed_its_transaction_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "max_transactions_per_user", 3)
    headers = register_and_login(client)
    for _ in range(3):
        assert client.post("/transactions", json={"amount": 10, "merchant": "Swiggy"}, headers=headers).status_code == 201
    over = client.post("/transactions", json={"amount": 10, "merchant": "Swiggy"}, headers=headers)
    assert over.status_code == 403 and "limit" in over.json()["detail"]


def test_an_import_that_would_exceed_the_limit_stores_nothing(client, monkeypatch):
    monkeypatch.setattr(settings, "max_transactions_per_user", 3)
    headers = register_and_login(client)
    text = "Date,Narration,Debit\n" + "".join(f"0{i}/10/2026,Shop {i},{10 + i}\n" for i in range(1, 6))
    r = upload(client, headers, text)
    assert r.status_code == 403
    assert client.get("/transactions", headers=headers).json() == []  # not even a partial import


# ------------------------------------------------------------ your data, your choice
def make_account_with_everything(client, email):
    from app.database import SessionLocal
    from app.models import Payment

    headers = register_and_login(client, email)
    client.post("/transactions", json={"amount": 120, "merchant": "Qwerty Traders"}, headers=headers)
    client.put("/merchants/category", json={"merchant": "Qwerty Traders", "category": "Groceries"}, headers=headers)
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        db.add(Payment(user_id=user_id, razorpay_order_id=f"order_{email}", amount_paise=19900))
        db.commit()
    return headers, user_id


def test_a_user_can_download_all_their_own_data(client):
    alice, _ = make_account_with_everything(client, "alice@test.com")
    bob, _ = make_account_with_everything(client, "bob@test.com")
    r = client.get("/auth/me/export", headers=alice)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["email"] == "alice@test.com" and "password" not in str(data).lower()
    assert [t["merchant"] for t in data["transactions"]] == ["Qwerty Traders"]
    assert data["transactions"][0]["amount"] == "120.00"
    assert data["category_corrections"] == [{"merchant": "qwerty traders", "category": "Groceries"}]
    assert [p["order_id"] for p in data["payments"]] == ["order_alice@test.com"]  # never Bob's


def test_deleting_an_account_erases_everything_and_only_that_account(client):
    from app.database import SessionLocal
    from app.models import CategoryOverride, Payment, Transaction, User

    alice, alice_id = make_account_with_everything(client, "alice@test.com")
    bob, bob_id = make_account_with_everything(client, "bob@test.com")

    wrong = client.post("/auth/delete-account", json={"password": "not-it"}, headers=alice)
    assert wrong.status_code == 403
    assert client.get("/auth/me", headers=alice).status_code == 200  # still there

    assert client.post("/auth/delete-account", json={"password": "password123"}, headers=alice).status_code == 204
    assert client.get("/auth/me", headers=alice).status_code == 401  # the old token is now useless
    assert client.post("/auth/login", data={"username": "alice@test.com", "password": "password123"}).status_code == 401

    with SessionLocal() as db:
        for model in (Transaction, CategoryOverride, Payment):
            assert db.query(model).filter(model.user_id == alice_id).count() == 0, model.__name__
            assert db.query(model).filter(model.user_id == bob_id).count() == 1, model.__name__  # Bob untouched
        assert db.get(User, alice_id) is None and db.get(User, bob_id) is not None


def test_deleting_needs_a_login(client):
    assert client.post("/auth/delete-account", json={"password": "x"}).status_code == 401
    assert client.get("/auth/me/export").status_code == 401


# -------------------------------------------------------------- safe logging and headers
def test_login_tokens_are_blanked_out_of_log_lines():
    from app.main import RedactTokens

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "WebSocket %s" [accepted]', ("1.2.3.4", "/ws?token=eyJhbGciOi.secret.sig&x=1"), None)
    RedactTokens().filter(record)
    line = record.getMessage()
    assert "eyJhbGciOi" not in line and "token=REDACTED&x=1" in line


def test_every_response_carries_browser_security_headers(client):
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "max-age" in headers["strict-transport-security"]
