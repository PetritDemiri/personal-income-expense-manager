"""Tests for signing in, sessions and password resets.

What this feature is and is not, since the tests assume it: on a shared
machine it keeps one person from casually reading another's finances. It is
not protection against someone holding the database file, who can open it in
any SQLite browser. It exists here because the web interface will need exactly
this, and proving it against the command line is cheaper than discovering it
is wrong once a browser depends on it.

Sessions are why a password does not make the program unscriptable.
"""

import datetime
import os

import pytest

from personal_finance import auth
from personal_finance.auth import RESET_ATTEMPTS, SESSION_HOURS, ResetOutcome
from personal_finance.passwords import (
    MIN_LENGTH,
    generate_code,
    hash_token,
    normalise_code,
    password_problems,
    tokens_match,
)


@pytest.fixture
def user(db):
    return db.add_user("Mami", "Fjalekalimi1")


class TestPasswordRules:
    @pytest.mark.parametrize("password", ["Fjalekalimi1", "Abcdefg1", "X1abcdefg"])
    def test_acceptable(self, password):
        assert password_problems(password) == []

    def test_too_short(self):
        assert "password_too_short" in password_problems("Abc1")

    def test_needs_a_capital(self):
        assert "password_needs_upper" in password_problems("fjalekalimi1")

    def test_needs_a_digit(self):
        assert "password_needs_digit" in password_problems("Fjalekalimi")

    def test_every_failure_is_reported_at_once(self):
        """Otherwise the rules are learned one rejection at a time."""
        assert len(password_problems("abc")) == 3

    def test_the_minimum_length_is_what_is_checked(self):
        assert password_problems("A1" + "x" * (MIN_LENGTH - 3)) != []
        assert password_problems("A1" + "x" * (MIN_LENGTH - 2)) == []

    def test_an_empty_password_fails_everything(self):
        assert len(password_problems("")) == 3
        assert len(password_problems(None)) == 3


class TestOneTimeCodes:
    def test_the_code_is_nine_characters(self):
        from personal_finance.passwords import CODE_LENGTH

        code = generate_code()
        assert len(code) == CODE_LENGTH
        assert "-" not in code and " " not in code

    def test_it_is_grouped_for_display(self):
        from personal_finance.passwords import format_code

        assert format_code("K7MQ2X9RT") == "K7M Q2X 9RT"

    def test_ambiguous_characters_are_excluded(self):
        """O against 0 and I against 1 are what a person misreads."""
        many = "".join(generate_code() for _ in range(300))
        assert not set("O0I1L") & set(many)

    def test_codes_differ(self):
        assert len({generate_code() for _ in range(50)}) > 45

    def test_the_code_has_no_separator(self):
        """Grouping is a display concern; the code itself is nine characters."""
        assert normalise_code("K7MQ2X9RT") == "K7MQ2X9RT"

    @pytest.mark.parametrize("typed", [" K7MQ2X9RT", "K7MQ2X9RT ", "K7M Q2X 9RT", "K7M-Q2X-9RT"])
    def test_grouping_and_whitespace_are_discarded(self, typed):
        """Neither is part of the code, so neither may cost an attempt."""
        assert normalise_code(typed) == "K7MQ2X9RT"

    @pytest.mark.parametrize("typed", ["k7m-q2x-9rt", "K7m-Q2x-9Rt", "K7MQ2X9RT", "K7M Q2X 9RT"])
    def test_anything_else_does_not_match(self, typed):
        """The code must be entered exactly as shown, dashes and capitals both."""
        assert normalise_code(typed) != "K7M-Q2X-9RT"

    def test_a_token_is_stored_hashed(self):
        stored = hash_token("K7M-Q2X-9RT")
        assert "K7M" not in stored
        assert tokens_match("K7M-Q2X-9RT", stored)
        assert not tokens_match("AAA-BBB-CCC", stored)


