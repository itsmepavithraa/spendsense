"""Bank statement CSV import: finding the columns, reading rows, cleaning merchants.

Every bank exports a slightly different CSV, so nothing here assumes one layout:

* Header row: located by scanning the first lines for recognisable column names
  (statements often start with account-holder details before the real header).
* Amounts: either separate Debit / Credit columns, or one signed Amount column
  (optionally with a Dr/Cr type column).
* Only money SPENT is imported; deposits and credits are counted and ignored.
* Dates are read day-first (31/12/2025), the Indian convention.
* The raw bank text ("UPI-SWIGGY-swiggy@icici-402918-PAYMENT") is reduced to a
  short merchant name ("Swiggy"). The original narration is not stored.

This module only parses. Saving, categorising and de-duplicating happen in the API
endpoint, so the parser is easy to test with plain strings.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation

MAX_FILE_BYTES = 2 * 1024 * 1024  # a year of statements is ~100 KB; 2 MB is generous
MAX_ROWS = 10_000


class StatementError(ValueError):
    """The file can't be used as a statement. The message is safe to show the user."""


# ---------------------------------------------------------------- column names
# Names are compared after normalising (lowercase, punctuation removed). The order
# inside each list is the priority when a file has several matches.
DATE_NAMES = ["transaction date", "txn date", "tran date", "trans date", "date", "posting date", "post date", "value date", "value dt"]
DESC_NAMES = ["narration", "description", "particulars", "transaction details", "transaction description", "transaction remarks", "details", "remarks", "merchant", "payee"]
DEBIT_NAMES = ["withdrawal amt", "withdrawal amount", "withdrawals", "withdrawal", "debit amount", "debit amt", "debit", "dr amount", "dr", "paid out", "money out"]
CREDIT_NAMES = ["deposit amt", "deposit amount", "deposits", "deposit", "credit amount", "credit amt", "credit", "cr amount", "cr", "paid in", "money in"]
AMOUNT_NAMES = ["transaction amount", "txn amount", "amount", "amt"]
TYPE_NAMES = ["dr/cr", "cr/dr", "debit/credit", "transaction type", "txn type", "type"]

DEBIT_MARKERS = {"dr", "d", "debit", "withdrawal", "wd"}
CREDIT_MARKERS = {"cr", "c", "credit", "deposit"}

DATE_FORMATS = [
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d-%b-%Y", "%d-%b-%y",
    "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
]


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ ]", " ", name.lower())).strip()


def _find(columns: dict[str, int], names: list[str]) -> int | None:
    # exact matches first, in priority order...
    for name in names:
        if name in columns:
            return columns[name]
    # ...then headings that START with a known name, e.g. "amount inr" for "amount"
    for name in names:
        for heading, position in columns.items():
            if heading.startswith(name + " "):
                return position
    return None


# ------------------------------------------------------------------ cell parsing
def parse_amount(text: str) -> Decimal | None:
    """'1,23,456.78' -> 123456.78. Negative for '-5', '(5)' or '5 Dr'; None if not a number."""
    s = text.strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    lowered = s.lower().rstrip(".")
    if lowered.endswith("dr"):
        negative, s = True, s[: len(lowered) - 2]
    elif lowered.endswith("cr"):
        s = s[: len(lowered) - 2]
    s = re.sub(r"(?i)(₹|rs\.?|inr)", "", s)
    s = s.replace(",", "").replace(" ", "").strip()
    if s.startswith("-"):
        negative, s = True, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def parse_date(text: str) -> datetime | None:
    """Day-first dates. A date with no time is set to 12:00 UTC so it stays on the same
    calendar day in every timezone."""
    s = re.sub(r"\s+", " ", text.strip())
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if "%H" not in fmt:
            parsed = datetime.combine(parsed.date(), time(12, 0))
        return parsed.replace(tzinfo=timezone.utc)
    return None


