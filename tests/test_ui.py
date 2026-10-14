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
    add_transactions,
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
        answers("anulo")
        assert prompt_index(5, "x") is None
        assert "Anuluar" in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["0", "6", "abc", "", "a", "ANULO", " anulo "])
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
        # how many, description, amount, today, category, subcategory, account
        answers("1", "Paga", "50", "po", "Paga", "", "1")
        add_transactions(app, INCOME)
        assert app.transactions()[-1].account == "Petrit"

    def test_add_does_not_ask_without_accounts(self, app, answers):
        # No account answer supplied: an extra prompt would raise.
        answers("1", "Paga", "50", "po", "Paga", "")
        add_transactions(app, INCOME)
        assert app.transactions()[-1].account_id is None

    def test_expense_flow_also_asks(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        answers("1", "Qera", "300", "po", "Qera", "", "1")
        add_transactions(app, EXPENSE)
        assert app.transactions()[-1].account == "Petrit"

    def test_the_account_can_be_skipped(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        answers("1", "Paga", "50", "po", "Paga", "", "")
        add_transactions(app, INCOME)
        assert app.transactions()[-1].account_id is None

    def test_nothing_is_left_unassigned(self, app, answers, capsys):
        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()
        answers("1", "Paga", "50", "po", "Paga", "", "1")
        add_transactions(app, INCOME)
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


class TestTheNumberShownIsTheRowPicked:
    """A screen reached by picking a row names that row, not the number the
    database keeps for it. The two part ways as soon as anything is deleted:
    picking row 2 said "transaction #3"."""

    @pytest.fixture
    def gap(self, app, capsys):
        first = app.add_transaction(EXPENSE, "E para", Decimal("1"), "01-06-2026", "Qera")
        app.add_transaction(EXPENSE, "E dyta", Decimal("2"), "02-06-2026", "Qera")
        app.add_transaction(EXPENSE, "E treta", Decimal("3"), "03-06-2026", "Qera")
        app.delete_transaction(first.id)
        capsys.readouterr()
        # Row 1 is now "E dyta", kept as 2; row 2 is "E treta", kept as 3.
        return app

    def test_editing(self, gap, answers, capsys):
        answers("2", "anulo")
        edit_transaction(gap)
        shown = capsys.readouterr().out
        assert "Duke ndryshuar transaksionin #2" in shown
        assert "#3" not in shown

    def test_the_history_of_one(self, gap, answers, capsys):
        from personal_finance.ui import show_transaction_history

        answers("2")
        show_transaction_history(gap)
        shown = capsys.readouterr().out
        assert "Historiku i transaksionit #2" in shown
        assert "#3" not in shown

    def test_the_history_of_everything_still_uses_the_kept_number(self, gap, capsys):
        """Deleted rows have no row number, so the full history cannot use one."""
        from personal_finance.ui import show_recent_history

        show_recent_history(gap)
        assert "#3" in capsys.readouterr().out


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


class TestStrictValidation:
    """Rules tightened in 3.1.0, each from something that got through before."""

    def test_whitespace_only_category_is_rejected(self, app, answers, capsys):
        """It used to strip to empty and be read as "no category", silently."""
        answers("   ", "Ushqim")
        assert prompt_category(app, EXPENSE) == "Ushqim"
        assert "vetem shkronja" in capsys.readouterr().out

    def test_enter_still_means_no_category(self, app, answers):
        answers("")
        assert prompt_category(app, EXPENSE) is None

    def test_a_name_with_digits_is_rejected(self, app, answers, capsys):
        answers("Kredia2", "Kredia")
        assert prompt_category(app, EXPENSE) == "Kredia"
        assert "vetem shkronja" in capsys.readouterr().out

    def test_whitespace_only_subcategory_is_rejected(self, app, answers, capsys):
        answers("  ", "Dyqan")
        assert prompt_subcategory(app, EXPENSE, "Ushqim") == "Dyqan"
        assert "vetem shkronja" in capsys.readouterr().out

    def test_enter_still_means_no_subcategory(self, app, answers):
        answers("")
        assert prompt_subcategory(app, EXPENSE, "Ushqim") is None

    @pytest.mark.parametrize("bad", ["3e2", "1_000", "١٢٣", "-5", "abc"])
    def test_amount_rejections(self, answers, bad, capsys):
        answers(bad, "50")
        assert prompt_amount() == Decimal("50")
        assert "pavlefshme" in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["PO", "Po", "pO", "yes", "y", "1"])
    def test_yes_is_lowercase_albanian_only(self, answers, bad, capsys):
        """The input is compared as typed; lowercasing accepted "PO"."""
        from personal_finance.dates import current_date_str

        answers(bad, "po")
        assert prompt_date() == current_date_str()
        assert "po" in capsys.readouterr().out

    def test_english_mode_takes_only_yes(self, answers, capsys):
        from personal_finance.dates import current_date_str

        i18n.set_language("en")
        answers("po", "Yes", "y", "yes")
        assert prompt_date() == current_date_str()
        i18n.set_language("sq")

    @pytest.mark.parametrize(
        "bad", ["1-1-2026", "31-04-2026", "29-02-2026", "31-13-2026", "00-01-2026", "2026-01-01"]
    )
    def test_date_rejections(self, answers, bad, capsys):
        answers("jo", bad, "15-06-2026")
        assert prompt_date() == "15-06-2026"
        assert "pavlefshem" in capsys.readouterr().out

    def test_a_real_leap_day_is_accepted(self, answers):
        answers("jo", "29-02-2024")
        assert prompt_date() == "29-02-2024"


class TestCategoryManagement:
    def test_add_a_category(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("2", "Ushqim")  # kind, name
        add_category(app)
        assert [c.name for c in app.categories(EXPENSE)] == ["Ushqim"]

    def test_a_duplicate_is_refused(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("2", "Ushqim")
        add_category(app)
        capsys.readouterr()
        answers("2", "ushqim")  # same name, different case
        add_category(app)
        assert "ekziston" in capsys.readouterr().out
        assert len(app.categories(EXPENSE)) == 1

    def test_the_same_name_is_allowed_in_each_kind(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("1", "Rimbursim")
        add_category(app)
        answers("2", "Rimbursim")
        add_category(app)
        assert len(app.categories(INCOME)) == 1
        assert len(app.categories(EXPENSE)) == 1

    def test_an_invalid_name_is_refused(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("2", "Kredia2", " Ushqim", "Ushqim")
        add_category(app)
        output = capsys.readouterr().out
        assert "vetem shkronja" in output
        assert [c.name for c in app.categories(EXPENSE)] == ["Ushqim"]

    def test_a_two_word_name_is_accepted(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("2", "Te tjera")
        add_category(app)
        assert [c.name for c in app.categories(EXPENSE)] == ["Te tjera"]

    def test_rename_touches_only_the_category_row(self, app, answers, capsys):
        from personal_finance.ui import rename_category

        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Ushqim")
        capsys.readouterr()
        answers("2", "1", "Ushqime")  # kind, pick, new name
        rename_category(app)
        assert app.transactions()[0].category == "Ushqime"

    def test_add_a_subcategory(self, app, answers, capsys):
        from personal_finance.ui import add_category, add_subcategory

        answers("2", "Ushqim")
        add_category(app)
        capsys.readouterr()
        answers("2", "1", "Dyqan")  # kind, pick category, name
        add_subcategory(app)
        category = app.categories(EXPENSE)[0]
        assert [s.name for s in app.subcategories(category.id)] == ["Dyqan"]

    def test_delete_a_category_keeps_its_transactions(self, app, answers, capsys):
        from personal_finance.ui import delete_category

        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Ushqim")
        capsys.readouterr()
        answers("2", "1", "po")  # kind, pick, confirm
        delete_category(app)
        assert app.count() == 1
        assert app.transactions()[0].category is None

    def test_deleting_a_category_can_be_cancelled(self, app, answers, capsys):
        from personal_finance.ui import delete_category

        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Ushqim")
        capsys.readouterr()
        answers("2", "1", "jo")
        delete_category(app)
        assert len(app.categories(EXPENSE)) == 1

    def test_deleting_a_category_removes_its_subcategories(self, app, answers, capsys):
        from personal_finance.ui import delete_category

        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Ushqim", "Dyqan")
        category = app.categories(EXPENSE)[0]
        assert len(app.subcategories(category.id)) == 1
        capsys.readouterr()

        answers("2", "1", "po")
        delete_category(app)
        assert app.categories(EXPENSE) == []
        assert app.transactions()[0].subcategory is None


class TestNoSurroundingWhitespace:
    """Values are taken exactly as typed, never trimmed into acceptability."""

    def test_a_category_with_a_leading_space_is_rejected(self, app, answers, capsys):
        answers(" Ushqim", "Ushqim")
        assert prompt_category(app, EXPENSE) == "Ushqim"
        assert "vetem shkronja" in capsys.readouterr().out

    def test_a_category_with_a_trailing_space_is_rejected(self, app, answers, capsys):
        answers("Ushqim ", "Ushqim")
        assert prompt_category(app, EXPENSE) == "Ushqim"
        assert "vetem shkronja" in capsys.readouterr().out

    def test_two_words_are_accepted(self, app, answers):
        answers("Te tjera")
        assert prompt_category(app, EXPENSE) == "Te tjera"

    def test_two_spaces_between_words_are_rejected(self, app, answers, capsys):
        answers("Te  tjera", "Te tjera")
        assert prompt_category(app, EXPENSE) == "Te tjera"
        assert "vetem shkronja" in capsys.readouterr().out

    def test_a_two_word_subcategory_is_accepted(self, app, answers):
        answers("Paga baze")
        assert prompt_subcategory(app, EXPENSE, "Paga") == "Paga baze"

    def test_a_subcategory_with_surrounding_spaces_is_rejected(self, app, answers, capsys):
        answers(" Dyqan ", "Dyqan")
        assert prompt_subcategory(app, EXPENSE, "Ushqim") == "Dyqan"
        assert "vetem shkronja" in capsys.readouterr().out

    @pytest.mark.parametrize("bad", [" po", "po ", " po ", "\tpo"])
    def test_yes_with_surrounding_whitespace_is_rejected(self, answers, bad, capsys):
        from personal_finance.dates import current_date_str

        answers(bad, "po")
        assert prompt_date() == current_date_str()
        assert "po" in capsys.readouterr().out

    def test_no_with_surrounding_whitespace_is_rejected(self, answers, capsys):
        answers(" jo", "jo", "15-06-2026")
        assert prompt_date() == "15-06-2026"
        assert "po" in capsys.readouterr().out

    def test_the_category_menu_prompt_is_equally_strict(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("2", " Ushqim", "Ushqim")
        add_category(app)
        assert [c.name for c in app.categories(EXPENSE)] == ["Ushqim"]


class TestCancelWord:
    """Cancelling takes a whole word, in the interface language, exactly typed.

    It used to be the single letter "a", which collided with "a" as a
    legitimate category name - the name could be created but not chosen for
    deletion, because the prompt read it as a cancellation.
    """

    def test_albanian_cancel(self, answers, capsys):
        answers("anulo")
        assert prompt_index(5, "x") is None
        assert "Anuluar" in capsys.readouterr().out

    def test_english_cancel(self, answers, capsys):
        i18n.set_language("en")
        answers("cancel")
        assert prompt_index(5, "x") is None
        assert "Cancelled" in capsys.readouterr().out
        i18n.set_language("sq")

    @pytest.mark.parametrize(
        "bad", ["ANULO", "Anulo", " anulo", "anulo ", " anulo ", "cancel", "a"]
    )
    def test_albanian_mode_refuses_everything_else(self, answers, bad, capsys):
        answers(bad)
        assert prompt_index(5, "x") is None
        # Refused as a number rather than accepted as a cancellation.
        assert "Anuluar" not in capsys.readouterr().out

    @pytest.mark.parametrize("bad", ["CANCEL", " cancel ", "anulo", "a"])
    def test_english_mode_refuses_everything_else(self, answers, bad, capsys):
        i18n.set_language("en")
        answers(bad)
        assert prompt_index(5, "x") is None
        assert "Cancelled" not in capsys.readouterr().out
        i18n.set_language("sq")

    def test_a_single_letter_is_a_usable_category_name_again(self, app, answers, capsys):
        """The collision the whole change exists to remove."""
        from personal_finance.ui import add_category, delete_category

        answers("2", "a")
        add_category(app)
        capsys.readouterr()

        answers("2", "1", "po")  # kind, pick the category, confirm
        delete_category(app)
        assert app.categories(EXPENSE) == []

    def test_the_prompt_names_the_cancel_word(self):
        assert "anulo" in i18n.t("ask_number_category")
        i18n.set_language("en")
        assert "cancel" in i18n.t("ask_number_category")
        i18n.set_language("sq")

    def test_cancelling_a_date_filter(self, app, answers, capsys):
        from personal_finance.ui import filter_single_date

        answers("anulo")
        filter_single_date(app)
        assert "Anuluar" in capsys.readouterr().out

    def test_cancelling_a_category_name_prompt(self, app, answers, capsys):
        from personal_finance.ui import add_category

        answers("2", "anulo")
        add_category(app)
        assert "Anuluar" in capsys.readouterr().out
        assert app.categories(EXPENSE) == []


class TestRuleSuggestionOnManualEntry:
    """A rule suggests, it does not decide.

    Pre-filling would let a rule written weeks ago choose the category on an
    unread Enter. During an import the preview catches that; a single manual
    entry has no preview, so the rule is shown and the user still answers.
    """

    def test_a_matching_rule_is_shown(self, app, answers, capsys):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        capsys.readouterr()

        answers("Argëtim")
        prompt_category(app, EXPENSE, description="E-commerce 0STEAMGAMES.CO")
        assert "Sugjerim" in capsys.readouterr().out

    def test_the_suggestion_is_not_pre_filled(self, app, answers, capsys):
        """Enter still means "no category", not "accept the suggestion"."""
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        capsys.readouterr()

        answers("")
        assert prompt_category(app, EXPENSE, description="0STEAMGAMES.CO") is None

    def test_the_user_can_choose_something_else(self, app, answers, capsys):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        capsys.readouterr()

        answers("Dhurata")
        assert prompt_category(app, EXPENSE, description="0STEAMGAMES.CO") == "Dhurata"

    def test_nothing_is_shown_without_a_match(self, app, answers, capsys):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        capsys.readouterr()

        answers("Ushqim")
        prompt_category(app, EXPENSE, description="Ushqime nga dyqani")
        assert "Sugjerim" not in capsys.readouterr().out

    def test_nothing_is_shown_when_editing(self, app, answers, capsys):
        """Editing already has a value; a suggestion would only be noise."""
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        capsys.readouterr()

        answers("")
        prompt_category(app, EXPENSE, current="Dhurata", description="0STEAMGAMES.CO")
        assert "Sugjerim" not in capsys.readouterr().out

    def test_adding_a_transaction_shows_the_suggestion(self, app, answers, capsys):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        capsys.readouterr()

        answers("1", "E-commerce 0STEAMGAMES.CO", "50", "po", "Argëtim", "")
        add_transactions(app, EXPENSE)
        output = capsys.readouterr().out
        assert "Sugjerim" in output
        assert app.transactions()[-1].category == "Argëtim"


class TestTheMessageCatalogs:
    """A message in one language and not the other falls back to Albanian, so a
    missing English one shows up as Albanian in the middle of an English screen."""

    def test_both_languages_have_the_same_messages(self):
        from personal_finance.i18n import MESSAGES

        assert set(MESSAGES["sq"]) == set(MESSAGES["en"])

    def test_none_is_empty(self):
        from personal_finance.i18n import MESSAGES

        for language, catalog in MESSAGES.items():
            assert all(text.strip() for text in catalog.values()), language
