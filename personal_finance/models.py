"""Modelet / Data models.

Each model knows how to convert itself to and from a CSV row. Keeping that
knowledge next to the model - rather than spread through the storage layer -
means a new field is added in one place.

Money is always Decimal. Constructing a model from a row raises ValueError on
bad input so the storage layer can skip exactly one corrupted row instead of
discarding a whole file.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .config import (
    DEFAULT_CATEGORY,
    EXPENSE,
    INCOME,
    LEGACY_TYPE_ALIASES,
    TRANSACTION_TYPES,
)
from .dates import parse_date


def parse_amount(value, allow_zero=True):
    """Convert a value to a non-negative Decimal, or return None if invalid.

    Used by both the models and the interactive prompts, so a value typed at a
    prompt and a value read from a file are validated identically.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError, ValueError):
            return None
    if not amount.is_finite():
        return None
    if amount < 0:
        return None
    if amount == 0 and not allow_zero:
        return None
    return amount


def normalize_type(value):
    """Map a stored type onto a canonical one, or return None if unrecognised.

    Files written by older versions used English values; those are translated
    here so old data keeps working.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text in TRANSACTION_TYPES:
        return text
    return LEGACY_TYPE_ALIASES.get(text.lower())


@dataclass
class Transaction:
    """A single income or expense entry."""

    lloji: str
    pershkrimi: str
    shuma: Decimal
    data: str
    kategoria: str = DEFAULT_CATEGORY
    # Optional: the empty string means the transaction sits directly in its
    # category with no subcategory.
    nenkategoria: str = ""

    FIELDNAMES = ["lloji", "pershkrimi", "shuma", "data", "kategoria", "nenkategoria"]

    @property
    def is_income(self):
        return self.lloji == INCOME

    @property
    def is_expense(self):
        return self.lloji == EXPENSE

    @property
    def date(self):
        """The transaction date as a date object, or None if unparseable."""
        return parse_date(self.data)

    @classmethod
    def from_row(cls, row):
        """Build a Transaction from a CSV row, raising ValueError if invalid."""
        trans_type = normalize_type(row.get("lloji"))
        if trans_type is None:
            raise ValueError("lloji i pavlefshem")

        amount = parse_amount(row.get("shuma"))
        if amount is None:
            raise ValueError("shume e pavlefshme")

        # Rows written before categories existed simply have no such column.
        category = (row.get("kategoria") or "").strip() or DEFAULT_CATEGORY

        description = (row.get("pershkrimi") or "").strip()
        if not description:
            raise ValueError("pershkrim i zbrazet")

        date_str = (row.get("data") or "").strip()
        if parse_date(date_str) is None:
            raise ValueError("date e pavlefshme")

        # Rows written before subcategories existed have no such column.
        subcategory = (row.get("nenkategoria") or "").strip()

        return cls(
            lloji=trans_type,
            pershkrimi=description,
            shuma=amount,
            data=date_str,
            kategoria=category,
            nenkategoria=subcategory,
        )

    def to_row(self):
        """Convert to a CSV row."""
        return {
            "lloji": self.lloji,
            "pershkrimi": self.pershkrimi,
            "shuma": f"{self.shuma:.2f}",
            "data": self.data,
            "kategoria": self.kategoria,
            "nenkategoria": self.nenkategoria,
        }


@dataclass
class RecurringRule:
    """A rule that generates transactions on a schedule."""

    lloji: str
    pershkrimi: str
    shuma: Decimal
    kategoria: str = DEFAULT_CATEGORY
    nenkategoria: str = ""
    frekuenca: str = "mujore"
    data_fillimit: str = ""
    # Empty means nothing has been generated yet, so the first occurrence due
    # is the start date itself.
    data_e_fundit: str = ""

    FIELDNAMES = [
        "lloji",
        "pershkrimi",
        "shuma",
        "kategoria",
        "nenkategoria",
        "frekuenca",
        "data_fillimit",
        "data_e_fundit",
    ]

    @property
    def start_date(self):
        return parse_date(self.data_fillimit)

    @property
    def last_generated(self):
        return parse_date(self.data_e_fundit)

    @classmethod
    def from_row(cls, row, valid_frequencies=None):
        """Build a RecurringRule from a CSV row, raising ValueError if invalid."""
        trans_type = normalize_type(row.get("lloji"))
        if trans_type is None:
            raise ValueError("lloji i pavlefshem")

        amount = parse_amount(row.get("shuma"))
        if amount is None:
            raise ValueError("shume e pavlefshme")

        frequency = (row.get("frekuenca") or "").strip()
        if valid_frequencies is not None and frequency not in valid_frequencies:
            raise ValueError("frekuence e panjohur")

        start = (row.get("data_fillimit") or "").strip()
        if parse_date(start) is None:
            raise ValueError("date fillimi e pavlefshme")

        last = (row.get("data_e_fundit") or "").strip()
        # An unparseable last-generated date is treated as "never generated"
        # rather than as a fatal error, so the rule keeps working.
        if last and parse_date(last) is None:
            last = ""

        description = (row.get("pershkrimi") or "").strip()
        if not description:
            raise ValueError("pershkrim i zbrazet")

        return cls(
            lloji=trans_type,
            pershkrimi=description,
            shuma=amount,
            kategoria=(row.get("kategoria") or "").strip() or DEFAULT_CATEGORY,
            nenkategoria=(row.get("nenkategoria") or "").strip(),
            frekuenca=frequency,
            data_fillimit=start,
            data_e_fundit=last,
        )

    def to_row(self):
        return {
            "lloji": self.lloji,
            "pershkrimi": self.pershkrimi,
            "shuma": f"{self.shuma:.2f}",
            "kategoria": self.kategoria,
            "nenkategoria": self.nenkategoria,
            "frekuenca": self.frekuenca,
            "data_fillimit": self.data_fillimit,
            "data_e_fundit": self.data_e_fundit,
        }

    def to_transaction(self, date_obj):
        """Create the transaction this rule produces on a given date."""
        from .dates import format_date

        return Transaction(
            lloji=self.lloji,
            pershkrimi=self.pershkrimi,
            shuma=self.shuma,
            data=format_date(date_obj),
            kategoria=self.kategoria,
            nenkategoria=self.nenkategoria,
        )


@dataclass
class Budget:
    """A monthly spending limit for one category."""

    kategoria: str
    shuma: Decimal = field(default_factory=lambda: Decimal("0.00"))

    FIELDNAMES = ["kategoria", "shuma"]

    @classmethod
    def from_row(cls, row):
        """Build a Budget from a CSV row, raising ValueError if invalid."""
        category = (row.get("kategoria") or "").strip()
        if not category:
            raise ValueError("kategori e zbrazet")
        amount = parse_amount(row.get("shuma"), allow_zero=False)
        if amount is None:
            raise ValueError("shume e pavlefshme")
        return cls(kategoria=category, shuma=amount)

    def to_row(self):
        return {"kategoria": self.kategoria, "shuma": f"{self.shuma:.2f}"}
