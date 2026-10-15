"""Each person's own choice about the typing effect, and where text goes.

The effect is on unless someone switches it off, and switching it off is for
that person alone - in the users menu, remembered for next time. The sign-in
screen belongs to nobody yet, so it is typed for everyone.

Which way text appears is decided where it is shown: menus, lists and tables
roll in, messages are typed, errors appear at once. The last tests here hold
the screens to that.
"""

import ast
import sqlite3
from pathlib import Path

import pytest

from personal_finance import cli, colors, display, i18n, typewriter, ui
from personal_finance.app import FinanceApp
from personal_finance.auth import owns_anything
from personal_finance.database import Database
from personal_finance.i18n import t
from personal_finance.schema import PREFERENCES, SCHEMA, SCHEMA_VERSION, all_audit_triggers

PACKAGE = Path(ui.__file__).parent


@pytest.fixture(autouse=True)
def plain(monkeypatch):
    i18n.set_language("sq")
    colors.configure(force_off=True)
    monkeypatch.setattr(typewriter, "_state", typewriter._State())
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


def preference_rows(app, user_id):
    return app.db.connection.execute(
        "SELECT COUNT(*) FROM preferences WHERE user_id = ?", (user_id,)
    ).fetchone()[0]


class TestTheSetting:
    def test_on_unless_switched_off(self, app):
        assert app.typing_effect() is True

    def test_switched_off_and_on_again(self, app):
        app.set_typing_effect(False)
        assert app.typing_effect() is False
        app.set_typing_effect(True)
        assert app.typing_effect() is True

    def test_remembered_for_next_time(self, tmp_path):
        path = str(tmp_path / "finance.db")
        first = FinanceApp(path=path, quiet=True)
        first.set_typing_effect(False)
        first.close()

        second = FinanceApp(path=path, quiet=True)
        assert second.typing_effect() is False
        second.close()

    def test_each_person_decides_for_themselves(self, app):
        me = app.user_id
        other = app.add_user("Mami")
        app.set_typing_effect(False)

        app.use_user(other)
        assert app.typing_effect() is True
        app.use_user(me)
        assert app.typing_effect() is False

    def test_set_for_one_person_by_id(self, app):
        me = app.user_id
        other = app.add_user("Mami")
        app.db.set_typing_effect(False, user_id=other)
        assert app.db.typing_effect(other) is False
        assert app.db.typing_effect(me) is True

    def test_it_goes_with_the_person(self, app):
        other = app.add_user("Mami")
        app.db.set_typing_effect(False, user_id=other)
        app.delete_user(other)
        assert preference_rows(app, other) == 0

    def test_it_is_not_something_an_account_is_kept_for(self, app):
        """A first-run account that owns nothing is removed; a setting is not
        something it owns."""
        other = app.add_user("Mami")
        app.db.set_typing_effect(False, user_id=other)
        assert not owns_anything(app.db.connection, other)

    def test_it_is_not_in_the_history(self, app):
        """A setting for how the program looks, not a change to anyone's data."""
        counted = "SELECT COUNT(*) FROM audit_log"
        before = app.db.connection.execute(counted).fetchone()[0]
        app.set_typing_effect(False)
        app.set_typing_effect(True)
        assert app.db.connection.execute(counted).fetchone()[0] == before


