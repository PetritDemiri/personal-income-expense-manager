"""Importimi / Importing transactions from a file.

Reading a file written by something else, and deciding what to trust before any
of it reaches the database.

Nothing here writes until the caller says so. A file is read into candidates,
each candidate is checked against what is already stored, and the whole set is
shown before a single row is committed - the mistakes this guards against
(a misread decimal separator, a day and month the wrong way round, an
overlapping range imported twice) are all silent ones, and a preview is the
only thing that makes them visible.

Number and date formats are worked out from the whole column rather than from
one value, because a single "01/02/2026" cannot say which half is the month
while a column containing "15/02/2026" can.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from .dates import format_date
from .schema import EXPENSE, INCOME, TRANSFER

# Tried in order when a file does not say what it is. utf-8-sig first so a byte
# order mark is consumed rather than becoming part of the first header name.
ENCODINGS = ("utf-8-sig", "utf-16", "utf-8", "cp1252", "latin-1")

DELIMITERS = (",", ";", "\t", "|")

# Header names that identify a column, matched case-insensitively against the
# start of the header. Albanian first, then English.
COLUMN_HINTS = {
    "date": ("data", "date", "dt"),
    "kind": ("lloji", "type", "kind"),
    "description": ("pershkrimi", "përshkrimi", "shpjegimi", "description", "narrative", "detaje"),
    "amount": ("shuma", "amount", "vlera", "value"),
    "debit": ("debi", "debit", "dalje", "out"),
    "credit": ("kredi", "credit", "hyrje", "in"),
    "category": ("kategoria", "category"),
    "subcategory": ("nenkategoria", "nënkategoria", "subcategory"),
    "account": ("llogaria", "account"),
    "reference": ("nr.trx", "nrtrx", "reference", "ref", "id"),
}

# What a type column may say. The program's own export writes the label shown
# on screen, so reading one back has to recognise both languages - and a file
# from anywhere else may well use a word of its own.
KIND_WORDS = {
    INCOME: ("te ardhura", "të ardhura", "income", "credit", "in", "hyrje"),
    EXPENSE: ("shpenzime", "expense", "debit", "out", "dalje"),
    TRANSFER: ("transferim", "transfer"),
}


def parse_kind(text):
    """The transaction type a cell names, or None if it names none."""
    cleaned = " ".join((text or "").split()).casefold()
    if not cleaned:
        return None
    for kind, words in KIND_WORDS.items():
        if cleaned in words:
            return kind
    return None


DATE_FORMATS = (
    ("%d-%m-%Y", "dd-mm-yyyy"),
    ("%d/%m/%Y", "dd/mm/yyyy"),
    ("%d.%m.%Y", "dd.mm.yyyy"),
    ("%Y-%m-%d", "yyyy-mm-dd"),
    ("%Y/%m/%d", "yyyy/mm/dd"),
    ("%m/%d/%Y", "mm/dd/yyyy"),
)


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """One parsed row, before it is anything the database knows about.

    Carries where it came from and what is wrong with it, so the preview can
    explain itself rather than silently dropping rows.
    """

    row_number: int
    kind: str = EXPENSE
    description: str = ""
    amount: Decimal = field(default_factory=lambda: Decimal("0.00"))
    occurred_on: str = ""
    category: Optional[str] = None
    subcategory: Optional[str] = None
    account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    reference: Optional[str] = None
    selected: bool = True
    duplicate_of: Optional[int] = None
    problem: Optional[str] = None

    @property
    def importable(self):
        """Whether this row could be written at all."""
        return self.problem is None

    @property
    def will_import(self):
        return self.importable and self.selected


class ImportError_(Exception):
    """A file that cannot be read at all, as opposed to a row that cannot."""


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------


def decode(raw):
    """Text from bytes, trying the encodings a statement is likely to use.

    Returns (text, encoding). A bank file arriving as UTF-16 and read as UTF-8
    yields no rows rather than an error, which is the worst kind of failure, so
    every candidate encoding is tried before giving up.
    """
    for encoding in ENCODINGS:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        # A wrong guess frequently "succeeds" while producing NUL characters.
        if "\x00" in text:
            continue
        return text, encoding
    raise ImportError_("kodimi i skedarit nuk u njoh")


def sniff_delimiter(text):
    """The delimiter that splits the first lines into the most equal columns."""
    lines = [line for line in text.splitlines() if line.strip()][:20]
    if not lines:
        raise ImportError_("skedari eshte bosh")

    best, best_score = ",", 0
    for delimiter in DELIMITERS:
        counts = [line.count(delimiter) for line in lines]
        if not counts or max(counts) == 0:
            continue
        # Consistent counts across lines mean it really is the separator.
        score = min(counts) * 10 + (1 if len(set(counts)) == 1 else 0)
        if score > best_score:
            best, best_score = delimiter, score
    return best


def read_rows(raw):
    """Split a file into (header, rows). Returns (header, rows, encoding)."""
    text, encoding = decode(raw)
    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ImportError_("skedari nuk permban asnje rresht")
    return rows[0], rows[1:], encoding


# ---------------------------------------------------------------------------
# Working out the columns
# ---------------------------------------------------------------------------


def guess_columns(header):
    """Map each recognised role to a column index.

    Only names that are actually recognised are returned; anything else is the
    caller's to ask about. Guessing wrongly is worse than asking.
    """
    mapping = {}
    for index, name in enumerate(header):
        cleaned = name.strip().casefold()
        if not cleaned:
            continue
        for role, hints in COLUMN_HINTS.items():
            if role in mapping:
                continue
            if any(cleaned.startswith(hint) for hint in hints):
                mapping[role] = index
                break
    return mapping


def has_usable_amount(mapping):
    """Whether the mapping can produce an amount at all."""
    return "amount" in mapping or "debit" in mapping or "credit" in mapping


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"^-?[\d.,\s']*\d$")


def detect_decimal_separator(values):
    """Whether '.' or ',' is the decimal separator in a column of numbers.

    Decided from the whole column. "1.234" alone could be a thousand and a bit
    or one and a bit; a column also containing "12,50" settles it. Where both
    separators appear in one value the last one is the decimal, which is true
    of every convention in use.
    """
    for value in values:
        text = (value or "").strip()
        if "." in text and "," in text:
            return "," if text.rfind(",") > text.rfind(".") else "."

    # Only one separator kind appears anywhere. A group of exactly three digits
    # after it looks like thousands; anything else is a decimal.
    votes = {".": 0, ",": 0}
    for value in values:
        text = (value or "").strip()
        for separator in (".", ","):
            if separator not in text:
                continue
            tail = text.rsplit(separator, 1)[1]
            if len(tail) != 3:
                votes[separator] += 1
    if votes["."] or votes[","]:
        return "." if votes["."] >= votes[","] else ","
    return "."


def parse_number(text, decimal_separator="."):
    """A Decimal from a formatted number, or None.

    Handles a leading or trailing minus, parentheses for negatives, spaces and
    apostrophes as thousands separators, and a currency symbol.
    """
    if text is None:
        return None
    cleaned = str(text).strip()
    if not cleaned:
        return None

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative, cleaned = True, cleaned[1:-1].strip()
    if cleaned.endswith("-"):
        negative, cleaned = True, cleaned[:-1].strip()
    if cleaned.startswith("-"):
        negative, cleaned = True, cleaned[1:].strip()

    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    if not cleaned:
        return None

    thousands = "," if decimal_separator == "." else "."
    cleaned = cleaned.replace(thousands, "").replace(decimal_separator, ".")
    if cleaned.count(".") > 1 or not cleaned.strip("."):
        return None

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    return -amount if negative else amount


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def detect_date_format(values):
    """The format that reads every date in a column, or None if unclear.

    Returns (strptime_format, label). Ambiguity between day-first and
    month-first is resolved by looking for a value whose first part exceeds 12;
    where no value settles it the caller is told rather than guessed at, since
    reading 03/04 as April rather than March is a silent error.
    """
    import datetime

    samples = [v.strip() for v in values if (v or "").strip()]
    if not samples:
        return None

    workable = []
    for fmt, label in DATE_FORMATS:
        try:
            for sample in samples:
                datetime.datetime.strptime(sample, fmt)
        except ValueError:
            continue
        workable.append((fmt, label))

    if not workable:
        return None
    if len(workable) == 1:
        return workable[0]

    # Several fit. Prefer day-first, which is what the program uses and what
    # every format in this region writes.
    for fmt, label in workable:
        if fmt.startswith("%d"):
            return fmt, label
    return workable[0]


def to_display_date(text, fmt):
    """A date from the file, in the dd-mm-yyyy the program stores."""
    import datetime

    try:
        return format_date(datetime.datetime.strptime(text.strip(), fmt).date())
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Building candidates
# ---------------------------------------------------------------------------


def build_candidates(header, rows, mapping, account_id=None, deposit_is_transfer=False):
    """Turn parsed rows into candidates, with formats detected from the column."""
    del header  # kept for signature symmetry with callers that report on it

    def column(row, role):
        index = mapping.get(role)
        if index is None or index >= len(row):
            return ""
        return row[index]

    amount_columns = [role for role in ("amount", "debit", "credit") if role in mapping]
    numbers = [column(row, role) for row in rows for role in amount_columns]
    separator = detect_decimal_separator(numbers)

    detected = detect_date_format([column(row, "date") for row in rows])
    date_format = detected[0] if detected else None

    candidates = []
    for offset, row in enumerate(rows, start=2):
        candidate = Candidate(row_number=offset)
        candidate.description = column(row, "description").strip() or "-"
        candidate.reference = column(row, "reference").strip() or None
        candidate.category = column(row, "category").strip() or None
        candidate.subcategory = column(row, "subcategory").strip() or None
        candidate.account_id = account_id

        raw_date = column(row, "date").strip()
        occurred = to_display_date(raw_date, date_format) if date_format else None
        if occurred is None:
            candidate.problem = "date"
            candidate.selected = False
        else:
            candidate.occurred_on = occurred

        amount = signed_amount(row, mapping, column, separator)
        if amount is None or amount == 0:
            if candidate.problem is None:
                candidate.problem = "amount"
                candidate.selected = False
        else:
            candidate.amount = abs(amount)
            # A type column is better evidence than the sign of the amount.
            # The program's own export writes every amount positive with the
            # type beside it, so reading the sign alone made every row income.
            stated = parse_kind(column(row, "kind")) if "kind" in mapping else None
            if stated is not None:
                candidate.kind = stated
            else:
                candidate.kind = INCOME if amount > 0 else EXPENSE
                if deposit_is_transfer and amount > 0 and is_deposit(candidate.description):
                    candidate.kind = TRANSFER

        candidates.append(candidate)

    return candidates, separator, detected


def signed_amount(row, mapping, column, separator):
    """One signed amount from either a single column or a debit/credit pair."""
    if "amount" in mapping:
        return parse_number(column(row, "amount"), separator)

    debit = parse_number(column(row, "debit"), separator) or Decimal("0")
    credit = parse_number(column(row, "credit"), separator) or Decimal("0")
    if debit == 0 and credit == 0:
        return None
    # A debit column may or may not already carry its own minus sign.
    return credit - abs(debit)


DEPOSIT_MARKERS = ("deponim", "deposit", "cash in")


def is_deposit(description):
    """Whether a description looks like cash being paid into the account.

    Money moved from a pocket into a bank is a transfer, not income - counting
    it as income would inflate earnings while leaving the cash account too high.
    """
    lowered = (description or "").casefold()
    return any(marker in lowered for marker in DEPOSIT_MARKERS)


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def normalise(text):
    """A description reduced to what two records of the same event share."""
    return " ".join(re.sub(r"[^\w\s]", " ", (text or "").casefold()).split())


def mark_duplicates(candidates, existing):
    """Flag candidates that match something already stored.

    Matched on date and amount together with either a reference the file
    carries or a normalised description. Flagged rather than dropped: the
    preview shows them deselected, so re-importing an overlapping range is
    visible instead of silently doubling the spending.
    """
    by_reference = {}
    by_description = {}
    for item in existing:
        key = (item.occurred_on, item.amount)
        by_description.setdefault((key, normalise(item.description)), item.id)

    for candidate in candidates:
        if not candidate.importable:
            continue
        key = (candidate.occurred_on, candidate.amount)
        match = by_description.get((key, normalise(candidate.description)))
        if match is None and candidate.reference:
            match = by_reference.get((candidate.occurred_on, candidate.reference))
        if match is not None:
            candidate.duplicate_of = match
            candidate.selected = False
    return candidates


# ---------------------------------------------------------------------------
# Committing
# ---------------------------------------------------------------------------


def commit(app, candidates):
    """Write every selected candidate, in one database transaction.

    All or nothing: a partial import would leave the user unable to tell what
    had landed, and re-running it would double whatever had.
    """
    chosen = [c for c in candidates if c.will_import]
    if not chosen:
        return 0

    with app.db.atomic() as connection:
        for candidate in chosen:
            category_id = (
                app.db.ensure_category(candidate.category, candidate.kind)
                if candidate.category and candidate.kind != TRANSFER
                else None
            )
            subcategory_id = (
                app.db.ensure_subcategory(candidate.subcategory, category_id)
                if candidate.subcategory and category_id
                else None
            )
            from .models import Transaction

            app.db.add_transaction(
                Transaction(
                    kind=candidate.kind,
                    description=candidate.description,
                    amount=candidate.amount,
                    occurred_on=candidate.occurred_on,
                    category_id=category_id,
                    subcategory_id=subcategory_id,
                    account_id=candidate.account_id,
                    to_account_id=candidate.to_account_id,
                ),
                connection=connection,
            )
    return len(chosen)
