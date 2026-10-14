"""Typing the cancel word on screens that ask several questions.

Since 3.9.0 the shared prompts answer "anulo" with a step back rather than a
value. Adding income or expenses understood that. Editing a transaction, a
transfer, assigning an account, a rule, a budget, a recurring transaction and
the import's questions did not: they passed the step back on as if it were an
answer, and the program crashed - on the very word the screen tells people to
type. Each of them now steps back one question, or cancels where the question
is the only one.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from personal_finance import colors, i18n
from personal_finance.models import BANK, CASH
from personal_finance.schema import EXPENSE, INCOME, TRANSFER

FIXTURE = Path(__file__).parent / "fixtures" / "teb_statement.htm"


@pytest.fixture(autouse=True)
def plain():
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield
    i18n.set_language("sq")


@pytest.fixture
def answers(monkeypatch):
    """Feed answers to input(), failing if the screen asks for more.

    Returns the list of prompts asked, so a test can see what was offered.
    """

    def feed(*values):
        queue = list(values)
        asked = []

        def fake_input(prompt=""):
            asked.append(prompt)
            if not queue:
                raise AssertionError(f"asked for more than expected: {prompt!r}")
            return queue.pop(0)

        monkeypatch.setattr("builtins.input", fake_input)
        return asked

    return feed


def backing_out(reach, steps):
    """The answers that reach a question and then cancel all the way out:
    the answers before it, then the cancel word once for it and once for
    every question before it."""
    return list(reach[:steps]) + ["anulo"] * (steps + 1)


class TestEditingATransaction:
    @pytest.fixture
    def rent(self, app, capsys):
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        capsys.readouterr()
        return app

    def stored(self, app):
        view = app.transactions()[0]
        return (view.kind, view.description, view.amount, view.occurred_on, view.category)

    def test_cancelling_the_first_question_changes_nothing(self, rent, answers, capsys):
        from personal_finance.ui import edit_transaction

        before = self.stored(rent)
        answers("1", "anulo")
        edit_transaction(rent)
        assert self.stored(rent) == before
        assert "Anuluar." in capsys.readouterr().out

    # type, description, amount, date, category, subcategory - each kept.
    KEEP_ALL = ("", "", "", "", "", "")

    @pytest.mark.parametrize("question", range(6))
    def test_no_question_crashes_on_it(self, rent, answers, capsys, question):
        """It used to crash on every one of them but the type."""
        from personal_finance.ui import edit_transaction

        before = self.stored(rent)
        answers("1", *backing_out(self.KEEP_ALL, question))
        edit_transaction(rent)
        assert self.stored(rent) == before
        assert "Anuluar." in capsys.readouterr().out

    def test_it_steps_back_one_question(self, rent, answers):
        from personal_finance.ui import edit_transaction

        # pick, keep the type, keep the description, cancel at the amount -
        # which goes back to the description - then a new description and
        # the rest kept.
        answers("1", "", "", "anulo", "Qera e re", "", "", "", "")
        edit_transaction(rent)
        view = rent.transactions()[0]
        assert view.description == "Qera e re"
        assert view.amount == Decimal("300")

    def test_stepping_back_offers_the_answer_just_given(self, rent, answers):
        """Going back to look must not undo what was typed there."""
        from personal_finance.ui import edit_transaction

        asked = answers("1", "", "Qera e re", "anulo", "", "", "", "", "")
        edit_transaction(rent)
        assert "Pershkrimi [Qera e re]: " in asked
        assert rent.transactions()[0].description == "Qera e re"

    def test_the_type_can_still_be_changed(self, rent, answers):
        from personal_finance.ui import edit_transaction

        answers("1", "1", "", "", "", "", "")
        edit_transaction(rent)
        assert rent.transactions()[0].kind == INCOME

    def test_cancelling_is_said_once_when_it_starts(self, rent, answers, capsys):
        from personal_finance.ui import edit_transaction

        answers("1", "anulo")
        edit_transaction(rent)
        assert capsys.readouterr().out.count("(Shkruani 'anulo' per t'u kthyer)") == 1


class TestAddingATransfer:
    @pytest.fixture
    def two(self, app, capsys):
        app.add_account("Banka", BANK, Decimal("500"))
        app.add_account("Kesh", CASH, Decimal("0"))
        capsys.readouterr()
        return app

    # from, to, description, amount, today
    REACH = ("1", "2", "Terheqje", "200", "po")

    @pytest.mark.parametrize("question", range(5))
    def test_no_question_crashes_on_it(self, two, answers, capsys, question):
        from personal_finance.ui import add_transfer

        answers(*backing_out(self.REACH, question))
        add_transfer(two)
        assert two.transactions() == []
        assert "Anuluar." in capsys.readouterr().out

    def test_it_steps_back_one_question(self, two, answers):
        from personal_finance.ui import add_transfer

        # Cancelling at the description goes back to where the money goes,
        # which can then be answered differently.
        answers("2", "1", "anulo", "1", "anulo", "1", "Depozite", "200", "po")
        add_transfer(two)
        stored = two.transactions()[0]
        assert stored.kind == TRANSFER
        assert stored.description == "Depozite"

    def test_the_same_account_twice_is_still_refused(self, two, answers, capsys):
        from personal_finance.ui import add_transfer

        answers("1", "1", "2", "Terheqje", "200", "po")
        add_transfer(two)
        assert "njejta" in capsys.readouterr().out
        assert two.transactions()[0].to_account == "Kesh"


class TestAssigningAnAccount:
    def test_cancelling_the_account_assigns_nothing(self, app, answers, capsys):
        from personal_finance.ui import assign_unassigned_transactions

        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        app.add_account("Banka", BANK, Decimal("500"))
        capsys.readouterr()
        answers("anulo")
        assign_unassigned_transactions(app)
        assert app.transactions()[0].account_id is None
        assert "Anuluar." in capsys.readouterr().out


class TestAddingARule:
    def test_cancelling_the_type_saves_nothing(self, app, answers, capsys):
        from personal_finance.ui import add_rule

        answers("STEAM", "anulo")
        add_rule(app)
        assert app.category_rules() == []
        assert "Anuluar." in capsys.readouterr().out

    def test_cancelling_the_category_steps_back_to_the_type(self, app, answers):
        from personal_finance.ui import add_rule

        # pattern, expense, cancel at the category, then income instead.
        answers("STEAM", "2", "anulo", "1", "Dhurata", "", "po")
        add_rule(app)
        rule = app.category_rules()[0]
        assert rule.category == "Dhurata"
        assert app.db.category(rule.category_id).kind == INCOME

    def test_cancelling_the_subcategory_steps_back_to_the_category(self, app, answers):
        from personal_finance.ui import add_rule

        answers("STEAM", "2", "Argetim", "anulo", "Lojera", "", "po")
        add_rule(app)
        assert app.category_rules()[0].category == "Lojera"

    def test_no_category_is_still_refused(self, app, answers, capsys):
        from personal_finance.ui import add_rule

        answers("STEAM", "2", "")
        add_rule(app)
        assert app.category_rules() == []


class TestSettingABudget:
    def test_cancelling_the_category_sets_nothing(self, app, answers, capsys):
        from personal_finance.ui import set_budget

        answers("anulo")
        set_budget(app)
        assert app.budgets() == []
        assert "Anuluar." in capsys.readouterr().out

    def test_cancelling_the_amount_steps_back_to_the_category(self, app, answers):
        from personal_finance.ui import set_budget

        answers("Ushqim", "anulo", "Transport", "120")
        set_budget(app)
        budgets = app.budgets()
        assert len(budgets) == 1
        assert app.category_name_map()[budgets[0].category_id] == "Transport"

    def test_no_category_is_still_refused_without_asking_the_amount(self, app, answers):
        from personal_finance.ui import set_budget

        answers("")
        set_budget(app)
        assert app.budgets() == []


class TestAddingARecurringTransaction:
    # type, description, amount, category, subcategory, frequency, not today
    REACH = ("2", "Qera", "300", "Qera", "", "2", "jo")

    @pytest.mark.parametrize("question", range(7))
    def test_no_question_crashes_on_it(self, app, answers, capsys, question):
        from personal_finance.ui import add_recurring

        answers(*backing_out(self.REACH, question))
        add_recurring(app)
        assert app.recurring_rules() == []
        assert "Anuluar." in capsys.readouterr().out

    def test_cancelling_the_date_steps_back_to_the_frequency(self, app, answers):
        from personal_finance.ui import add_recurring

        # ... monthly, cancel at "today?", then yearly instead.
        answers("2", "Qera", "300", "Qera", "", "2", "anulo", "3", "jo", "01-01-2027")
        add_recurring(app)
        assert app.recurring_rules()[0].frequency == "vjetore"

    def test_it_still_asks_for_an_account(self, app, answers, capsys):
        from personal_finance.ui import add_recurring

        app.add_account("Banka", BANK, Decimal("0"))
        capsys.readouterr()
        answers("2", "Qera", "300", "Qera", "", "1", "2", "jo", "01-01-2027")
        add_recurring(app)
        assert app.recurring_rules()[0].account_id is not None


class TestTheImport:
    def test_cancelling_a_category_change_leaves_it_as_it_was(self, app, answers, capsys):
        from personal_finance.importing import Candidate
        from personal_finance.ui import set_candidate_category

        candidate = Candidate(
            row_number=2,
            kind=EXPENSE,
            description="Qera",
            amount=Decimal("300"),
            occurred_on="01-08-2026",
            category="Qera",
        )
        answers("anulo")
        set_candidate_category(app, [candidate], "1")
        assert candidate.category == "Qera"

    def test_cancelling_the_account_of_a_file_cancels_the_import(
        self, app, answers, capsys, tmp_path
    ):
        from personal_finance.ui import import_from_file

        app.add_account("Banka", BANK, Decimal("500"))
        capsys.readouterr()
        path = tmp_path / "levizjet.csv"
        path.write_text("Data,Pershkrimi,Shuma\n01-09-2026,Qera,-300.00\n", encoding="utf-8")
        answers("anulo")
        import_from_file(app, path=str(path))
        assert app.transactions() == []
        assert "Importimi u anulua" in capsys.readouterr().out

    def test_cancelling_the_account_of_a_statement_cancels_the_import(self, app, answers, capsys):
        from personal_finance.ui import import_from_file

        app.add_account("TEB", BANK, Decimal("0"))
        capsys.readouterr()
        answers("anulo")
        import_from_file(app, path=str(FIXTURE))
        assert app.transactions() == []
        assert "Importimi u anulua" in capsys.readouterr().out


class TestAddingAnAccount:
    """The name used to be taken as typed, so cancelling made an account
    called "anulo"."""

    def test_cancelling_the_name_makes_nothing(self, app, answers, capsys):
        from personal_finance.ui import add_account

        answers("anulo")
        add_account(app)
        assert app.accounts() == []
        assert "Anuluar." in capsys.readouterr().out

    # name, cash, opening balance
    REACH = ("Kesh", "1", "40")

    @pytest.mark.parametrize("question", range(3))
    def test_no_question_takes_it_as_an_answer(self, app, answers, capsys, question):
        from personal_finance.ui import add_account

        answers(*backing_out(self.REACH, question))
        add_account(app)
        assert app.accounts() == []

    def test_it_steps_back_one_question(self, app, answers):
        from personal_finance.ui import add_account

        # name, cancel at the kind, another name, bank, opening balance
        answers("Kesh", "anulo", "Banka", "2", "850")
        add_account(app)
        [account] = app.accounts()
        assert (account.name, account.kind, account.opening) == ("Banka", BANK, Decimal("850"))

    def test_a_name_already_used_is_still_refused(self, app, answers, capsys):
        from personal_finance.ui import add_account

        app.add_account("Kesh", CASH, Decimal("0"))
        capsys.readouterr()
        answers("Kesh", "Banka", "2", "")
        add_account(app)
        assert "ekziston" in capsys.readouterr().out
        assert [a.name for a in app.accounts()] == ["Kesh", "Banka"]


class TestChangingAnAccount:
    @pytest.fixture
    def cash(self, app, capsys):
        app.add_account("Kesh", CASH, Decimal("40"))
        capsys.readouterr()
        return app

    def test_cancelling_the_name_changes_nothing(self, cash, answers, capsys):
        from personal_finance.ui import edit_account

        answers("1", "anulo")
        edit_account(cash)
        [account] = cash.accounts()
        assert (account.name, account.opening) == ("Kesh", Decimal("40"))
        assert "Anuluar." in capsys.readouterr().out

    def test_it_steps_back_offering_the_answer_just_given(self, cash, answers):
        from personal_finance.ui import edit_account

        asked = answers("1", "Xhepi", "anulo", "", "", "")
        edit_account(cash)
        assert "Emri [Xhepi] (Enter = pa ndryshim): " in asked
        assert cash.accounts()[0].name == "Xhepi"

    def test_enter_keeps_everything(self, cash, answers):
        from personal_finance.ui import edit_account

        answers("1", "", "", "")
        edit_account(cash)
        [account] = cash.accounts()
        assert (account.name, account.kind, account.opening) == ("Kesh", CASH, Decimal("40"))
