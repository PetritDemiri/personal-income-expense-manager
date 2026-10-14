"""A digit that is not 0 to 9.

`str.isdigit()` says yes to "²", "³" and "①" - characters a keyboard can type
with AltGr - and int() then refuses them. Every number check written with it
let them through to a crash: a stray AltGr+2 at the main menu ended the
program, and so it did at the sign-in screen, before anyone had signed in.
Only 0 to 9 are digits now, wherever a number is typed.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from personal_finance import colors, i18n
from personal_finance.models import BANK, CASH, whole_number
from personal_finance.schema import EXPENSE

from .conftest import claim_database

ODD = ["²", "³", "①", "١", "2²"]


@pytest.fixture(autouse=True)
def plain():
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield
    i18n.set_language("sq")


@pytest.fixture
def answers(monkeypatch):
    def feed(*values):
        queue = list(values)

        def fake_input(prompt=""):
            if not queue:
                raise AssertionError(f"asked for more than expected: {prompt!r}")
            return queue.pop(0)

        monkeypatch.setattr("builtins.input", fake_input)

    return feed


class TestWholeNumbers:
    @pytest.mark.parametrize(("typed", "number"), [("0", 0), ("7", 7), ("21", 21), ("007", 7)])
    def test_plain_digits_are_a_number(self, typed, number):
        assert whole_number(typed) == number

    @pytest.mark.parametrize("typed", [*ODD, "", " 2", "2 ", "-1", "+1", "1.5", "1e3", "abc"])
    def test_anything_else_is_not(self, typed):
        assert whole_number(typed) is None


class TestTheMenus:
    @pytest.mark.parametrize("odd", ODD)
    def test_the_main_menu(self, app, answers, capsys, odd):
        from personal_finance.ui import run_menu

        answers(odd, "21")
        run_menu(app)
        assert "Zgjedhje e pavlefshme" in capsys.readouterr().out

    def test_the_sign_in_screen(self, app, answers, capsys):
        from personal_finance.ui import choose_user

        app.set_password(app.user_id, "Fjalekalimi1")
        answers("²", "3")
        assert choose_user(app) is None
        assert "Numer i pavlefshem." in capsys.readouterr().out

    def test_the_users_menu(self, app, answers, capsys):
        from personal_finance.ui import users_menu

        # An administrator's menu has eight entries, so going back is the ninth.
        assert app.is_admin
        answers("²", "9")
        users_menu(app)
        assert "Zgjedhje e pavlefshme" in capsys.readouterr().out


class TestTheQuestions:
    def test_a_category_number(self, app, answers, capsys):
        from personal_finance.ui import prompt_category

        app.add_transaction(EXPENSE, "x", Decimal("1"), "01-06-2026", "Ushqim")
        answers("²", "1")
        assert prompt_category(app, EXPENSE) == "Ushqim"

    def test_a_subcategory_number(self, app, answers):
        from personal_finance.ui import prompt_subcategory

        app.add_transaction(EXPENSE, "x", Decimal("1"), "01-06-2026", "Ushqim", "Dyqan")
        answers("²", "1")
        assert prompt_subcategory(app, EXPENSE, "Ushqim") == "Dyqan"

    def test_an_account_number(self, app, answers):
        from personal_finance.ui import prompt_account

        account_id = app.add_account("Banka", BANK, Decimal("0"))
        answers("²", "1")
        assert prompt_account(app) == account_id

    def test_an_account_kind(self, answers):
        from personal_finance.ui import prompt_account_kind

        answers("²", "1")
        assert prompt_account_kind() == CASH

    def test_a_frequency(self, answers):
        from personal_finance.ui import prompt_frequency

        answers("²", "2")
        assert prompt_frequency() == "mujore"

    def test_a_number_of_months(self, answers):
        from personal_finance.ui import prompt_span

        answers("²", "6")
        assert prompt_span() == 6

    def test_rows(self):
        from personal_finance.ui import parse_positions

        for typed in ("²", "1, ²", "1-²", "²-3"):
            assert parse_positions(typed, 5) is None

    def test_a_row_to_change_at_the_import_preview(self, app, capsys):
        from personal_finance.importing import Candidate
        from personal_finance.ui import set_candidate_category

        candidate = Candidate(
            row_number=2,
            kind=EXPENSE,
            description="Qera",
            amount=Decimal("300"),
            occurred_on="01-08-2026",
        )
        set_candidate_category(app, [candidate], "²")
        assert "Numer i pavlefshem." in capsys.readouterr().out

    def test_a_column_of_the_file(self, answers):
        from personal_finance.ui import ask_import_columns

        # date, amount, and no description column
        answers("²", "1", "2", "0")
        mapping = ask_import_columns(["Data", "Shuma"], {})
        assert mapping == {"date": 0, "amount": 1}

    def test_a_file_among_several(self, tmp_path, answers, monkeypatch):
        from personal_finance import ui

        found = [(str(tmp_path / "a.csv"), "Downloads"), (str(tmp_path / "a.htm"), "Downloads")]
        monkeypatch.setattr("personal_finance.locations.find_import_candidates", lambda _t: found)
        answers("²", "2")
        assert ui.choose_import_file("a") == found[1][0]


class TestTheCommandLine:
    def test_a_chart_span(self, tmp_path, capsys):
        from personal_finance.cli import main

        path = claim_database(tmp_path)
        main(["--baza", path, "--grafiku", "²"])
        assert "Zgjidhni nje nga: 3, 6, 12." in capsys.readouterr().out


class TestNamesThatContainOne:
    """A category made by a flag or an import is not checked the way a typed
    one is, so it can hold any character - and sorting the list of
    categories took a digit-looking character for a number."""

    def test_they_sort_without_a_crash(self):
        from personal_finance.collation import sort_names

        assert sort_names(["Ushqim²", "Paga"]) == ["Paga", "Ushqim²"]

    def test_real_numbers_in_names_still_sort_as_numbers(self):
        from personal_finance.collation import sort_names

        assert sort_names(["Kati 10", "Kati 9"]) == ["Kati 9", "Kati 10"]

    def test_a_category_like_that_still_lists(self, app):
        app.add_transaction(EXPENSE, "x", Decimal("1"), "01-06-2026", "Ushqim²")
        app.add_transaction(EXPENSE, "y", Decimal("1"), "01-06-2026", "Qera")
        assert app.category_names(EXPENSE) == ["Qera", "Ushqim²"]


class TestABankStatement:
    def test_an_odd_digit_in_the_row_count_is_not_a_crash(self):
        """The count is read from the last cell that looks like a number."""
        from personal_finance.statements import parse_statement

        fixture = Path(__file__).parent / "fixtures" / "teb_statement.htm"
        raw = fixture.read_bytes().decode("utf-16")
        marked = raw.replace(">8<", ">²<", 1)
        assert marked != raw
        statement = parse_statement(marked.encode("utf-16"))
        assert statement.stated_count is None


def test_account_names_can_hold_them(app):
    """An account name is free text: such a character is just a character."""
    from personal_finance.accounts import find_account

    app.add_account("Kesh²", CASH, Decimal("0"))
    assert find_account(app.accounts(), "Kesh²") is not None
