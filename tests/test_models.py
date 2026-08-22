"""Tests for the data models.

Name normalisation gets close attention: SQLite's own case-insensitive
collation folds only A-Z, so "Ë" and "ë" would pass as two different
categories. Uniqueness rests on a key computed here instead.
"""

from decimal import Decimal

import pytest

from personal_finance.models import (
    ACCOUNT_KINDS,
    ALL_KINDS,
    BANK,
    CARD,
    CASH,
    ENTRY_KINDS,
    Account,
    Budget,
    Category,
    RecurringRule,
    Subcategory,
    Transaction,
    TransactionView,
    name_key,
    parse_amount,
    parse_signed_amount,
)
from personal_finance.schema import EXPENSE, INCOME, TRANSFER


class TestNameKey:
    def test_folds_case(self):
        assert name_key("Ushqim") == name_key("USHQIM")

    def test_folds_albanian_letters(self):
        """The reason this exists rather than COLLATE NOCASE."""
        assert name_key("Ëmbëlsira") == name_key("ëmbëlsira")
        assert name_key("Çaji") == name_key("çaji")

    def test_matches_composed_and_decomposed_accents(self):
        assert name_key("\u00eb") == name_key("e\u0308")

    def test_trims(self):
        assert name_key("  Ushqim  ") == name_key("Ushqim")

    def test_handles_none_and_empty(self):
        assert name_key(None) == ""
        assert name_key("") == ""

    def test_distinct_names_stay_distinct(self):
        assert name_key("Ushqim") != name_key("Ushqime")


class TestParseAmount:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("10", Decimal("10")),
            ("10.50", Decimal("10.50")),
            ("0", Decimal("0")),
            ("  25.75  ", Decimal("25.75")),
            (Decimal("3.33"), Decimal("3.33")),
            (5, Decimal("5")),
        ],
    )
    def test_valid(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize("bad", ["abc", "", None, "-5", "NaN", "Infinity", "1,5"])
    def test_invalid(self, bad):
        assert parse_amount(bad) is None

    def test_zero_can_be_rejected(self):
        assert parse_amount("0", allow_zero=False) is None
        assert parse_amount("0.01", allow_zero=False) == Decimal("0.01")

    def test_decimal_precision_is_exact(self):
        assert parse_amount("0.10") + parse_amount("0.20") == Decimal("0.30")


class TestParseSignedAmount:
    def test_allows_negative(self):
        """A card's opening balance routinely is."""
        assert parse_signed_amount("-250.00") == Decimal("-250.00")

    def test_allows_positive_and_zero(self):
        assert parse_signed_amount("100") == Decimal("100")
        assert parse_signed_amount("0") == Decimal("0")

    @pytest.mark.parametrize("bad", ["abc", None, "NaN"])
    def test_rejects_nonsense(self, bad):
        assert parse_signed_amount(bad) is None


class TestKindConstants:
    def test_entry_kinds_exclude_transfer(self):
        """A transfer is created through its own flow, needing two accounts."""
        assert TRANSFER not in ENTRY_KINDS
        assert set(ENTRY_KINDS) == {INCOME, EXPENSE}

    def test_all_kinds_includes_transfer(self):
        assert set(ALL_KINDS) == {INCOME, EXPENSE, TRANSFER}

    def test_account_kinds(self):
        assert set(ACCOUNT_KINDS) == {CASH, BANK, CARD}


class TestModels:
    def test_transaction_defaults_to_no_references(self):
        item = Transaction(EXPENSE, "x", Decimal("5"), "01-06-2026")
        assert item.category_id is None
        assert item.account_id is None
        assert item.id is None

    def test_transaction_kind_helpers(self):
        assert Transaction(INCOME, "x", Decimal("1"), "01-06-2026").is_income
        assert Transaction(EXPENSE, "x", Decimal("1"), "01-06-2026").is_expense
        assert Transaction(TRANSFER, "x", Decimal("1"), "01-06-2026").is_transfer

    def test_account_key(self):
        assert Account(name="Banka").key == name_key("Banka")

    def test_category_key(self):
        assert Category(name="Ushqim", kind=EXPENSE).key == name_key("Ushqim")

    def test_subcategory_key(self):
        assert Subcategory(name="Dyqan", category_id=1).key == name_key("Dyqan")

    def test_account_opening_defaults_to_zero(self):
        assert Account(name="Kesh").opening == Decimal("0.00")

    def test_budget_holds_a_category_id(self):
        """Keyed on an id, so a rename needs nothing here rewritten."""
        assert Budget(category_id=7, limit=Decimal("200")).category_id == 7

    def test_view_kind_helpers(self):
        view = TransactionView(
            id=1,
            kind=TRANSFER,
            description="x",
            amount=Decimal("1"),
            occurred_on="01-06-2026",
        )
        assert view.is_transfer
        assert not view.is_income

    def test_view_names_default_to_none(self):
        view = TransactionView(
            id=1,
            kind=EXPENSE,
            description="x",
            amount=Decimal("1"),
            occurred_on="01-06-2026",
        )
        assert view.category is None
        assert view.account is None


class TestRuleToTransaction:
    def test_carries_every_reference(self):
        import datetime

        rule = RecurringRule(
            kind=EXPENSE,
            description="Qera",
            amount=Decimal("300"),
            frequency="mujore",
            starts_on="01-01-2026",
            category_id=3,
            subcategory_id=4,
            account_id=5,
        )
        created = rule.to_transaction(datetime.date(2026, 5, 1))
        assert created.occurred_on == "01-05-2026"
        assert created.amount == Decimal("300")
        assert created.category_id == 3
        assert created.subcategory_id == 4
        assert created.account_id == 5

    def test_the_new_transaction_has_no_id_yet(self):
        import datetime

        rule = RecurringRule(
            kind=EXPENSE,
            description="Qera",
            amount=Decimal("300"),
            starts_on="01-01-2026",
        )
        assert rule.to_transaction(datetime.date(2026, 5, 1)).id is None
