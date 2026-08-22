"""Tests for the interactive prompts and flows.

Input is simulated so the validation loops - which reject bad input and retry -
are covered without a human at a keyboard.

The account prompts are covered here because version 2.3.0 shipped with them
missing from the menu entirely: the command-line paths were tested and the menu
paths were not, so an edit that silently failed to apply reached a release.
"""

from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.accounts import count_unassigned
from personal_finance.models import BANK, CASH
from personal_finance.schema import EXPENSE, INCOME, TRANSFER
from personal_finance.ui import (
    add_recurring,
    add_transaction,
    add_transfer,
    delete_transaction,
    edit_transaction,
    numbered,
    prompt_amount,
    prompt_category,
    prompt_date,
    prompt_description,
    prompt_index,
    prompt_kind,
    prompt_opening_balance,
    prompt_subcategory,
)


@pytest.fixture(autouse=True)
def plain():
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield
    i18n.set_language("sq")


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


class TestPromptAmount:
    def test_accepts_a_number(self, answers):
        answers("300")
        assert prompt_amount() == Decimal("300")

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


class TestPromptOpeningBalance:
    def test_allows_negative(self, answers):
        """A card usually starts out owing money."""
        answers("-250")
        assert prompt_opening_balance() == Decimal("-250")

    def test_empty_means_zero(self, answers):
        answers("")
        assert prompt_opening_balance() == Decimal("0.00")

    def test_rejects_nonsense(self, answers, capsys):
        answers("abc", "0")
        assert prompt_opening_balance() == Decimal("0")
        assert "pavlefshme" in capsys.readouterr().out


class TestPromptDate:
    def test_yes_gives_today(self, answers):
        from personal_finance.dates import current_date_str

        answers("po")
        assert prompt_date() == current_date_str()

    def test_no_then_a_custom_date(self, answers):
        answers("jo", "15-06-2026")
        assert prompt_date() == "15-06-2026"

    def test_rejects_a_bad_yes_no(self, answers, capsys):
        answers("maybe", "po")
        prompt_date()
        assert "po" in capsys.readouterr().out

    def test_rejects_a_bad_date_then_accepts(self, answers, capsys):
        answers("jo", "99-99-9999", "15-06-2026")
        assert prompt_date() == "15-06-2026"
        assert "pavlefshem" in capsys.readouterr().out


class TestPromptKind:
    def test_one_is_income(self, answers):
        answers("1")
        assert prompt_kind() == INCOME

    def test_two_is_expense(self, answers):
        answers("2")
        assert prompt_kind() == EXPENSE

    def test_rejects_other_input(self, answers, capsys):
        answers("9", "1")
        assert prompt_kind() == INCOME
        assert "pavlefshme" in capsys.readouterr().out


class TestPromptCategory:
    def test_typing_a_new_name_is_accepted(self, app, answers):
        answers("Kafene")
        assert prompt_category(app, EXPENSE) == "Kafene"

    def test_empty_means_none(self, app, answers):
        answers("")
        assert prompt_category(app, EXPENSE) is None

    def test_pick_an_existing_one_by_number(self, app, answers, capsys):
        app.add_transaction(EXPENSE, "x", Decimal("1"), "01-06-2026", "Ushqim")
        capsys.readouterr()
        answers("1")
        assert prompt_category(app, EXPENSE) == "Ushqim"

    def test_enter_keeps_the_current_value(self, app, answers):
        answers("")
        assert prompt_category(app, EXPENSE, current="Qera") == "Qera"

    def test_dash_clears_it(self, app, answers):
        answers("-")
        assert prompt_category(app, EXPENSE, current="Qera") is None


class TestPromptSubcategory:
    def test_no_category_means_no_subcategory(self, app, answers):
        assert prompt_subcategory(app, EXPENSE, None) is None

    def test_empty_means_none(self, app, answers):
        answers("")
        assert prompt_subcategory(app, EXPENSE, "Ushqim") is None

    def test_typing_a_new_name(self, app, answers):
        answers("Dyqan")
        assert prompt_subcategory(app, EXPENSE, "Ushqim") == "Dyqan"


class TestPromptIndex:
    def test_converts_to_zero_based(self, answers):
        answers("3")
        assert prompt_index(5, "x") == 2

    def test_cancel_returns_none(self, answers, capsys):
        answers("a")
        assert prompt_index(5, "x") is None
        assert "Anuluar" in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["0", "6", "abc", ""])
    def test_invalid_returns_none(self, answers, bad):
        answers(bad)
        assert prompt_index(5, "x") is None


