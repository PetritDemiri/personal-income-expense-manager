"""Pasqyrat bankare / Bank statements.

Reading a statement as the bank sends it, rather than asking the user to
convert it first.

TEB sends HTML, which `html.parser` reads without any dependency. Three things
about that file are not obvious and each would break a reasonable parser:

It is UTF-16 little-endian. Read as UTF-8 it produces no tables at all rather
than an error, so an importer would report an empty statement instead of a
problem.

It contains six tables, two of them pages of deposit-insurance boilerplate. The
transactions are found by matching the header row, never by position - a
layout change would otherwise pick a different table in silence.

The totals row has one more cell than the header, so anything assuming a fixed
width misreads it.

What the format gives back is worth more than any of that costs. Every row
carries the running balance, so the parse can be checked against arithmetic the
bank did: apply each row to the opening balance and the result must equal the
balance printed beside it. A statement that does not reconcile is not imported.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from typing import Optional

from .importing import ImportError_, decode, is_deposit, parse_number
from .models import whole_number

# The header that identifies the transactions table. Matched loosely so a
# renamed trailing column does not stop the whole import.
TEB_HEADER = ("data", "shpjegimi")
TEB_COLUMNS = {
    "date": 0,
    "description": 1,
    "currency": 2,
    "debit": 3,
    "credit": 4,
    "balance": 5,
    "reference": 6,
}

# The row that carries the balance brought forward rather than a movement.
OPENING_MARKERS = ("transferimi i bilancit", "balance brought forward", "bilanci fillestar")

# The row that repeats the column totals at the end.
TOTAL_MARKERS = ("totali", "total", "sasia")

DATE_FORMAT = "%d/%m/%Y"


class _TableReader(HTMLParser):
    """Collect every table in a document as lists of cell text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self.tables:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def read_tables(raw):
    """Every table in an HTML document, decoded however it was written."""
    text, _encoding = decode(raw)
    reader = _TableReader()
    reader.feed(text)
    return reader.tables


def looks_like_teb(raw):
    """Whether a file is a TEB statement, without committing to reading it."""
    try:
        return find_statement_table(read_tables(raw)) is not None
    except (ImportError_, ValueError):
        return False


def find_statement_table(tables):
    """The table holding transactions, identified by its header row.

    By header rather than by position: this document also contains three pages
    of legal text laid out as tables, and their order is the bank's business.
    """
    for table in tables:
        if len(table) < 2:
            continue
        header = [cell.strip().casefold() for cell in table[0]]
        if len(header) >= 6 and tuple(header[:2]) == TEB_HEADER:
            return table
    return None


@dataclass
class Statement:
    """A parsed statement, before any of it becomes a transaction."""

    opening: Optional[Decimal] = None
    rows: list = field(default_factory=list)
    stated_debit: Optional[Decimal] = None
    stated_credit: Optional[Decimal] = None
    stated_count: Optional[int] = None

    @property
    def closing(self):
        """The balance after every row, computed rather than read."""
        total = self.opening if self.opening is not None else Decimal("0.00")
        for row in self.rows:
            total += row["signed"]
        return total


def _cell(row, index):
    return row[index].strip() if index < len(row) else ""


def parse_statement(raw):
    """Read a TEB statement into an opening balance, rows, and stated totals."""
    table = find_statement_table(read_tables(raw))
    if table is None:
        raise ImportError_("nuk u gjet tabela e transaksioneve")

    statement = Statement()
    for row in table[1:]:
        description = _cell(row, TEB_COLUMNS["description"]).casefold()
        debit = _cell(row, TEB_COLUMNS["debit"])
        credit = _cell(row, TEB_COLUMNS["credit"])

        if any(marker in description for marker in TOTAL_MARKERS) and not _cell(row, 0):
            statement.stated_debit = parse_number(debit)
            statement.stated_credit = parse_number(credit)
            # The count sits in the last cell, past the header's width.
            for cell in reversed(row):
                count = whole_number(cell.strip())
                if count is not None:
                    statement.stated_count = count
                    break
            continue

        # The opening balance carries neither a debit nor a credit - both cells
        # are empty rather than zero, which is what tells it apart from a
        # movement of exactly nothing.
        if not debit and not credit:
            if any(marker in description for marker in OPENING_MARKERS):
                statement.opening = parse_number(_cell(row, TEB_COLUMNS["balance"]))
            continue

        debit_amount = parse_number(debit) or Decimal("0")
        credit_amount = parse_number(credit) or Decimal("0")
        signed = credit_amount - abs(debit_amount)
        if signed == 0:
            continue

        statement.rows.append(
            {
                "date": _cell(row, TEB_COLUMNS["date"]),
                "description": _cell(row, TEB_COLUMNS["description"]),
                "signed": signed,
                "balance": parse_number(_cell(row, TEB_COLUMNS["balance"])),
                "reference": _cell(row, TEB_COLUMNS["reference"]) or None,
            }
        )

    if not statement.rows:
        raise ImportError_("pasqyra nuk permban asnje transaksion")
    return statement