class TestAuthenticating:
    def test_the_right_password(self, db, user):
        assert auth.authenticate(db, user, "Fjalekalimi1")

    def test_the_wrong_password(self, db, user):
        assert not auth.authenticate(db, user, "gabim")

    def test_a_user_without_one_never_authenticates(self, db):
        """Absent is not the same as empty; it must not let anyone in."""
        other = db.add_user("Babi")
        assert not auth.authenticate(db, other, "")
        assert not auth.authenticate(db, other, "anything")

    def test_a_weak_hash_is_upgraded_on_success(self, db, user):
        """A login is the one moment the plain password is in hand."""
        from personal_finance.passwords import ITERATIONS, hash_password

        digest, salt, _ = hash_password("Fjalekalimi1", iterations=1000)
        with db.connection as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, password_salt = ?, "
                "password_iters = 1000 WHERE id = ?",
                (digest, salt, user),
            )
        assert auth.authenticate(db, user, "Fjalekalimi1")
        assert db.user(user).password_iters == ITERATIONS

    def test_the_upgraded_hash_still_verifies(self, db, user):
        from personal_finance.passwords import hash_password

        digest, salt, _ = hash_password("Fjalekalimi1", iterations=1000)
        with db.connection as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, password_salt = ?, "
                "password_iters = 1000 WHERE id = ?",
                (digest, salt, user),
            )
        auth.authenticate(db, user, "Fjalekalimi1")
        assert auth.authenticate(db, user, "Fjalekalimi1")


class TestSessions:
    def test_a_token_resolves_to_its_user(self, db, user):
        token = auth.start_session(db, user)
        assert auth.session_user(db, token) == user

    def test_an_unknown_token_resolves_to_nobody(self, db, user):
        auth.start_session(db, user)
        assert auth.session_user(db, "nonsense") is None
        assert auth.session_user(db, None) is None

    def test_the_token_is_not_stored_in_the_clear(self, db, user):
        """Reading the table must not yield anything presentable as a login."""
        token = auth.start_session(db, user)
        found = db.connection.execute(
            "SELECT 1 FROM sessions WHERE token_hash = ?", (token,)
        ).fetchone()
        assert found is None

    def test_an_expired_session_is_refused_and_removed(self, db, user):
        token = auth.start_session(db, user)
        with db.connection as conn:
            conn.execute("UPDATE sessions SET expires_at = '2020-01-01 00:00:00'")
        assert auth.session_user(db, token) is None
        assert db.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0

    def test_signing_out_ends_it(self, db, user):
        token = auth.start_session(db, user)
        auth.end_session(db, token)
        assert auth.session_user(db, token) is None

    def test_one_user_signing_out_leaves_another_alone(self, db, user):
        """Logging yourself out should not log out someone else."""
        other = db.add_user("Babi", "Fjalekalimi2")
        mine = auth.start_session(db, user)
        theirs = auth.start_session(db, other)
        auth.end_session(db, mine)
        assert auth.session_user(db, theirs) == other

    def test_the_session_lasts_the_stated_time(self, db, user):
        auth.start_session(db, user)
        expires = db.connection.execute("SELECT expires_at FROM sessions").fetchone()[0]
        when = datetime.datetime.strptime(expires, "%Y-%m-%d %H:%M:%S")
        hours = (when - datetime.datetime.now()).total_seconds() / 3600
        assert SESSION_HOURS - 1 < hours <= SESSION_HOURS

    def test_expired_sessions_are_purged(self, db, user):
        auth.start_session(db, user)
        with db.connection as conn:
            conn.execute("UPDATE sessions SET expires_at = '2020-01-01 00:00:00'")
        auth.purge_expired(db)
        assert db.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0

    def test_the_token_file_round_trips(self, db, user):
        token = auth.start_session(db, user)
        auth.write_token(db.path, token)
        assert auth.read_token(db.path) == token
        auth.clear_token(db.path)
        assert auth.read_token(db.path) is None

    def test_the_token_file_is_owner_only(self, db, user):
        """Where the platform supports it; Windows ignores these bits."""
        if os.name == "nt":
            pytest.skip("POSIX permissions do not apply on Windows")
        auth.write_token(db.path, auth.start_session(db, user))
        mode = os.stat(auth.session_path(db.path)).st_mode & 0o777
        assert mode == 0o600


