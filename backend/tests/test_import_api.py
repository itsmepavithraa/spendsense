"""The statement upload endpoint: saving, categorising, de-duplicating and staying safe."""
from tests.conftest import register_and_login, requires_postgres, token_of
from tests.test_importer import HDFC_STYLE


def upload(client, headers, text: str | bytes, name: str = "statement.csv"):
    content = text.encode() if isinstance(text, str) else text
    return client.post(
        "/transactions/import", headers=headers, files={"file": (name, content, "text/csv")}
    )


def test_importing_a_statement_saves_categorises_and_summarises(client):
    headers = register_and_login(client)
    r = upload(client, headers, HDFC_STYLE)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 3
    assert body["credits_ignored"] == 1  # the salary is not spending
    assert body["invalid_rows"] == 0
    assert body["duplicates_skipped"] == 0
    assert body["date_from"] == "2026-10-01" and body["date_to"] == "2026-10-04"
    assert body["columns"]["description"] == "Narration"  # shows what was detected
    assert body["preview"][0]["merchant"] == "Swiggy"
    assert body["preview"][0]["category"] == "Food & Dining"

    stored = client.get("/transactions?limit=50", headers=headers).json()
    assert len(stored) == 3
    assert {t["merchant"] for t in stored} == {"Swiggy", "Amazon Pay", "Mg Road"}


def test_unfamiliar_merchants_are_left_uncategorized_not_guessed(client):
    headers = register_and_login(client)
    text = "Date,Narration,Debit\n01/10/2026,UPI-RAMESH TRADERS-9876543210@YBL-UTIB0000000-402918374652-UPI,300\n"
    body = upload(client, headers, text).json()
    assert body["uncategorized"] == 1
    assert body["preview"][0]["category"] == "Uncategorized"


def test_uploading_the_same_statement_twice_adds_nothing(client):
    headers = register_and_login(client)
    assert upload(client, headers, HDFC_STYLE).json()["imported"] == 3
    again = upload(client, headers, HDFC_STYLE).json()
    assert again["imported"] == 0
    assert again["duplicates_skipped"] == 3
    assert len(client.get("/transactions?limit=50", headers=headers).json()) == 3


def test_two_identical_purchases_on_one_day_are_both_kept(client):
    headers = register_and_login(client)
    two_coffees = "Date,Narration,Debit\n01/10/2026,STARBUCKS,250\n01/10/2026,STARBUCKS,250\n"
    assert upload(client, headers, two_coffees).json()["imported"] == 2  # genuinely two purchases

    three = two_coffees + "01/10/2026,STARBUCKS,250\n"  # a later, longer export of the same day
    body = upload(client, headers, three).json()
    assert body["duplicates_skipped"] == 2 and body["imported"] == 1  # only the new one is added


@requires_postgres
def test_two_simultaneous_uploads_of_one_file_never_duplicate_rows(client):
    """Regression test for a real race: both requests checked for duplicates before either
    had saved, so every row was stored twice. A per-user lock now makes them queue."""
    from concurrent.futures import ThreadPoolExecutor

    headers = register_and_login(client)
    rows = 1500  # big enough that the two requests genuinely overlap in time
    text = "Date,Narration,Debit\n" + "".join(
        f"{1 + i % 28:02d}/09/2026,UPI-SWIGGY-SWIGGY@ICICI-ICIC0000001-{i:012d}-ORDER,{100 + i * 0.5}\n"
        for i in range(rows)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda _: upload(client, headers, text).json(), range(2))

    assert first["imported"] + second["imported"] == rows
    assert first["duplicates_skipped"] + second["duplicates_skipped"] == rows
    total = client.get("/analytics/summary", headers=headers).json()["transaction_count"]
    assert total == rows


def test_each_user_has_their_own_history_for_deduplication(client):
    alice = register_and_login(client, "alice@test.com")
    bob = register_and_login(client, "bob@test.com")
    assert upload(client, alice, HDFC_STYLE).json()["imported"] == 3
    assert upload(client, bob, HDFC_STYLE).json()["imported"] == 3  # Alice's rows don't count for Bob
    assert len(client.get("/transactions", headers=bob).json()) == 3


def test_an_unusually_large_row_is_flagged(client):
    headers = register_and_login(client)
    text = "Date,Narration,Debit\n01/10/2026,UPI-SWIGGY-SWIGGY@ICICI-ICIC0000001-402918374652-ORDER,25000\n"
    body = upload(client, headers, text).json()
    assert body["unusual"] == 1 and body["preview"][0]["is_anomaly"] is True


def test_import_notifies_the_open_dashboard(client):
    headers = register_and_login(client)
    with client.websocket_connect(f"/ws?token={token_of(headers)}") as ws:
        ws.receive_json()  # "connected"
        upload(client, headers, HDFC_STYLE)
        event = ws.receive_json()
        assert event["type"] == "transactions.imported"
        assert event["data"]["count"] == 3


def test_bad_uploads_get_clear_errors(client):
    headers = register_and_login(client)
    assert upload(client, headers, "Name,Age\nAda,36\n").status_code == 400
    assert "column headings" in upload(client, headers, "Name,Age\nAda,36\n").json()["detail"]
    assert upload(client, headers, b"").status_code == 400
    assert upload(client, headers, bytes(range(256)) * 50).status_code == 400  # binary junk
    too_big = b"Date,Narration,Debit\n" + b"01/10/2026,Uber,100\n" * 120_000
    assert upload(client, headers, too_big).status_code == 413
    assert client.get("/transactions", headers=headers).json() == []  # nothing half-saved


def test_upload_requires_login(client):
    r = client.post("/transactions/import", files={"file": ("s.csv", b"Date,Narration,Debit\n", "text/csv")})
    assert r.status_code == 401


def test_dangerous_merchant_names_cannot_become_spreadsheet_formulas(client):
    from app.database import SessionLocal
    from app.models import User

    headers = register_and_login(client)
    client.post("/transactions", json={"amount": 10, "merchant": "=HYPERLINK(\"http://evil\",\"x\")"}, headers=headers)
    client.post("/transactions", json={"amount": 10, "merchant": "@SUM(1+1)"}, headers=headers)
    with SessionLocal() as db:
        db.query(User).update({"is_pro": True})
        db.commit()

    exported = client.get("/transactions/export", headers=headers).text
    for line in exported.splitlines()[1:]:
        merchant_cell = line.split(",", 2)[1].lstrip('"')
        assert merchant_cell[0] not in "=+-@"  # defanged with a leading quote
    # and the import path strips them before they are ever stored
    text = 'Date,Narration,Debit\n01/10/2026,"=CMD|calc",5\n'
    upload(client, headers, text)
    merchants = {t["merchant"] for t in client.get("/transactions?limit=10", headers=headers).json()}
    assert "Cmd" in merchants  # "=CMD|calc" arrives as "Cmd", the leading "=" stripped
