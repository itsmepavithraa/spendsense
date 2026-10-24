"""Teaching the app a category once: it fixes old rows and is used for every future one."""
from tests.conftest import register_and_login, token_of
from tests.test_import_api import upload

SHOP = "Qwerty Traders"  # unknown to the keyword rules and the model, so it starts Uncategorized


def add(client, headers, merchant=SHOP, amount=100, **extra):
    r = client.post("/transactions", json={"merchant": merchant, "amount": amount, **extra}, headers=headers)
    assert r.status_code == 201
    return r.json()


def correct(client, headers, merchant, category):
    return client.put("/merchants/category", json={"merchant": merchant, "category": category}, headers=headers)


def test_a_correction_fixes_every_existing_row_of_that_merchant(client):
    headers = register_and_login(client)
    for amount in (100, 150, 200):
        assert add(client, headers, amount=amount)["category"] == "Uncategorized"
    add(client, headers, merchant="Someone Else", amount=50)

    r = correct(client, headers, SHOP, "Groceries")
    assert r.status_code == 200
    assert r.json() == {"merchant": SHOP, "category": "Groceries", "updated": 3}

    rows = client.get("/transactions?limit=50", headers=headers).json()
    by_merchant = {(t["merchant"], t["category"]) for t in rows}
    assert by_merchant == {(SHOP, "Groceries"), ("Someone Else", "Uncategorized")}  # only that shop


def test_matching_ignores_capitals_and_extra_spaces(client):
    headers = register_and_login(client)
    add(client, headers, merchant="Qwerty  TRADERS ")
    add(client, headers, merchant="qwerty traders")
    assert correct(client, headers, "QWERTY TRADERS", "Shopping").json()["updated"] == 2


def test_new_transactions_use_the_remembered_category(client):
    headers = register_and_login(client)
    correct(client, headers, SHOP, "Health")
    assert add(client, headers)["category"] == "Health"  # no category sent: memory is used
    assert add(client, headers, category="Groceries")["category"] == "Groceries"  # explicit choice still wins


def test_future_imports_use_the_remembered_category(client):
    headers = register_and_login(client)
    correct(client, headers, "Qwerty Traders", "Groceries")
    text = "Date,Narration,Debit\n01/10/2026,UPI-QWERTY TRADERS-9876543210@YBL-UTIB0000000-402918374652-UPI,300\n"
    body = upload(client, headers, text).json()
    assert body["preview"][0]["category"] == "Groceries"
    assert body["uncategorized"] == 0


def test_a_correction_overrides_keyword_rules_and_the_model(client):
    headers = register_and_login(client)
    assert add(client, headers, merchant="Swiggy")["category"] == "Food & Dining"  # the model's answer
    correct(client, headers, "Swiggy", "Entertainment")  # this user disagrees
    assert add(client, headers, merchant="Swiggy")["category"] == "Entertainment"


def test_a_later_correction_replaces_an_earlier_one(client):
    headers = register_and_login(client)
    correct(client, headers, SHOP, "Groceries")
    correct(client, headers, SHOP, "Transport")
    assert add(client, headers)["category"] == "Transport"


def test_the_unusual_flag_is_recomputed_for_the_new_category(client):
    headers = register_and_login(client)
    big = add(client, headers, amount=25000)
    assert big["category"] == "Uncategorized" and big["is_anomaly"] is False  # no baseline, no judgement
    correct(client, headers, SHOP, "Food & Dining")  # ₹25,000 on food is far from normal
    row = client.get(f"/transactions/{big['id']}", headers=headers).json()
    assert row["category"] == "Food & Dining" and row["is_anomaly"] is True


def test_unknown_categories_are_rejected(client):
    headers = register_and_login(client)
    assert correct(client, headers, SHOP, "Spaceships").status_code == 422
    assert correct(client, headers, "", "Groceries").status_code == 422


def test_corrections_are_private_to_each_user(client):
    alice = register_and_login(client, "alice@test.com")
    bob = register_and_login(client, "bob@test.com")
    add(client, alice)
    add(client, bob)
    correct(client, alice, SHOP, "Groceries")
    assert add(client, bob)["category"] == "Uncategorized"  # Bob's shop is untouched
    bob_rows = client.get("/transactions", headers=bob).json()
    assert {t["category"] for t in bob_rows} == {"Uncategorized"}


def test_needs_a_category_list_is_grouped_and_biggest_first(client):
    headers = register_and_login(client)
    add(client, headers, merchant="Small Shop", amount=10)
    add(client, headers, merchant="Big Shop", amount=900)
    add(client, headers, merchant="BIG SHOP", amount=100)  # same shop, different capitals
    add(client, headers, merchant="Swiggy", amount=500)  # categorised: must not appear
    listing = client.get("/merchants/uncategorized", headers=headers).json()
    # one entry per shop (capitals ignored), summed, biggest total first
    assert [(m["merchant"].lower(), m["count"], m["total"]) for m in listing] == [
        ("big shop", 2, 1000.0),
        ("small shop", 1, 10.0),
    ]
    correct(client, headers, "Big Shop", "Shopping")
    after = client.get("/merchants/uncategorized", headers=headers).json()
    assert [m["merchant"] for m in after] == ["Small Shop"]


def test_corrections_need_login(client):
    assert client.put("/merchants/category", json={"merchant": "x", "category": "Groceries"}).status_code == 401
    assert client.get("/merchants/uncategorized").status_code == 401


def test_other_open_tabs_are_told(client):
    headers = register_and_login(client)
    add(client, headers)
    with client.websocket_connect(f"/ws?token={token_of(headers)}") as ws:
        ws.receive_json()  # "connected"
        correct(client, headers, SHOP, "Groceries")
        event = ws.receive_json()
        assert event["type"] == "transactions.recategorized"
        assert event["data"]["count"] == 1 and event["data"]["category"] == "Groceries"
