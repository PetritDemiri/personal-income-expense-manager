"""Modelet / Data models.

Plain records passed between the database and the rest of the program. They
carry an `id` once stored, and `None` where the database holds NULL - there are
no sentinel strings any more. "No category" is the absence of a category, not
a category named "no category".

Identifiers are English; the values they hold are the user's, in whatever
language the user wrote them. Conversion between what the database stores and
what these hold - cents to Decimal, ISO dates to dd-mm-yyyy - happens in the
repository layer, not here, so a model is only ever holding the same kinds of
value the rest of the program works with.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from .schema import EXPENSE, INCOME, TRANSFER

ENTRY_KINDS = (INCOME, EXPENSE)
ALL_KINDS = (INCOME, EXPENSE, TRANSFER)

CASH = "Kesh"
BANK = "Banke"
CARD = "Karte"
ACCOUNT_KINDS = (CASH, BANK, CARD)

ZERO = Decimal("0.00")


def name_key(name):
    """Normalised form of a name, for case-insensitive uniqueness.

    SQLite's COLLATE NOCASE folds only A-Z, so it treats "Ë" and "ë" as
    different letters and would allow both as separate categories. Composing
    accents first means a name typed with a combining diaeresis matches the
    same name typed with a precomposed one.
    """
    return unicodedata.normalize("NFC", (name or "").strip()).casefold()


# Plain digits, optionally with a decimal point. Written out rather than left
# to Decimal, which also accepts things nobody types on purpose: scientific
# notation (3e2), Python's underscore separators (1_000), and digits from other
# scripts. [0-9] rather than \d, because \d matches those other scripts too.
AMOUNT_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
# The same, with an optional leading minus, for an opening balance.
SIGNED_AMOUNT_PATTERN = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")


def parse_amount(value, allow_zero=True):
    """Convert a value to a non-negative Decimal, or None if it is not one."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        amount = value
    else:
        text = str(value).strip()
        if not AMOUNT_PATTERN.match(text):
            return None
        try:
            amount = Decimal(text)
        except (InvalidOperation, AttributeError, ValueError):
            return None
    if not amount.is_finite() or amount < 0:
        return None
    if amount == 0 and not allow_zero:
        return None
    return amount


def valid_name(text):
    """Whether a category or subcategory name is acceptable.

    Letters, with single spaces between words: "Ushqim", "Te tjera",
    "Paga baze". `str.isalpha` is Unicode-aware, so every Albanian letter
    passes while digits and punctuation do not.

    Rejected as typed rather than tidied up: leading or trailing spaces,
    runs of spaces, and anything that is only whitespace. A name the program
    silently trimmed would not be the name the user thought they had entered,
    and two names differing only by a space would look identical in a list.
    """
    if not text:
        return False
    if text != text.strip():
        return False
    if "  " in text:
        return False
    if not any(character.isalpha() for character in text):
        return False
    return all(character.isalpha() or character == " " for character in text)