class TestMigrationFromVersionTen:
    @staticmethod
    def build_v10(path):
        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA.replace(PREFERENCES, ""))
        connection.executescript(all_audit_triggers(connection))
        connection.execute("PRAGMA user_version = 10")
        connection.execute("INSERT INTO users (name, name_key) VALUES ('Une','une')")
        connection.execute(
            "INSERT INTO transactions (user_id,kind,description,amount_cents,occurred_on)"
            " VALUES (1,'Shpenzime','Qera',30000,'2026-08-01')"
        )
        connection.commit()
        connection.close()

    def test_everyone_starts_with_it_on(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v10(path)

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        assert db.typing_effect(1) is True
        db.set_typing_effect(False, user_id=1)
        assert db.typing_effect(1) is False
        db.close()

    def test_the_data_survives(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v10(path)

        db = Database(path)
        assert db.count_transactions() == 1
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        db.close()


class TestTheUsersMenu:
    """Admin menus have ten entries with going back, others four."""

    def test_the_entry_says_whether_it_is_on(self, app, answers, capsys):
        answers("10")
        ui.users_menu(app)
        assert "3. Efekti i shkrimit: i ndezur" in capsys.readouterr().out

    def test_switching_it_off(self, app, answers, capsys):
        typewriter.prefer(True)
        answers("3", "10")
        ui.users_menu(app)
        shown = capsys.readouterr().out
        assert "Efekti i shkrimit u fik." in shown
        assert "3. Efekti i shkrimit: i fikur" in shown
        assert app.typing_effect() is False
        # And at once, not from the next time.
        assert typewriter._state.wanted is False

    def test_switching_it_back_on(self, app, answers, capsys):
        app.set_typing_effect(False)
        typewriter.prefer(False)
        answers("3", "10")
        ui.users_menu(app)
        assert "Efekti i shkrimit u ndez." in capsys.readouterr().out
        assert app.typing_effect() is True
        assert typewriter._state.wanted is True

    def test_it_is_there_for_everyone_not_only_administrators(self, app, answers, capsys):
        other = app.add_user("Mami")
        app.use_user(other)
        assert not app.is_admin
        answers("3", "4")
        ui.users_menu(app)
        assert "3. Efekti i shkrimit: i ndezur" in capsys.readouterr().out
        assert app.typing_effect() is False

    def test_in_english(self, app, answers, capsys):
        i18n.set_language("en")
        answers("3", "10")
        ui.users_menu(app)
        shown = capsys.readouterr().out
        assert "3. Typing effect: on" in shown
        assert "Typing effect turned off." in shown
        assert "3. Typing effect: off" in shown


class TestWhoseChoiceApplies:
    def test_the_menu_follows_whoever_is_signed_in(self, app, answers):
        app.set_typing_effect(False)
        answers("21")
        ui.run_menu(app)
        assert typewriter._state.wanted is False

    def test_and_their_choice_not_the_last_persons(self, app, answers):
        typewriter.prefer(False)
        answers("21")
        ui.run_menu(app)
        assert typewriter._state.wanted is True

    def test_the_sign_in_screen_is_nobodys_yet(self, app, answers):
        """Typed for everyone, whatever the last person chose."""
        app.set_password(app.user_id, "Fjalekalimi1")
        typewriter.prefer(False)
        answers("3")
        assert ui.choose_user(app) is None
        assert typewriter._state.wanted is True


class TestTheCodeBoxes:
    """The one question not asked through the effect: the code boxes read
    the keyboard themselves."""

    @pytest.fixture
    def no_typing(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _prompt="": pytest.fail("asked again"))

    def test_a_code_typed_ahead_goes_into_the_boxes(self, no_typing, capsys):
        from personal_finance.codeentry import prompt_code, render
        from personal_finance.passwords import CODE_ALPHABET

        typewriter._state.pending = ["XCQ 2ES B3Z"]
        assert prompt_code("Kodi: ", 9, allowed=CODE_ALPHABET) == "XCQ2ESB3Z"
        assert render("XCQ2ESB3Z", 9) in capsys.readouterr().out

    def test_only_as_much_as_the_boxes_hold(self, no_typing):
        from personal_finance.codeentry import prompt_code

        typewriter._state.pending = ["XCQ2ESB3ZXCQ"]
        assert prompt_code("Kodi: ", 9) == "XCQ2ESB3Z"

    def test_so_it_never_answers_a_later_question(self, no_typing):
        from personal_finance.codeentry import prompt_code

        typewriter._state.pending = ["XCQ2ESB3Z"]
        prompt_code("Kodi: ", 9)
        assert typewriter.typed_ahead() is None

    def test_the_next_screen_starts_afresh(self, monkeypatch):
        from personal_finance.codeentry import prompt_code

        monkeypatch.setattr("builtins.input", lambda _prompt="": "XCQ2ESB3Z")
        typewriter._state.skipping = True
        typewriter._state.spent = 1.0
        prompt_code("Kodi: ", 9)
        assert (typewriter._state.skipping, typewriter._state.spent) == (False, 0.0)


class TestTheCommandLine:
    @pytest.fixture
    def allowed(self, monkeypatch):
        """What the program let the effect do, in order."""
        calls = []
        monkeypatch.setattr(typewriter, "allow", calls.append)
        monkeypatch.setattr(cli.console, "attended", lambda: True)
        monkeypatch.setattr(cli.console, "set_title", lambda _title: None)
        monkeypatch.setattr(cli.console, "restore_title", lambda: None)
        return calls

    def test_a_person_at_a_terminal_gets_it(self, allowed, monkeypatch):
        monkeypatch.setattr(cli, "run_program", lambda *_: 0)
        assert cli.main([]) == 0
        assert allowed == [True, False]

    def test_a_run_with_flags_never_does(self, allowed, monkeypatch):
        monkeypatch.setattr(cli, "run_program", lambda *_: 0)
        cli.main(["--lista"])
        assert allowed == [False, False]

    def test_it_is_taken_away_even_after_a_failure(self, allowed, monkeypatch):
        def broken(*_):
            raise RuntimeError("boom")

        monkeypatch.setattr(cli, "run_program", broken)
        monkeypatch.setattr(cli.console, "log_crash", lambda: "crash.txt")
        monkeypatch.setattr(cli.console, "report_crash", lambda _path: None)
        monkeypatch.setattr(cli.console, "pause", lambda _message: None)
        assert cli.main([]) == 1
        assert allowed == [True, False]


class TestWhichWayTextAppears:
    @pytest.fixture
    def shown(self, monkeypatch):
        """Everything shown, as (which way, text)."""
        lines = []

        def way(name):
            def show(*parts, sep=" ", end="\n", **_):
                lines.append((name, sep.join(str(part) for part in parts)))

            return show

        monkeypatch.setattr(ui, "say", way("typed"))
        monkeypatch.setattr(ui, "roll", way("rolled"))
        monkeypatch.setattr(display, "roll", way("rolled"))
        monkeypatch.setattr(typewriter, "say", way("typed"))
        monkeypatch.setattr("builtins.print", way("at once"))
        return lines

    def test_the_main_menu(self, app, answers, shown):
        answers("x", "21")
        ui.run_menu(app)
        assert ("typed", f"\n{t('menu')}") in shown
        assert ("rolled", f"1. {t('menu_add_income')}") in shown
        assert ("at once", t("invalid_choice", low=1, high=21)) in shown
        assert ("typed", t("goodbye")) in shown

    def test_a_table(self, app, shown):
        ui.show_users(app)
        assert {way for way, _ in shown} == {"rolled"}

    def test_a_list_of_transactions(self, stocked, shown):
        app, _ = stocked
        ui.show_transactions(app)
        assert {way for way, _ in shown} == {"rolled"}
        assert any("Benzine" in text for _, text in shown)

    def test_leaving_from_the_sign_in_screen(self, app, answers, shown):
        app.set_password(app.user_id, "Fjalekalimi1")
        answers("3")
        assert cli.run_sessions(app) is True
        assert ("typed", t("goodbye")) in shown


def calls_in(module):
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                yield function.id, node
            elif isinstance(function, ast.Attribute):
                yield function.attr, node


def painted_red(node):
    return any(
        isinstance(argument, ast.Call)
        and getattr(argument.func, "id", None) == "paint"
        and any(getattr(colour, "id", None) == "RED" for colour in argument.args[1:])
        for argument in node.args
    )


class TestTheScreensKeepToIt:
    """Read from the source, so a screen added later is held to it too."""

    @pytest.mark.parametrize("module", ["ui", "display"])
    def test_every_question_can_be_skipped_to(self, module):
        """Asked through the effect, so an Enter that skips text is taken
        before the question - never as its answer."""
        names = {name for name, _ in calls_in(module)}
        assert not names & {"input", "getpass"}

    def test_a_list_or_table_always_rolls_in(self):
        names = {name for name, _ in calls_in("display")}
        assert "print" not in names
        assert "say" not in names

    def test_what_appears_at_once_is_an_error(self):
        printed = [node for name, node in calls_in("ui") if name == "print"]
        assert printed
        assert all(painted_red(node) for node in printed)

    def test_an_error_is_never_typed_out(self):
        """A red line in a list rolls in whole, like the rest of the list."""
        for name, node in calls_in("ui"):
            if name == "say":
                assert not painted_red(node), f"ui.py line {node.lineno}"
