"""Tests for the data models.

Type normalization gets heavy coverage here on purpose: mismatched type
strings caused three separate bugs in this project's history, once by mixing
languages and once by mixing capitalization.
"""

from decimal import Decimal

import pytest

from personal_finance.config import EXPENSE, INCOME
from personal_finance.models import (
    Budget,
    RecurringRule,
    Transaction,
    normalize_type,
    parse_amount,
)


class TestNormalizeType:
    def test_canonical_values_pass_through(self):
        assert normalize_type(INCOME) == INCOME
        assert normalize_type(EXPENSE) == EXPENSE

    @pytest.mark.parametrize(
        "legacy,expected",
        [
            ("income", INCOME),
            ("expense", EXPENSE),
            ("te ardhura", INCOME),
            ("shpenzime", EXPENSE),
        ],
    )
    def test_legacy_english_and_lowercase_values_are_migrated(self, legacy, expected):
        assert normalize_type(legacy) == expected

    def test_case_insensitive_for_legacy_values(self):
        # The exact bug that made income silently count as zero.
        assert normalize_type("TE ARDHURA") == INCOME
        assert normalize_type("Te ardhura") == INCOME

    def test_whitespace_is_tolerated(self):
        assert normalize_type("  Te Ardhura  ") == INCOME

    @pytest.mark.parametrize("bad", [None, "", "nonsense", "revenue"])
    def test_unknown_values_return_none(self, bad):
        assert normalize_type(bad) is None


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
    def test_valid_amounts(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize("bad", ["abc", "", None, "-5", "NaN", "Infinity", "1,5"])
    def test_invalid_amounts_return_none(self, bad):
        assert parse_amount(bad) is None

    def test_zero_can_be_rejected(self):
        assert parse_amount("0", allow_zero=False) is None
        assert parse_amount("0.01", allow_zero=False) == Decimal("0.01")

    def test_decimal_precision_is_exact(self):
        total = parse_amount("0.10") + parse_amount("0.20")
        assert total == Decimal("0.30")
        assert str(total) == "0.30"


class TestTransaction:
    def test_round_trip_through_row(self):
        original = Transaction(INCOME, "Paga", Decimal("1200.00"), "01-06-2026", "Paga")
        restored = Transaction.from_row(original.to_row())
        assert restored == original

    def test_amount_is_always_two_decimals_on_disk(self):
        row = Transaction(INCOME, "Paga", Decimal("1200"), "01-06-2026").to_row()
        assert row["shuma"] == "1200.00"

    def test_missing_category_column_gets_default(self):
        # A row written before categories existed.
        row = {"lloji": INCOME, "pershkrimi": "Paga", "shuma": "100", "data": "01-06-2026"}
        assert Transaction.from_row(row).kategoria == "Pa kategori"

    def test_legacy_english_type_is_migrated_on_load(self):
        row = {"lloji": "income", "pershkrimi": "Paga", "shuma": "100", "data": "01-06-2026"}
        assert Transaction.from_row(row).lloji == INCOME

    @pytest.mark.parametrize(
        "row",
        [
            {"lloji": "bad", "pershkrimi": "x", "shuma": "1", "data": "01-06-2026"},
            {"lloji": INCOME, "pershkrimi": "x", "shuma": "abc", "data": "01-06-2026"},
            {"lloji": INCOME, "pershkrimi": "", "shuma": "1", "data": "01-06-2026"},
            {"lloji": INCOME, "pershkrimi": "x", "shuma": "1", "data": "bad-date"},
            {"lloji": INCOME, "pershkrimi": "x", "shuma": "-1", "data": "01-06-2026"},
        ],
    )
    def test_invalid_rows_raise(self, row):
        with pytest.raises(ValueError):
            Transaction.from_row(row)

    def test_is_income_and_is_expense(self):
        assert Transaction(INCOME, "x", Decimal("1"), "01-06-2026").is_income
        assert Transaction(EXPENSE, "x", Decimal("1"), "01-06-2026").is_expense


class TestRecurringRule:
    def test_round_trip_through_row(self):
        # Keyword arguments on purpose: positional ones silently landed in the
        # wrong fields here, and the round-trip preserved the mistake.
        original = RecurringRule(
            lloji=EXPENSE,
            pershkrimi="Qera",
            shuma=Decimal("300.00"),
            kategoria="Qera",
            nenkategoria="Banesa",
            llogaria="Banka",
            frekuenca="mujore",
            data_fillimit="01-01-2026",
            data_e_fundit="01-03-2026",
        )
        restored = RecurringRule.from_row(original.to_row())
        assert restored == original

    def test_every_field_survives_the_round_trip(self):
        original = RecurringRule(
            lloji=EXPENSE,
            pershkrimi="Qera",
            shuma=Decimal("300.00"),
            kategoria="Qera",
            nenkategoria="Banesa",
            llogaria="Banka",
            frekuenca="mujore",
            data_fillimit="01-01-2026",
            data_e_fundit="01-03-2026",
        )
        restored = RecurringRule.from_row(original.to_row())
        assert restored.nenkategoria == "Banesa"
        assert restored.llogaria == "Banka"
        assert restored.frekuenca == "mujore"
        assert restored.data_fillimit == "01-01-2026"
        assert restored.data_e_fundit == "01-03-2026"

    def test_unknown_frequency_rejected_when_validated(self):
        row = {
            "lloji": EXPENSE,
            "pershkrimi": "x",
            "shuma": "1",
            "frekuenca": "cdo-hene",
            "data_fillimit": "01-01-2026",
        }
        with pytest.raises(ValueError):
            RecurringRule.from_row(row, valid_frequencies={"mujore"})

    def test_bad_last_generated_is_treated_as_never(self):
        # Should degrade gracefully rather than kill the whole rule.
        row = {
            "lloji": EXPENSE,
            "pershkrimi": "x",
            "shuma": "1",
            "frekuenca": "mujore",
            "data_fillimit": "01-01-2026",
            "data_e_fundit": "garbage",
        }
        assert RecurringRule.from_row(row).data_e_fundit == ""

    def test_to_transaction_uses_the_given_date(self):
        import datetime

        rule = RecurringRule(
            lloji=EXPENSE,
            pershkrimi="Qera",
            shuma=Decimal("300"),
            kategoria="Qera",
            llogaria="Banka",
            frekuenca="mujore",
            data_fillimit="01-01-2026",
        )
        transaction = rule.to_transaction(datetime.date(2026, 5, 1))
        assert transaction.data == "01-05-2026"
        assert transaction.shuma == Decimal("300")
        assert transaction.kategoria == "Qera"
        # The generated transaction lands in the account the rule names.
        assert transaction.llogaria == "Banka"


class TestBudget:
    def test_round_trip_through_row(self):
        original = Budget("Ushqim", Decimal("200.00"))
        assert Budget.from_row(original.to_row()) == original

    @pytest.mark.parametrize(
        "row",
        [
            {"kategoria": "", "shuma": "100"},
            {"kategoria": "Ushqim", "shuma": "0"},
            {"kategoria": "Ushqim", "shuma": "abc"},
        ],
    )
    def test_invalid_rows_raise(self, row):
        with pytest.raises(ValueError):
            Budget.from_row(row)