class TestResettingAForgottenPassword:
    def test_a_code_is_written_to_a_file(self, db, user, tmp_path):
        from personal_finance.passwords import format_code

        code, path = auth.begin_reset(db, user, str(tmp_path), "Mami")
        assert os.path.exists(path)
        # Written grouped, which is how the entry boxes show it.
        assert format_code(code) in open(path, encoding="utf-8").read()

    def test_the_code_is_stored_hashed(self, db, user, tmp_path):
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        stored = db.connection.execute("SELECT code_hash FROM password_resets").fetchone()[0]
        assert code not in stored

    def test_the_right_code_is_accepted(self, db, user, tmp_path):
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        assert auth.check_code(db, user, code)[0] == ResetOutcome.OK

    def test_surrounding_whitespace_is_forgiven(self, db, user, tmp_path):
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        assert auth.check_code(db, user, f"  {code}  ")[0] == ResetOutcome.OK

    def test_the_wrong_case_is_refused(self, db, user, tmp_path):
        """And costs an attempt, like any other wrong code."""
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        outcome, left = auth.check_code(db, user, code.lower())
        assert outcome == ResetOutcome.WRONG
        assert left == RESET_ATTEMPTS - 1

    def test_the_grouped_form_is_accepted(self, db, user, tmp_path):
        """What the file shows must work if it is typed back verbatim."""
        from personal_finance.passwords import format_code

        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        assert auth.check_code(db, user, format_code(code))[0] == ResetOutcome.OK

    def test_a_wrong_code_counts_against_the_attempts(self, db, user, tmp_path):
        auth.begin_reset(db, user, str(tmp_path), "Mami")
        outcome, left = auth.check_code(db, user, "AAA-BBB-CCC")
        assert outcome == ResetOutcome.WRONG
        assert left == RESET_ATTEMPTS - 1

    def test_running_out_of_attempts_cancels_the_reset(self, db, user, tmp_path):
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        for _ in range(RESET_ATTEMPTS - 1):
            auth.check_code(db, user, "AAA-BBB-CCC")
        assert auth.check_code(db, user, "AAA-BBB-CCC")[0] == ResetOutcome.EXHAUSTED
        assert auth.check_code(db, user, code)[0] == ResetOutcome.NONE

    def test_guessing_cannot_continue_by_running_it_again(self, db, user, tmp_path):
        auth.begin_reset(db, user, str(tmp_path), "Mami")
        for _ in range(RESET_ATTEMPTS):
            auth.check_code(db, user, "AAA-BBB-CCC")
        assert auth.check_code(db, user, "AAA-BBB-CCC")[0] == ResetOutcome.NONE

    def test_an_expired_code_is_refused(self, db, user, tmp_path):
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        with db.connection as conn:
            conn.execute("UPDATE password_resets SET expires_at = '2020-01-01 00:00:00'")
        assert auth.check_code(db, user, code)[0] == ResetOutcome.EXPIRED

    def test_a_code_works_only_once(self, db, user, tmp_path):
        code, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        assert auth.check_code(db, user, code)[0] == ResetOutcome.OK
        assert auth.check_code(db, user, code)[0] == ResetOutcome.NONE

    def test_a_new_request_invalidates_the_old_code(self, db, user, tmp_path):
        first, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        second, _ = auth.begin_reset(db, user, str(tmp_path), "Mami")
        assert auth.check_code(db, user, first)[0] == ResetOutcome.WRONG
        assert auth.check_code(db, user, second)[0] == ResetOutcome.OK

    def test_no_reset_in_progress(self, db, user):
        assert auth.check_code(db, user, "AAA-BBB-CCC")[0] == ResetOutcome.NONE

    def test_finishing_sets_the_new_password(self, db, user, tmp_path):
        code, path = auth.begin_reset(db, user, str(tmp_path), "Mami")
        auth.check_code(db, user, code)
        auth.finish_reset(db, user, "Fjalekalimi2", path)
        assert auth.authenticate(db, user, "Fjalekalimi2")
        assert not auth.authenticate(db, user, "Fjalekalimi1")

    def test_finishing_deletes_the_code_file(self, db, user, tmp_path):
        code, path = auth.begin_reset(db, user, str(tmp_path), "Mami")
        auth.check_code(db, user, code)
        auth.finish_reset(db, user, "Fjalekalimi2", path)
        assert not os.path.exists(path)

    def test_finishing_ends_every_session(self, db, user, tmp_path):
        """A login granted under the old password must not survive it."""
        token = auth.start_session(db, user)
        code, path = auth.begin_reset(db, user, str(tmp_path), "Mami")
        auth.check_code(db, user, code)
        auth.finish_reset(db, user, "Fjalekalimi2", path)
        assert auth.session_user(db, token) is None