# ---------------------------------------------------------------------------
# Checking the parse against the bank's own arithmetic
# ---------------------------------------------------------------------------


@dataclass
class Reconciliation:
    """Whether a parsed statement agrees with the totals printed on it."""

    checked: int = 0
    mismatches: list = field(default_factory=list)
    debit_ok: Optional[bool] = None
    credit_ok: Optional[bool] = None
    count_ok: Optional[bool] = None

    @property
    def balances_ok(self):
        return not self.mismatches

    @property
    def ok(self):
        """Every check that could be made, passed."""
        return self.balances_ok and all(
            result is not False for result in (self.debit_ok, self.credit_ok, self.count_ok)
        )


def reconcile(statement):
    """Apply each row to the opening balance and compare with what is printed.

    Four independent checks against numbers the bank computed. A statement that
    fails any of them has been misread - by an unnoticed row, a misplaced
    decimal separator, or a column read as the wrong one - and importing it
    would write money that is wrong in a way nothing later would reveal.
    """
    result = Reconciliation()
    if statement.opening is None:
        # Without an opening balance the running total cannot be checked, but
        # the stated totals still can.
        running = None
    else:
        running = statement.opening

    for row in statement.rows:
        if running is None or row["balance"] is None:
            continue
        running += row["signed"]
        result.checked += 1
        if running != row["balance"]:
            result.mismatches.append((row["date"], running, row["balance"]))

    debits = sum((r["signed"] for r in statement.rows if r["signed"] < 0), Decimal("0"))
    credits = sum((r["signed"] for r in statement.rows if r["signed"] > 0), Decimal("0"))

    if statement.stated_debit is not None:
        result.debit_ok = abs(debits) == abs(statement.stated_debit)
    if statement.stated_credit is not None:
        result.credit_ok = credits == statement.stated_credit
    if statement.stated_count is not None:
        result.count_ok = len(statement.rows) == statement.stated_count

    return result


# ---------------------------------------------------------------------------
# Turning a statement into candidates
# ---------------------------------------------------------------------------


def to_candidates(statement, account_id=None, deposit_is_transfer=True):
    """Candidates from a parsed statement, ready for the same preview as a CSV."""
    import datetime

    from .dates import format_date
    from .importing import Candidate
    from .schema import EXPENSE, INCOME, TRANSFER

    candidates = []
    for offset, row in enumerate(statement.rows, start=2):
        candidate = Candidate(row_number=offset)
        candidate.description = clean_description(row["description"])
        candidate.reference = row["reference"]
        candidate.account_id = account_id

        try:
            parsed = datetime.datetime.strptime(row["date"], DATE_FORMAT).date()
            candidate.occurred_on = format_date(parsed)
        except ValueError:
            candidate.problem = "date"
            candidate.selected = False

        amount = row["signed"]
        candidate.amount = abs(amount)
        if amount < 0:
            candidate.kind = EXPENSE
        elif deposit_is_transfer and is_deposit(row["description"]):
            candidate.kind = TRANSFER
            # A deposit is money arriving, so the statement's account is the
            # destination. Putting it on account_id would take the money out
            # of the very account the statement says it went into.
            candidate.account_id = None
            candidate.to_account_id = account_id
        else:
            candidate.kind = INCOME

        candidates.append(candidate)
    return candidates


# Runs of asterisks are how the bank masks a card or account number; the time
# of day and the trailing yyyymmdd add nothing a date column does not already
# carry.
_MASK = re.compile(r"\*{3,}")
_TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")
_TRAILING_DATE = re.compile(r"\b\d{8}\b\s*$")
# A long run of digits in a statement description is an account or card
# number. It identifies nothing about the purchase and would otherwise be
# copied into the database and out again through every export.
_LONG_NUMBER = re.compile(r"\b\d{10,}\b")


def clean_description(text):
    """A statement description with the noise taken out.

    What is left is what identifies the purchase. Everything removed is either
    masked already or repeated in a column of its own.
    """
    cleaned = _MASK.sub(" ", text or "")
    cleaned = _TIME.sub(" ", cleaned)
    cleaned = _TRAILING_DATE.sub(" ", cleaned)
    cleaned = _LONG_NUMBER.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned or "-"