# -------------------------------------------------------------- merchant cleaning
# Words that describe HOW money moved rather than WHO it went to.
NOISE_WORDS = {
    "upi", "imps", "neft", "rtgs", "pos", "atm", "ach", "ecs", "nach", "ib", "mb", "bil", "mob",
    "payment", "payments", "paid", "txn", "ref", "via", "to", "from", "by", "for", "in", "on", "the",
    "purchase", "wdl", "debit", "credit", "dr", "cr", "transfer", "bank", "ltd", "limited", "pvt",
    "private", "phone", "cash", "order", "online", "ecom", "pur", "ibl", "ybl", "axl",
    # banks and UPI handles: the bank that processed a payment isn't who was paid
    "icici", "icic", "hdfc", "hdfcbank", "sbi", "sbin", "axis", "utib", "yesb", "kotak", "kkbk",
    "pnb", "punb", "canara", "cnrb", "idfc", "idfb", "indb", "federal", "fdrl", "baroda", "barb",
    "okaxis", "okicici", "okhdfcbank", "oksbi", "apl", "upi",
}
# Payment apps appear in most UPI text but are rarely the merchant; used only as a last resort.
WALLET_WORDS = {"phonepe", "gpay", "googlepay", "google pay", "paytm", "bhim", "amazon pay"}
SEPARATORS = re.compile(r"[/\-*|,;:()\[\]~_]+")
IFSC = re.compile(r"^[a-z]{4}0[a-z0-9]{6}$", re.I)


def _usable_word(word: str) -> bool:
    if "@" in word or len(word) < 2:
        return False
    if IFSC.match(word):
        return False
    if sum(ch.isdigit() for ch in word) >= 4:  # reference numbers, masked card numbers
        return False
    if re.fullmatch(r"[x*]+\d*", word, re.I):
        return False
    return word.lower() not in NOISE_WORDS


def clean_merchant(narration: str) -> str:
    """'UPI-SWIGGY-swiggy@icici-ICIC0000001-402918374652-PAYMENT' -> 'Swiggy'."""
    text = re.sub(r"\s+", " ", narration).strip()
    candidates: list[str] = []

    for segment in SEPARATORS.split(text):
        words = [w for w in segment.split() if _usable_word(w)]
        if words:
            candidates.append(" ".join(words[:3]))

    # the name part of a UPI address (swiggy@icici -> swiggy) is a decent backup
    for vpa in re.findall(r"([A-Za-z][A-Za-z0-9._]{2,})@", text):
        name = re.sub(r"[._]+", " ", vpa).strip()
        if name and not any(ch.isdigit() for ch in name):
            candidates.append(name)

    chosen = next((c for c in candidates if c.lower() not in WALLET_WORDS), None)
    if chosen is None:
        chosen = candidates[0] if candidates else (text[:60] or "Unknown")
    # a leading = + @ - would make a spreadsheet treat the name as a formula
    return chosen.title().lstrip("=+@-\t ")[:60] or "Unknown"


# ------------------------------------------------------------------- the parser
@dataclass
class ParsedRow:
    occurred_at: datetime
    merchant: str
    amount: Decimal  # always positive: money spent


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    credits_ignored: int = 0
    invalid: list[str] = field(default_factory=list)  # human-readable reasons
    columns: dict[str, str] = field(default_factory=dict)  # what we detected, for transparency
    assumed_all_expenses: bool = False


def _decode(content: bytes) -> str:
    # UTF-16 only when the file says so (a byte-order mark): otherwise ordinary
    # Latin-1 bytes can "decode" as UTF-16 into garbage without raising an error.
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return content.decode("utf-16")
        except UnicodeError:
            pass
    try:
        return content.decode("utf-8-sig")
    except UnicodeError:
        return content.decode("latin-1")  # never fails; some banks still export this way


def _read_rows(text: str) -> list[list[str]]:
    if "\x00" in text:  # NUL characters only appear in binary files (PDF, XLSX, images...)
        raise StatementError("That doesn't look like a CSV file. Export the statement as CSV from your bank.")
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    try:
        # newline="" lets the csv module see \r, \n and \r\n line endings as they are
        return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    except csv.Error:
        raise StatementError("The file couldn't be read as a CSV. Check that it is a plain-text export.")


