"""Authentication, per-user data isolation and transaction CRUD."""
from tests.conftest import register_and_login


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# ---------- authentication ----------
def test_register_login_and_me(client):
    headers = register_and_login(client, "Ada@Test.com")
    me = client.get("/auth/me", headers=headers).json()
    assert me["email"] == "ada@test.com"  # emails are normalised to lowercase
    assert me["is_pro"] is False
    assert "password" not in str(me).lower()  # the hash never leaks into responses


def test_duplicate_email_is_rejected(client):
    register_and_login(client, "dup@test.com")
    r = client.post(
        "/auth/register",
        json={"email": "DUP@test.com", "full_name": "X", "password": "password123"},
    )
    assert r.status_code == 409


def test_wrong_password_and_unknown_user_look_identical(client):
    register_and_login(client, "real@test.com")
    wrong = client.post("/auth/login", data={"username": "real@test.com", "password": "nope-nope"})
    unknown = client.post("/auth/login", data={"username": "ghost@test.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # no hint about which emails exist


def test_short_password_is_rejected(client):
    r = client.post(
        "/auth/register",
        json={"email": "a@test.com", "full_name": "A", "password": "short"},
    )
    assert r.status_code == 422


def test_protected_routes_need_a_valid_token(client):
    assert client.get("/transactions").status_code == 401
    assert client.get("/transactions", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ---------- transactions ----------
def test_crud_flow(client):
    headers = register_and_login(client)
    created = client.post(
        "/transactions",
        json={"amount": 250.5, "merchant": "Swiggy", "category": "Food & Dining"},
        headers=headers,
    )
    assert created.status_code == 201
    txn = created.json()
    assert txn["amount"] == "250.50"  # money is returned as an exact string

    assert client.get(f"/transactions/{txn['id']}", headers=headers).json()["merchant"] == "Swiggy"

    patched = client.patch(f"/transactions/{txn['id']}", json={"category": "Groceries"}, headers=headers)
    assert patched.json()["category"] == "Groceries"
    assert patched.json()["merchant"] == "Swiggy"  # untouched fields stay as they were

    assert client.delete(f"/transactions/{txn['id']}", headers=headers).status_code == 204
    assert client.get(f"/transactions/{txn['id']}", headers=headers).status_code == 404


def test_invalid_amounts_are_rejected(client):
    headers = register_and_login(client)
    for bad in (0, -5, "abc"):
        r = client.post("/transactions", json={"amount": bad, "merchant": "X"}, headers=headers)
        assert r.status_code == 422, bad


def test_users_cannot_see_or_change_each_others_data(client):
    alice = register_and_login(client, "alice@test.com")
    bob = register_and_login(client, "bob@test.com")
    txn_id = client.post(
        "/transactions", json={"amount": 100, "merchant": "Uber"}, headers=alice
    ).json()["id"]

    # 404, not 403: don't even reveal that the id exists
    assert client.get(f"/transactions/{txn_id}", headers=bob).status_code == 404
    assert client.patch(f"/transactions/{txn_id}", json={"merchant": "Hacked"}, headers=bob).status_code == 404
    assert client.delete(f"/transactions/{txn_id}", headers=bob).status_code == 404
    assert client.get("/transactions", headers=bob).json() == []
    # and Alice's data is intact
    assert client.get(f"/transactions/{txn_id}", headers=alice).json()["merchant"] == "Uber"


def test_filtering_and_pagination(client):
    headers = register_and_login(client)
    for i in range(5):
        client.post("/transactions", json={"amount": 10 + i, "merchant": "Uber"}, headers=headers)
    client.post("/transactions", json={"amount": 99, "merchant": "Netflix"}, headers=headers)

    assert len(client.get("/transactions?limit=2", headers=headers).json()) == 2
    assert len(client.get("/transactions?limit=100&offset=4", headers=headers).json()) == 2
    transport = client.get("/transactions?category=Transport&limit=100", headers=headers).json()
    assert len(transport) == 5 and all(t["category"] == "Transport" for t in transport)
    assert client.get("/transactions?limit=0", headers=headers).status_code == 422  # bounds enforced
    assert client.get("/transactions?limit=100000", headers=headers).status_code == 422