def parse_signed_amount(value):
    """Convert a value to a Decimal that may be negative.

    Used for an account's opening balance, which is routinely negative on a
    card and must not go through the non-negative check above.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        amount = value
    else:
        text = str(value).strip()
        if not SIGNED_AMOUNT_PATTERN.match(text):
            return None
        try:
            amount = Decimal(text)
        except (InvalidOperation, AttributeError, ValueError):
            return None
    return amount if amount.is_finite() else None


@dataclass
class Account:
    """Somewhere money sits: cash, a bank account, a card."""

    name: str
    kind: str = CASH
    opening: Decimal = field(default_factory=lambda: ZERO)
    position: int = 0
    id: Optional[int] = None

    @property
    def key(self):
        return name_key(self.name)


@dataclass
class Category:
    """A grouping for transactions of one kind."""

    name: str
    kind: str = EXPENSE
    id: Optional[int] = None

    @property
    def key(self):
        return name_key(self.name)


@dataclass
class Subcategory:
    """A grouping within a category. Meaningless without its parent."""

    name: str
    category_id: int
    id: Optional[int] = None

    @property
    def key(self):
        return name_key(self.name)


@dataclass
class Transaction:
    """A single entry: income, an expense, or a movement between accounts.

    Every reference is optional. A transaction with no category is not a
    transaction in some placeholder category - it simply has none.
    """

    kind: str
    description: str
    amount: Decimal
    occurred_on: str
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
    account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    id: Optional[int] = None

    @property
    def is_income(self):
        return self.kind == INCOME

    @property
    def is_expense(self):
        return self.kind == EXPENSE

    @property
    def is_transfer(self):
        return self.kind == TRANSFER


@dataclass
class TransactionView:
    """A transaction with the names of the things it points at.

    Reading needs names; writing needs ids. Rather than have every caller
    resolve one to the other, the query that fetches transactions already
    joins the referenced tables, so the names come back for free and land
    here. Reports and the display work on views; writes take Transactions.

    A name is None where the reference is - a transaction with no category has
    no category name, rather than a name meaning "no category".
    """

    id: int
    kind: str
    description: str
    amount: Decimal
    occurred_on: str
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
    account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    account: Optional[str] = None
    to_account: Optional[str] = None
    # When the row was written and last changed. Maintained by the database,
    # so they are read here and never set.
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def is_income(self):
        return self.kind == INCOME

    @property
    def is_expense(self):
        return self.kind == EXPENSE

    @property
    def is_transfer(self):
        return self.kind == TRANSFER


@dataclass
class RecurringRule:
    """A rule that generates transactions on a schedule."""

    kind: str
    description: str
    amount: Decimal
    frequency: str = "mujore"
    starts_on: str = ""
    generated_upto: Optional[str] = None
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
    account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    id: Optional[int] = None

    def to_transaction(self, occurrence_date):
        """The transaction this rule produces on a given date."""
        from .dates import format_date

        return Transaction(
            kind=self.kind,
            description=self.description,
            amount=self.amount,
            occurred_on=format_date(occurrence_date),
            category_id=self.category_id,
            subcategory_id=self.subcategory_id,
            account_id=self.account_id,
            to_account_id=self.to_account_id,
        )


@dataclass
class CategoryRule:
    """A description pattern, and the category to apply when it matches."""

    pattern: str
    category_id: int
    subcategory_id: Optional[int] = None
    id: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None

    @property
    def key(self):
        return name_key(self.pattern)

    def matches(self, description):
        """Whether this rule applies to a description.

        Substring, case-insensitive, folded the same way names are - so a
        pattern written "Ëmbëlsira" matches a description containing
        "ëmbëlsira". Substring rather than a regular expression: a wrong
        pattern here does nothing visible, while a wrong expression matches
        things nobody intended and is hard to see in a preview.
        """
        return bool(self.key) and self.key in name_key(description)


def best_rule(rules, description):
    """The rule that applies to a description, or None.

    The longest matching pattern wins, so "STEAM" and "STEAMGAMES.CO" can both
    exist with the specific one beating the general one - without anyone
    having to maintain an order by hand.
    """
    matching = [rule for rule in rules if rule.matches(description)]
    if not matching:
        return None
    return max(matching, key=lambda rule: (len(rule.key), rule.id or 0))


@dataclass
class AuditEntry:
    """One recorded change: what, which row, when, and the row either side.

    Written by database triggers, never by this program, so it is only ever
    read. `before` is None on a create and `after` is None on a delete.
    """

    id: int
    entity: str
    entity_id: Optional[int]
    action: str
    at: str
    before: Optional[dict] = None
    after: Optional[dict] = None

    @classmethod
    def from_row(cls, row):
        import json

        def decode(text):
            if not text:
                return None
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return None

        return cls(
            id=row["id"],
            entity=row["entity"],
            entity_id=row["entity_id"],
            action=row["action"],
            at=row["at"],
            before=decode(row["before_json"]),
            after=decode(row["after_json"]),
        )

    def changes(self):
        """Fields that differ, as (field, before, after).

        The whole row is stored either side, which survives a schema change
        and keeps the trigger simple; the difference is worked out here, where
        it is cheap and only needed for display.
        """
        if self.action == "create":
            return [(key, None, value) for key, value in sorted((self.after or {}).items())]
        if self.action == "delete":
            return [(key, value, None) for key, value in sorted((self.before or {}).items())]
        before, after = self.before or {}, self.after or {}
        return [
            (key, before.get(key), after.get(key))
            for key in sorted(set(before) | set(after))
            if before.get(key) != after.get(key)
        ]


@dataclass
class Budget:
    """A monthly spending limit on one category."""

    category_id: int
    limit: Decimal
    id: Optional[int] = None