def parse_statement(content: bytes) -> ParseResult:
    rows = _read_rows(_decode(content))
    if len(rows) > MAX_ROWS + 60:
        raise StatementError(f"Too many rows (the limit is {MAX_ROWS:,}). Split the statement into smaller files.")

    # 1. find the header row: needs a date, a description and a debit or amount column
    header_index, found = None, None
    for i, row in enumerate(rows[:60]):
        columns = {}
        for position, cell in enumerate(row):
            columns.setdefault(_normalise(cell), position)
        date_col = _find(columns, DATE_NAMES)
        desc_col = _find(columns, DESC_NAMES)
        debit_col = _find(columns, DEBIT_NAMES)
        amount_col = _find(columns, AMOUNT_NAMES)
        if date_col is not None and desc_col is not None and (debit_col is not None or amount_col is not None):
            header_index = i
            found = {
                "date": date_col,
                "desc": desc_col,
                "debit": debit_col,
                "credit": _find(columns, CREDIT_NAMES),
                "amount": amount_col,
                "type": _find(columns, TYPE_NAMES),
            }
            break
    if header_index is None or found is None:
        raise StatementError(
            "Couldn't find the column headings. The file needs a Date column, a Description/"
            "Narration column and a Debit/Withdrawal or Amount column."
        )

    result = ParseResult()
    header = rows[header_index]
    name_of = lambda col: header[col].strip() if col is not None else ""  # noqa: E731
    result.columns = {
        "date": name_of(found["date"]),
        "description": name_of(found["desc"]),
        "amount": name_of(found["debit"]) or name_of(found["amount"]),
    }
    body = rows[header_index + 1 :]

    def cell(row: list[str], col: int | None) -> str:
        return row[col].strip() if col is not None and col < len(row) else ""

    # 2. with one signed Amount column and no Dr/Cr marker, decide what the signs mean
    use_debit_column = found["debit"] is not None
    negatives_are_expenses = True
    if not use_debit_column and found["type"] is None:
        signed = [parse_amount(cell(r, found["amount"])) for r in body]
        if not any(a is not None and a < 0 for a in signed):
            negatives_are_expenses = False  # all positive: they must all be spending
            result.assumed_all_expenses = True

    # 3. read the rows
    for offset, row in enumerate(body):
        line = header_index + 2 + offset  # 1-based line number in the file
        if not any(c.strip() for c in row):
            continue
        date_text = cell(row, found["date"])
        if not date_text:
            continue  # footers and notes have no date: not a transaction
        occurred_at = parse_date(date_text)
        if occurred_at is None:
            # Text with no digits ("Closing balance...", "Page 1 of 2") is a note, not a
            # transaction with a broken date; only digit-bearing cells are worth reporting.
            if any(ch.isdigit() for ch in date_text) and any(
                parse_amount(cell(row, col)) is not None
                for col in (found["debit"], found["amount"])
                if col is not None
            ):
                result.invalid.append(f"line {line}: unreadable date '{date_text[:20]}'")
            continue

        amount: Decimal | None
        if use_debit_column:
            debit_text = cell(row, found["debit"])
            amount = parse_amount(debit_text)
            if not debit_text:
                result.credits_ignored += 1  # empty Withdrawal cell: money came IN
                continue
            if amount is None:
                result.invalid.append(f"line {line}: unreadable amount '{debit_text[:20]}'")
                continue
            if amount == 0:
                continue
            amount = abs(amount)
        else:
            value = parse_amount(cell(row, found["amount"]))
            if value is None:
                result.invalid.append(f"line {line}: unreadable amount '{cell(row, found['amount'])[:20]}'")
                continue
            marker = _normalise(cell(row, found["type"])) if found["type"] is not None else ""
            if marker in CREDIT_MARKERS:
                result.credits_ignored += 1
                continue
            if marker in DEBIT_MARKERS:
                amount = abs(value)
            elif negatives_are_expenses and value >= 0:
                result.credits_ignored += 1
                continue
            else:
                amount = abs(value)
            if amount == 0:
                continue

        narration = cell(row, found["desc"])
        if not narration:
            result.invalid.append(f"line {line}: no description")
            continue
        if amount >= Decimal("10000000000"):
            result.invalid.append(f"line {line}: amount too large")
            continue
        result.rows.append(ParsedRow(occurred_at, clean_merchant(narration), amount.quantize(Decimal("0.01"))))

    if not result.rows and not result.invalid and not result.credits_ignored:
        raise StatementError("The file has a header but no transactions below it.")
    return result