class TestChangingAPassword:
    def test_the_current_one_is_required(self, db, user):
        """Without this anyone at the keyboard could take over the account."""
        assert not auth.change_password(db, user, "gabim", "Fjalekalimi2")
        assert auth.authenticate(db, user, "Fjalekalimi1")

    def test_the_right_current_one_works(self, db, user):
        assert auth.change_password(db, user, "Fjalekalimi1", "Fjalekalimi2")
        assert auth.authenticate(db, user, "Fjalekalimi2")

    def test_a_user_without_one_can_set_it(self, db):
        other = db.add_user("Babi")
        assert auth.change_password(db, other, "", "Fjalekalimi1")
        assert auth.authenticate(db, other, "Fjalekalimi1")

    def test_changing_it_ends_every_session(self, db, user):
        token = auth.start_session(db, user)
        auth.change_password(db, user, "Fjalekalimi1", "Fjalekalimi2")
        assert auth.session_user(db, token) is None


class TestTheServiceLayer:
    def test_no_login_is_needed_without_a_password(self, app):
        assert not app.needs_login()

    def test_a_login_is_needed_once_one_is_set(self, app):
        app.set_password(app.user_id, "Fjalekalimi1")
        assert app.needs_login()

    def test_signing_in_removes_the_need(self, app):
        app.set_password(app.user_id, "Fjalekalimi1")
        assert app.sign_in("Fjalekalimi1")
        assert not app.needs_login()

    def test_a_wrong_password_does_not(self, app):
        app.set_password(app.user_id, "Fjalekalimi1")
        assert not app.sign_in("gabim")
        assert app.needs_login()

    def test_signing_out_brings_it_back(self, app):
        app.set_password(app.user_id, "Fjalekalimi1")
        app.sign_in("Fjalekalimi1")
        app.sign_out()
        assert app.needs_login()

    def test_a_session_survives_a_new_connection(self, tmp_path):
        """This is what makes the program scriptable with a password set."""
        from personal_finance.app import FinanceApp

        path = str(tmp_path / "finance.db")
        first = FinanceApp(path=path, quiet=True)
        first.set_password(first.user_id, "Fjalekalimi1")
        first.sign_in("Fjalekalimi1")
        first.close()

        second = FinanceApp(path=path, quiet=True)
        assert not second.needs_login()
        second.close()


class TestMigrationFromVersionSeven:
    def test_the_tables_are_added_and_data_survives(self, tmp_path):
        import sqlite3

        from personal_finance.database import Database
        from personal_finance.schema import SCHEMA, SCHEMA_VERSION, all_audit_triggers

        path = str(tmp_path / "finance.db")
        connection = sqlite3.connect(path)
        text = SCHEMA
        start = text.index("-- A logged-in session.")
        end = text.index("-- Append only.")
        text = text[:start] + text[end:]
        text = "\n".join(
            line
            for line in text.split("\n")
            if "idx_sessions_user" not in line and "idx_resets_user" not in line
        )
        connection.executescript(text)
        connection.executescript(all_audit_triggers(connection))
        connection.execute("PRAGMA user_version = 7")
        connection.execute("INSERT INTO users (name, name_key) VALUES ('Une','une')")
        connection.execute(
            "INSERT INTO transactions (user_id,kind,description,amount_cents,occurred_on)"
            " VALUES (1,'Shpenzime','Qera',30000,'2026-08-01')"
        )
        connection.commit()
        connection.close()

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        assert db.count_transactions() == 1
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        token = auth.start_session(db, 1)
        assert auth.session_user(db, token) == 1
        db.close()