class TestNumbered:
    def test_numbers_reflect_position(self, stocked):
        app, _ = stocked
        rows = app.transactions()
        assert [n for n, _ in numbered(rows)] == [1, 2, 3, 4]

    def test_a_filtered_subset_keeps_its_original_numbers(self, stocked):
        """A number seen in a filtered view must still work for edit or delete."""
        app, ids = stocked
        rows = app.transactions()
        subset = [rows[2]]
        assert numbered(rows, subset) == [(3, rows[2])]


class TestInteractiveFlowsAskForAnAccount:
    """Shipped broken in 2.3.0: the menu never asked which account to use."""

    def test_add_asks_when_an_account_exists(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        # description, amount, today, category, subcategory, account
        answers("Paga", "50", "po", "Paga", "", "1")
        add_transaction(app, INCOME)
        assert app.transactions()[-1].account == "Petrit"

    def test_add_does_not_ask_without_accounts(self, app, answers):
        # No account answer supplied: an extra prompt would raise.
        answers("Paga", "50", "po", "Paga", "")
        add_transaction(app, INCOME)
        assert app.transactions()[-1].account_id is None

    def test_expense_flow_also_asks(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        answers("Qera", "300", "po", "Qera", "", "1")
        add_transaction(app, EXPENSE)
        assert app.transactions()[-1].account == "Petrit"

    def test_the_account_can_be_skipped(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        answers("Paga", "50", "po", "Paga", "", "")
        add_transaction(app, INCOME)
        assert app.transactions()[-1].account_id is None

    def test_nothing_is_left_unassigned(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        answers("Paga", "50", "po", "Paga", "", "1")
        add_transaction(app, INCOME)
        assert count_unassigned(app.transactions(), app.recurring_rules()) == 0

    def test_a_recurring_rule_asks_too(self, app, answers, capsys):
        """A rule with no account regenerates unassigned transactions monthly."""
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        # kind, description, amount, category, subcategory, account,
        # frequency, not-today, start date
        answers("2", "Qera", "300", "Qera", "", "1", "2", "jo", "01-01-2027")
        add_recurring(app)
        assert app.recurring_rules()[-1].account_id is not None


class TestEditAndDelete:
    def test_edit_changes_only_what_is_given(self, app, answers, capsys):
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        capsys.readouterr()
        # pick 1, keep kind, keep description, new amount, keep date,
        # keep category, keep subcategory
        answers("1", "", "", "350", "", "", "")
        edit_transaction(app)
        stored = app.transactions()[0]
        assert stored.amount == Decimal("350")
        assert stored.description == "Qera"
        assert stored.category == "Qera"

    def test_delete_removes_the_chosen_row(self, app, answers, capsys):
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        app.add_transaction(EXPENSE, "Ushqime", Decimal("50"), "02-06-2026", "Ushqim")
        capsys.readouterr()
        answers("1")
        delete_transaction(app)
        assert [t.description for t in app.transactions()] == ["Ushqime"]

    def test_delete_names_the_category(self, app, answers, capsys):
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        capsys.readouterr()
        answers("1")
        delete_transaction(app)
        output = capsys.readouterr().out
        assert "U fshi:" in output
        assert "Qera" in output


class TestTransferFlow:
    def test_needs_two_accounts(self, app, capsys):
        app.add_account("Banka", BANK, Decimal("0"))
        capsys.readouterr()
        add_transfer(app)
        assert "dy llogari" in capsys.readouterr().out

    def test_records_a_transfer(self, app, answers, capsys):
        app.add_account("Banka", BANK, Decimal("500"))
        app.add_account("Kesh", CASH, Decimal("0"))
        capsys.readouterr()
        # source, destination, description, amount, today
        answers("1", "2", "Terheqje", "200", "po")
        add_transfer(app)
        stored = app.transactions()[0]
        assert stored.kind == TRANSFER
        assert stored.account == "Banka"
        assert stored.to_account == "Kesh"

    def test_rejects_the_same_account_twice(self, app, answers, capsys):
        app.add_account("Banka", BANK, Decimal("500"))
        app.add_account("Kesh", CASH, Decimal("0"))
        capsys.readouterr()
        answers("1", "1", "2", "Terheqje", "200", "po")
        add_transfer(app)
        assert "njejta" in capsys.readouterr().out
        assert app.transactions()[0].to_account == "Kesh"
