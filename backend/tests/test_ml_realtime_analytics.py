"""ML predictions, the real-time WebSocket feed, the simulator and analytics."""
import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import register_and_login, requires_postgres, token_of


# ---------- ML ----------
@pytest.mark.parametrize(
    "merchant, category",
    [
        ("Swiggy", "Food & Dining"),
        ("Zomato Gold", "Food & Dining"),  # a merchant variant the model never saw
        ("Uber", "Transport"),
        ("Netflix", "Subscriptions"),
        ("Amazon Books", "Education"),  # similar name, different category than "Amazon"
    ],
)
def test_category_is_predicted_from_the_merchant(client, merchant, category):
    headers = register_and_login(client)
    r = client.post("/transactions", json={"amount": 300, "merchant": merchant}, headers=headers)
    assert r.json()["category"] == category


def test_explicit_category_wins_over_the_model(client):
    headers = register_and_login(client)
    r = client.post(
        "/transactions",
        json={"amount": 300, "merchant": "Swiggy", "category": "Groceries"},
        headers=headers,
    )
    assert r.json()["category"] == "Groceries"


def test_unusually_large_amounts_are_flagged(client):
    headers = register_and_login(client)
    normal = client.post("/transactions", json={"amount": 420, "merchant": "Swiggy"}, headers=headers)
    huge = client.post("/transactions", json={"amount": 9500, "merchant": "Swiggy"}, headers=headers)
    assert normal.json()["is_anomaly"] is False
    assert huge.json()["is_anomaly"] is True


# ---------- real time ----------
def test_websocket_rejects_a_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws?token=garbage"):
            pass
    assert exc.value.code == 1008


def test_live_events_reach_the_owner_only(client):
    alice = register_and_login(client, "alice@test.com")
    bob = register_and_login(client, "bob@test.com")

    with client.websocket_connect(f"/ws?token={token_of(alice)}") as ws_alice, client.websocket_connect(
        f"/ws?token={token_of(bob)}"
    ) as ws_bob:
        assert ws_alice.receive_json()["type"] == "connected"
        assert ws_bob.receive_json()["type"] == "connected"

        client.post("/transactions", json={"amount": 420, "merchant": "Swiggy"}, headers=alice)
        event = ws_alice.receive_json()
        assert event["type"] == "transaction.created"
        assert event["data"]["merchant"] == "Swiggy"
        assert event["data"]["category"] == "Food & Dining"

        # Bob's own activity is the first thing Bob sees: Alice's never reached him
        client.post("/transactions", json={"amount": 100, "merchant": "Uber"}, headers=bob)
        bob_event = ws_bob.receive_json()
        assert bob_event["data"]["merchant"] == "Uber"


def test_anomaly_sends_a_second_alert_event(client):
    headers = register_and_login(client)
    with client.websocket_connect(f"/ws?token={token_of(headers)}") as ws:
        ws.receive_json()  # "connected"
        client.post("/transactions", json={"amount": 14000, "merchant": "Uber"}, headers=headers)
        first, second = ws.receive_json(), ws.receive_json()
        assert first["type"] == "transaction.created"
        assert second["type"] == "anomaly.alert"
        assert "Uber" in second["data"]["message"]


def test_simulator_streams_transactions_until_stopped(client):
    headers = register_and_login(client)
    with client.websocket_connect(f"/ws?token={token_of(headers)}") as ws:
        ws.receive_json()
        assert client.post("/simulate/start?interval=0.5", headers=headers).json()["status"] == "started"
        assert client.post("/simulate/start?interval=0.5", headers=headers).json()["status"] == "already running"
        events = []
        while len(events) < 2:  # skip any anomaly alerts, wait for two transactions
            message = ws.receive_json()
            if message["type"] == "transaction.created":
                events.append(message)
        assert client.post("/simulate/stop", headers=headers).json()["status"] == "stopped"
    assert client.post("/simulate/stop", headers=headers).json()["status"] == "not running"


# ---------- analytics ----------
def test_summary_numbers_add_up(client):
    headers = register_and_login(client)
    for amount, merchant in [(100, "Swiggy"), (200, "Swiggy"), (50, "Uber")]:
        client.post("/transactions", json={"amount": amount, "merchant": merchant}, headers=headers)

    summary = client.get("/analytics/summary", headers=headers).json()
    assert summary["total_spend"] == 350
    assert summary["transaction_count"] == 3
    assert summary["anomaly_count"] == 0
    assert summary["by_category"][0] == {"category": "Food & Dining", "total": 300}  # biggest first
    assert summary["monthly"][-1]["total"] == 350  # all of it falls in the current month


def test_summary_is_per_user(client):
    alice = register_and_login(client, "alice@test.com")
    bob = register_and_login(client, "bob@test.com")
    client.post("/transactions", json={"amount": 100, "merchant": "Swiggy"}, headers=alice)
    assert client.get("/analytics/summary", headers=bob).json()["transaction_count"] == 0


@requires_postgres
def test_monthly_charges_are_detected_as_a_subscription(client):
    headers = register_and_login(client)
    for days_ago in (90, 60, 30, 0):  # Netflix, same amount, every 30 days
        client.post(
            "/transactions",
            json={"amount": 649, "merchant": "Netflix", "occurred_at": _days_ago(days_ago)},
            headers=headers,
        )
    # same amount but at random gaps: must NOT count as a subscription
    for days_ago in (200, 150, 149, 20):
        client.post(
            "/transactions",
            json={"amount": 900, "merchant": "Cafe Coffee Day", "occurred_at": _days_ago(days_ago)},
            headers=headers,
        )

    found = client.get("/analytics/subscriptions", headers=headers).json()
    assert [s["merchant"] for s in found] == ["Netflix"]
    assert found[0]["charges"] == 4
    assert found[0]["yearly_cost"] == 649 * 12


def _days_ago(days: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