class TestBoxedEntry:
    """Typing a code into boxes that fill as you go.

    The boxes are drawn with escape codes and read a keystroke at a time,
    which needs a real terminal. Where there is not one - a pipe, a script,
    these tests - it falls back to reading a line, and the same input is
    accepted either way.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors

        colors.configure(force_off=True)

    def test_empty_boxes(self):
        from personal_finance.codeentry import render

        assert render("", 9) == "[_][_][_] [_][_][_] [_][_][_]"

    def test_boxes_fill_from_the_left(self):
        from personal_finance.codeentry import render

        assert render("XCQ", 9) == "[X][C][Q] [_][_][_] [_][_][_]"

    def test_full_boxes(self):
        from personal_finance.codeentry import render

        assert render("XCQ2ESB3Z", 9) == "[X][C][Q] [2][E][S] [B][3][Z]"

    def test_the_grouping_matches_the_file(self):
        """What the boxes show and what the code file shows must agree."""
        from personal_finance.codeentry import render
        from personal_finance.passwords import format_code

        drawn = render("XCQ2ESB3Z", 9).replace("[", "").replace("]", "")
        assert drawn == format_code("XCQ2ESB3Z")

    def test_it_falls_back_to_a_line_when_there_is_no_terminal(self, monkeypatch):
        from personal_finance import codeentry

        monkeypatch.setattr("builtins.input", lambda _prompt="": "XCQ2ESB3Z")
        assert codeentry.prompt_code("Kodi: ", 9) == "XCQ2ESB3Z"

    def test_the_fallback_handles_no_input_at_all(self, monkeypatch):
        from personal_finance import codeentry

        def raise_eof(_prompt=""):
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        assert codeentry.prompt_code("Kodi: ", 9) is None


class TestSigningOutFromTheMenu:
    """Signing out should not need a command-line flag.

    It ends the session and exits together, because signing out without
    leaving would put someone back in front of the data they had just signed
    out of.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    @pytest.fixture
    def answers(self, monkeypatch):
        def feed(*values):
            queue = list(values)

            def fake_input(_prompt=""):
                if not queue:
                    raise AssertionError("asked for more input than expected")
                return queue.pop(0)

            monkeypatch.setattr("builtins.input", fake_input)

        return feed

    def test_it_ends_the_session_and_asks_to_stop(self, app, answers, capsys):
        from personal_finance.ui import sign_out_and_exit

        app.set_password(app.user_id, "Fjalekalimi1")
        app.sign_in("Fjalekalimi1")
        assert not app.needs_login()
        capsys.readouterr()

        answers("po")
        assert sign_out_and_exit(app) is True
        assert app.needs_login()

    def test_declining_leaves_the_session_alone(self, app, answers, capsys):
        from personal_finance.ui import sign_out_and_exit

        app.set_password(app.user_id, "Fjalekalimi1")
        app.sign_in("Fjalekalimi1")
        capsys.readouterr()

        answers("jo")
        assert sign_out_and_exit(app) is False
        assert not app.needs_login()

    def test_a_user_without_a_password_has_nothing_to_sign_out_of(self, app, capsys):
        from personal_finance.ui import sign_out_and_exit

        assert sign_out_and_exit(app) is False
        assert "asnje sesion" in capsys.readouterr().out

    def test_it_is_not_in_the_users_submenu(self, app, capsys, monkeypatch):
        """It lives on the main menu instead."""
        from personal_finance.ui import users_menu

        seen = []

        def fake_input(prompt=""):
            seen.append(capsys.readouterr().out)
            # Whatever the last entry is, it is "back".
            numbers = [
                int(line.split(".")[0])
                for line in seen[-1].split("\n")
                if line.strip()[:1].isdigit() and "." in line
            ]
            return str(max(numbers))

        monkeypatch.setattr("builtins.input", fake_input)
        users_menu(app)
        assert "Mbyll sesionin" not in "".join(seen)

    def test_it_stays_out_of_the_users_submenu_even_with_a_password(self, app, capsys, monkeypatch):
        """Signing out is not a user-management action. It belongs on the main
        menu, where anyone would look for it."""
        from personal_finance.ui import users_menu

        app.set_password(app.user_id, "Fjalekalimi1")
        capsys.readouterr()
        seen = []

        def fake_input(prompt=""):
            seen.append(capsys.readouterr().out)
            numbers = [
                int(line.split(".")[0])
                for line in seen[-1].split("\n")
                if line.strip()[:1].isdigit() and "." in line
            ]
            return str(max(numbers))

        monkeypatch.setattr("builtins.input", fake_input)
        users_menu(app)
        assert "Mbyll sesionin" not in "".join(seen)


