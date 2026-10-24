"""Excel statements, including password-protected ones (invented rows only)."""

import io
from datetime import datetime

import pytest
from openpyxl import Workbook

from app.importer import StatementError, parse_statement
from app.spreadsheet import is_spreadsheet, spreadsheet_to_csv
from msoffcrypto.format.ooxml import OOXMLFile
from tests.conftest import register_and_login

HEADER = ["Txn Date", "Description", "Withdrawal Amt", "Deposit Amt", "Balance"]
ROWS = [
    [datetime(2026, 9, 24, 7, 24, 3), "UPI/Raju Tea Stall/123", 40.0, None, 960.5],
    [datetime(2026, 9, 25), "UPI/Swiggy Order/456", 349.0, None, 600],
    [datetime(2026, 9, 26), "Salary Credit", None, 50000, 50600],
]


def make_xlsx() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["Account statement"])  # junk above the header, as banks do
    sheet.append(HEADER)
    for row in ROWS:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def lock(plain: bytes, password: str) -> bytes:
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(plain)).encrypt(password, out)
    return out.getvalue()


def test_plain_xlsx_is_converted_and_parsed():
    content = make_xlsx()
    assert is_spreadsheet(content)
    result = parse_statement(spreadsheet_to_csv(content))
    assert [r.amount for r in result.rows] == [40, 349]
    assert result.credits_ignored == 1


def test_locked_xlsx_needs_the_right_password():
    locked = lock(make_xlsx(), "secret-123")
    with pytest.raises(StatementError, match="password-protected"):
        spreadsheet_to_csv(locked)
    with pytest.raises(StatementError, match="Could not unlock"):
        spreadsheet_to_csv(locked, "wrong")
    result = parse_statement(spreadsheet_to_csv(locked, "secret-123"))
    assert len(result.rows) == 2


def test_garbage_that_looks_like_a_zip_is_refused_politely():
    with pytest.raises(StatementError):
        spreadsheet_to_csv(b"PK\x03\x04 not really a zip")


def test_import_endpoint_accepts_locked_excel(client):
    headers = register_and_login(client, "excel@example.com")
    locked = lock(make_xlsx(), "secret-123")
    files = {"file": ("statement.xlsx", locked, "application/octet-stream")}

    no_password = client.post("/transactions/import", files=files, headers=headers)
    assert no_password.status_code == 400
    assert "password" in no_password.json()["detail"].lower()

    wrong = client.post("/transactions/import", files=files, data={"password": "nope"}, headers=headers)
    assert wrong.status_code == 400

    ok = client.post("/transactions/import", files=files, data={"password": "secret-123"}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["imported"] == 2
