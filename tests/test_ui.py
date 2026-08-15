"""Tests for the interactive prompts.

Input is simulated so the validation loops - which reject bad input and retry -
are covered without a human at a keyboard.
"""

from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.config import EXPENSE, INCOME
from personal_finance.ui import (
    numbered,
    prompt_amount,
    prompt_category,
    prompt_date,
    prompt_description,
    prompt_index,
    prompt_type,
)

from .conftest import make_transaction


@pytest.fixture(autouse=True)
def plain_output(monkeypatch):
    i18n.set_language("sq")
    colors.configure(force_off=True)


@pytest.fixture
def answers(monkeypatch):
    """Feed a queue of answers to input()."""

    def feed(*values):
        queue = list(values)

        def fake_input(_prompt=""):
            if not queue:
                raise AssertionError("prompt asked for more input than expected")
            return queue.pop(0)

        monkeypatch.setattr("builtins.input", fake_input)
        return queue

    return feed


class TestPromptDescription:
    def test_accepts_a_value(self, answers):
        answers("Qera")
        assert prompt_description() == "Qera"

    def test_strips_whitespace(self, answers):
        answers("  Qera  ")
        assert prompt_description() == "Qera"

    def test_rejects_empty_then_accepts(self, answers, capsys):
        answers("", "   ", "Qera")
        assert prompt_description() == "Qera"
        assert "zbrazet" in capsys.readouterr().out

    def test_enter_keeps_the_current_value(self, answers):
        answers("")
        assert prompt_description(current="Old") == "Old"

    def test_new_value_replaces_the_current_one(self, answers):
        answers("New")
        assert prompt_description(current="Old") == "New"


class TestPromptAmount:
    def test_accepts_a_number(self, answers):
        answers("300")
        assert prompt_amount() == Decimal("300")

    def test_accepts_decimals(self, answers):
        answers("12.50")
        assert prompt_amount() == Decimal("12.50")

    def test_rejects_text_then_accepts(self, answers, capsys):
        answers("abc", "50")
        assert prompt_amount() == Decimal("50")
        assert "pavlefshme" in capsys.readouterr().out

    def test_rejects_negative_then_accepts(self, answers):
        answers("-5", "5")
        assert prompt_amount() == Decimal("5")

    def test_enter_keeps_the_current_value(self, answers):
        answers("")
        assert prompt_amount(current=Decimal("99.99")) == Decimal("99.99")


class TestPromptDate:
    def test_yes_gives_today(self, answers):
        from personal_finance.dates import current_date_str

        answers("po")
        assert prompt_date() == current_date_str()

    def test_no_then_a_custom_date(self, answers):
        answers("jo", "15-06-2026")
        assert prompt_date() == "15-06-2026"

    def test_rejects_a_bad_yes_no_answer(self, answers, capsys):
        answers("maybe", "po")
        prompt_date()
        assert "po" in capsys.readouterr().out

    def test_rejects_a_bad_date_then_accepts(self, answers, capsys):
        answers("jo", "99-99-9999", "15-06-2026")
        assert prompt_date() == "15-06-2026"
        assert "pavlefshem" in capsys.readouterr().out

    def test_enter_keeps_the_current_value(self, answers):
        answers("")
        assert prompt_date(current="01-01-2026") == "01-01-2026"

    def test_english_yes_works_in_english_mode(self, answers):
        from personal_finance.dates import current_date_str

        i18n.set_language("en")
        answers("yes")
        assert prompt_date() == current_date_str()
        i18n.set_language("sq")


class TestPromptType:
    def test_one_is_income(self, answers):
        answers("1")
        assert prompt_type() == INCOME

    def test_two_is_expense(self, answers):
        answers("2")
        assert prompt_type() == EXPENSE

    def test_rejects_other_input(self, answers, capsys):
        answers("9", "1")
        assert prompt_type() == INCOME
        assert "pavlefshme" in capsys.readouterr().out

    def test_enter_keeps_the_current_value(self, answers):
        answers("")
        assert prompt_type(current=EXPENSE) == EXPENSE


class TestPromptCategory:
    def test_pick_by_number(self, answers):
        answers("2")
        assert prompt_category(["Ushqim", "Qera", "Transport"]) == "Qera"

    def test_type_a_custom_category(self, answers):
        answers("Kafene")
        assert prompt_category(["Ushqim"]) == "Kafene"

    def test_out_of_range_number_is_rejected(self, answers, capsys):
        answers("99", "1")
        assert prompt_category(["Ushqim"]) == "Ushqim"
        assert "pavlefshem" in capsys.readouterr().out

    def test_empty_input_falls_back_to_the_default(self, answers):
        answers("")
        assert prompt_category(["Ushqim"]) == "Pa kategori"

    def test_enter_keeps_the_current_value(self, answers):
        answers("")
        assert prompt_category(["Ushqim"], current="Qera") == "Qera"


class TestPromptIndex:
    def test_converts_to_a_zero_based_index(self, answers):
        answers("3")
        assert prompt_index(5, "x") == 2

    def test_cancel_returns_none(self, answers, capsys):
        answers("a")
        assert prompt_index(5, "x") is None
        assert "Anuluar" in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["0", "6", "abc", ""])
    def test_invalid_input_returns_none(self, answers, bad):
        answers(bad)
        assert prompt_index(5, "x") is None


class TestNumbered:
    def test_numbers_reflect_position_in_the_full_list(self):
        transactions = [
            make_transaction(description="A", date="01-06-2026"),
            make_transaction(description="B", date="02-06-2026"),
            make_transaction(description="C", date="03-06-2026"),
        ]
        rows = numbered(transactions)
        assert [n for n, _ in rows] == [1, 2, 3]

    def test_filtered_subsets_keep_their_original_numbers(self):
        """A number shown in a filtered view must still work for edit/delete."""
        transactions = [
            make_transaction(description="A", date="01-06-2026"),
            make_transaction(description="B", date="02-06-2026"),
            make_transaction(description="C", date="03-06-2026"),
        ]
        subset = [transactions[2]]
        rows = numbered(transactions, subset)
        assert rows == [(3, transactions[2])]

    def test_reordered_subsets_keep_their_original_numbers(self):
        transactions = [
            make_transaction(description="Late", date="20-06-2026"),
            make_transaction(description="Early", date="01-06-2026"),
        ]
        from personal_finance.reports import sort_by_date

        rows = numbered(transactions, sort_by_date(transactions))
        assert rows[0][0] == 2  # 'Early' is second in storage order
        assert rows[0][1].pershkrimi == "Early"