class TestTheSignInLoop:
    """The program loops between the sign-in screen and the menu.

    Signing out returns to the screen rather than ending the program, so
    someone else can sign in without restarting it. Leaving is offered at the
    screen, which is the one place where nobody's data is on show.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_the_main_menu_ends_with_signing_out(self):
        from personal_finance.ui import MENU_ITEMS

        assert MENU_ITEMS[-1][0] == "menu_logout"

    def test_leaving_is_offered_at_the_sign_in_screen(self, app, capsys, monkeypatch):
        from personal_finance.ui import choose_user

        app.set_password(app.user_id, "Fjalekalimi1")
        capsys.readouterr()

        shown = []

        def fake_input(_prompt=""):
            shown.append(capsys.readouterr().out)
            # One user, then "new user", then leaving: the third entry.
            return "3"

        monkeypatch.setattr("builtins.input", fake_input)
        assert choose_user(app) is None
        assert "Dil nga programi" in "".join(shown)

    def test_choosing_it_stops(self, app, capsys, monkeypatch):
        from personal_finance.ui import choose_user

        app.set_password(app.user_id, "Fjalekalimi1")
        app.add_user("Mami")
        capsys.readouterr()

        # Two users, then "new user", then leave: the fourth entry.
        monkeypatch.setattr("builtins.input", lambda _prompt="": "4")
        assert choose_user(app) is None

    def test_the_entry_says_what_it_does_with_a_sign_in_screen(self, app):
        app.set_password(app.user_id, "Fjalekalimi1")
        assert app.sign_in_applies()

    def test_and_says_what_it_does_without_one(self, app):
        """One user and no password: the same entry simply leaves."""
        assert not app.sign_in_applies()


class TestTheSignInScreensAreSpacedOut:
    """A blank line before each question, so the lists above them can be read.

    What the user typed stays attached to what it produced: the confirmation
    of signing out, and the goodbye, follow straight on.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_a_blank_line_precedes_the_who_are_you_question(self, app, capsys, monkeypatch):
        from personal_finance.ui import choose_user

        app.set_password(app.user_id, "Fjalekalimi1")
        capsys.readouterr()
        shown = []

        def fake_input(_prompt=""):
            shown.append(capsys.readouterr().out)
            return "3"

        monkeypatch.setattr("builtins.input", fake_input)
        choose_user(app)
        assert shown[0].endswith("\n\n")

    def test_a_blank_line_precedes_the_sign_out_question(self, app, capsys, monkeypatch):
        from personal_finance.ui import sign_out_and_exit

        app.set_password(app.user_id, "Fjalekalimi1")
        app.sign_in("Fjalekalimi1")
        capsys.readouterr()
        shown = []

        def fake_input(_prompt=""):
            shown.append(capsys.readouterr().out)
            return "jo"

        monkeypatch.setattr("builtins.input", fake_input)
        sign_out_and_exit(app)
        assert shown[0] == "\n"

    def test_a_blank_line_precedes_the_welcome(self, app, capsys, monkeypatch):
        from personal_finance.ui import run_menu

        monkeypatch.setattr("builtins.input", lambda _prompt="": "21")
        capsys.readouterr()
        run_menu(app)
        assert capsys.readouterr().out.startswith("\n")
