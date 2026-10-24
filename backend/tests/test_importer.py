"""Statement parsing: column detection, amounts, dates and merchant cleaning.

All data here is invented. The layouts imitate how real Indian bank exports look.
"""
from decimal import Decimal

import pytest

from app.importer import StatementError, clean_merchant, parse_amount, parse_date, parse_statement

HDFC_STYLE = """HDFC BANK LTD
Account Branch :MG ROAD
Statement From : 01/10/2026 To : 31/10/2026

Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/10/26,UPI-SWIGGY-SWIGGY@ICICI-ICIC0000001-402918374652-PAYMENT FOR ORDER,0000402918374652,01/10/26,420.00,,10580.00
02/10/26,NEFT-HDFCN52026-ACME CORP-SALARY,N001,02/10/26,,50000.00,60580.00
03/10/26,POS 456789XXXXXX1234 AMAZON PAY IN,0000000,03/10/26,"1,299.00",,59281.00
04/10/26,ATM WDL 1234 MG ROAD,0001234,04/10/26,"5,000.00",,54281.00

Closing balance and notes appear down here
"""


# ---------------------------------------------------------------- whole files
def test_debit_credit_layout_with_a_preamble():
    result = parse_statement(HDFC_STYLE.encode())
    assert [(r.merchant, r.amount) for r in result.rows] == [
        ("Swiggy", Decimal("420.00")),
        ("Amazon Pay", Decimal("1299.00")),
        ("Mg Road", Decimal("5000.00")),
    ]
    assert result.credits_ignored == 1  # the salary
    assert result.invalid == []  # footer lines are not transactions, not errors
    assert result.rows[0].occurred_at.date().isoformat() == "2026-10-01"  # day-first
    assert result.columns["amount"] == "Withdrawal Amt."


def test_signed_amount_column_treats_negatives_as_spending():
    text = "Date,Description,Amount\n2026-10-01,Starbucks,-250.00\n2026-10-02,Salary,50000.00\n2026-10-03,Uber,-120.50\n"
    result = parse_statement(text.encode())
    assert [r.amount for r in result.rows] == [Decimal("250.00"), Decimal("120.50")]
    assert result.credits_ignored == 1
    assert result.assumed_all_expenses is False


def test_all_positive_amounts_are_assumed_to_be_spending_and_flagged():
    text = "Transaction Date;Description;Amount (INR)\n01-10-2026;Swiggy;420\n05-10-2026;Uber;180.5\n"
    result = parse_statement(text.encode())  # semicolons, and a heading with extra words
    assert [r.amount for r in result.rows] == [Decimal("420.00"), Decimal("180.50")]
    assert result.assumed_all_expenses is True  # the user is told we guessed


def test_type_column_decides_debit_or_credit():
    text = "Date,Narration,Amount,Dr/Cr\n01/10/2026,Zomato,300,DR\n02/10/2026,Refund,300,CR\n"
    result = parse_statement(text.encode())
    assert [r.merchant for r in result.rows] == ["Zomato"]
    assert result.credits_ignored == 1


def test_dr_cr_suffix_on_the_amount():
    text = "Date,Particulars,Amount\n01/10/2026,Uber,\"1,250.00 Dr\"\n02/10/2026,Interest,\"5,000.00 Cr\"\n"
    result = parse_statement(text.encode())
    assert [r.amount for r in result.rows] == [Decimal("1250.00")]


def test_unreadable_rows_are_reported_not_fatal():
    text = "Date,Narration,Debit\n01/10/2026,Uber,100\n31/31/2026,Bad Date,50\n02/10/2026,Ola,abc\n03/10/2026,,70\n"
    result = parse_statement(text.encode())
    assert len(result.rows) == 1
    assert len(result.invalid) == 3
    assert result.invalid[0].startswith("line 3")  # tells the user WHERE


def test_utf8_bom_and_latin1_files_are_read():
    text = "Date,Narration,Debit\n01/10/2026,Café Coffee,100\n"
    assert parse_statement(("﻿" + text).encode("utf-8")).rows[0].merchant == "Café Coffee"
    assert parse_statement(text.encode("latin-1")).rows[0].merchant == "Café Coffee"


def test_a_file_without_the_right_columns_is_rejected_clearly():
    with pytest.raises(StatementError, match="column headings"):
        parse_statement(b"Name,Age\nAda,36\n")


def test_header_without_rows_is_rejected():
    with pytest.raises(StatementError, match="no transactions"):
        parse_statement(b"Date,Narration,Debit\n")


# ------------------------------------------------------------------- the pieces
@pytest.mark.parametrize(
    "text, expected",
    [
        ("420", Decimal("420")),
        ("1,23,456.78", Decimal("123456.78")),  # Indian digit grouping
        ("₹ 1,250.50", Decimal("1250.50")),
        ("Rs. 99", Decimal("99")),
        ("-75.25", Decimal("-75.25")),
        ("(75.25)", Decimal("-75.25")),
        ("500 Dr", Decimal("-500")),
        ("500 Cr", Decimal("500")),
        ("", None),
        ("abc", None),
        ("12.3.4", None),
    ],
)
def test_amounts(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text, iso",
    [
        ("31/12/2025", "2025-12-31"),
        ("31/12/25", "2025-12-31"),
        ("31-Dec-2025", "2025-12-31"),
        ("31 Dec 2025", "2025-12-31"),
        ("2025-12-31", "2025-12-31"),
        ("05/06/2025", "2025-06-05"),  # day first: 5 June, not May 6
        ("31/12/2025 14:30:00", "2025-12-31"),
    ],
)
def test_dates(text, iso):
    assert parse_date(text).date().isoformat() == iso


def test_dates_without_a_time_stay_on_the_same_day_in_any_timezone():
    assert parse_date("01/10/2026").hour == 12  # noon UTC is the same date from the US to India


@pytest.mark.parametrize(
    "narration, merchant",
    [
        ("UPI-SWIGGY-SWIGGY@ICICI-ICIC0000001-402918374652-PAYMENT FOR ORDER", "Swiggy"),
        ("UPI/DR/402918374652/SWIGGY/YESB/swiggy@yesb/UPI", "Swiggy"),
        ("UPI/402918374652/Payment from PhonePe/swiggy@ybl/ICICI Bank", "Swiggy"),  # skips the wallet
        ("UPI-RAHUL SHARMA-9876543210@YBL-UTIB0000000-402918374652-UPI", "Rahul Sharma"),
        ("POS 456789XXXXXX1234 AMAZON PAY IN", "Amazon Pay"),
        ("ATM WDL 1234 MG ROAD", "Mg Road"),
        ("IMPS-402918374652-ANITA RAO-HDFC-XXXXXXXX1234-RENT", "Anita Rao"),
        ("NACH DR ZERODHA BROKING LTD", "Zerodha Broking"),
        ("ZOMATO", "Zomato"),
    ],
)
def test_bank_text_is_reduced_to_a_merchant_name(narration, merchant):
    assert clean_merchant(narration) == merchant


def test_unreadable_text_falls_back_instead_of_going_blank():
    assert clean_merchant("1234567890 /// 987654") != ""
    assert len(clean_merchant("x" * 500)) <= 60
