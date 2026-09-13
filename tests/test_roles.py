"""Tests for administrators, first-run setup, and who may do what.

Passwords alone were privacy: they kept a second person from reading your
data. What these cover is authorisation - who is signed in decides what they
may do, and one person cannot reach another's account at all.

The first-run flow generates an administrator rather than asking for one,
which is the shape a deployed web version needs, where nobody is at a console
when a database is first created.
"""

import os

import pytest

from personal_finance import auth
from personal_finance.app import FinanceApp
from personal_finance.auth import SETUP_ATTEMPTS, ResetOutcome
from personal_finance.database import Database
from personal_finance.passwords import SETUP_LENGTH, admin_name


@pytest.fixture
def empty(tmp_path, monkeypatch):
    """A database with nobody in it, as a brand-new installation has."""
    monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
    app = FinanceApp(path=str(tmp_path / "finance.db"), quiet=True)
    with app.db.connection as conn:
        conn.execute("DELETE FROM users")
    yield app
    app.close()


class TestGeneratedAdministrator:
    def test_an_empty_database_has_nobody(self, empty):
        assert not empty.has_users

    def test_creating_one_writes_a_file(self, empty, tmp_path):
        name, password, path = empty.create_admin()
        assert os.path.exists(path)
        assert name in open(path, encoding="utf-8").read()

    def test_the_password_is_generated_not_asked_for(self, empty):
        _name, password, _path = empty.create_admin()
        assert len(password) == SETUP_LENGTH

    def test_the_generated_password_satisfies_the_rules(self, empty):
        """A generated password must never fail the check it is measured by."""
        from personal_finance.passwords import password_problems

        _name, password, _path = empty.create_admin()
        assert password_problems(password) == []

    def test_the_name_is_plainly_admin(self, empty):
        """It is read off a file and typed back, so it should be the obvious
        word rather than characters to transcribe."""
        assert admin_name([]) == "admin"

    def test_the_created_account_is_called_admin(self, empty):
        empty.create_admin()
        assert empty.users()[0].name == "admin"

    def test_a_suffix_is_only_reached_if_the_name_is_taken(self):
        assert admin_name(["admin"]) == "admin2"
        assert admin_name(["ADMIN", "admin2"]) == "admin3"

    def test_the_account_is_an_administrator(self, empty):
        empty.create_admin()
        assert empty.users()[0].is_admin

    def test_it_must_change_its_password(self, empty):
        """The generated password is only good enough to sign in and replace."""
        empty.create_admin()
        assert empty.users()[0].must_change

    def test_the_password_is_stored_hashed(self, empty):
        _name, password, _path = empty.create_admin()
        stored = empty.db.connection.execute("SELECT code_hash FROM admin_setup").fetchone()[0]
        assert password not in stored


class TestClaimingIt:
    def test_the_right_password_is_accepted(self, empty):
        _name, password, _path = empty.create_admin()
        assert empty.check_setup_password(password)[0] == ResetOutcome.OK

    def test_the_grouped_form_is_accepted(self, empty):
        """The file shows it grouped; typing that back must work."""
        from personal_finance.passwords import format_code

        _name, password, _path = empty.create_admin()
        assert empty.check_setup_password(format_code(password))[0] == ResetOutcome.OK

    def test_a_wrong_password_costs_an_attempt(self, empty):
        empty.create_admin()
        outcome, left = empty.check_setup_password("AAAAAAAAAAAA")
        assert outcome == ResetOutcome.WRONG
        assert left == SETUP_ATTEMPTS - 1

    def test_running_out_of_attempts_discards_the_account(self, empty):
        """Safe: there is nothing in the database yet to lock anyone out of."""
        _name, password, _path = empty.create_admin()
        for _ in range(SETUP_ATTEMPTS - 1):
            empty.check_setup_password("AAAAAAAAAAAA")
        assert empty.check_setup_password("AAAAAAAAAAAA")[0] == ResetOutcome.EXHAUSTED
        assert not empty.has_users

    def test_an_expired_password_is_refused(self, empty):
        _name, password, _path = empty.create_admin()
        with empty.db.connection as conn:
            conn.execute("UPDATE admin_setup SET expires_at = '2020-01-01 00:00:00'")
        assert empty.check_setup_password(password)[0] == ResetOutcome.EXPIRED

    def test_completing_it_sets_the_chosen_name_and_password(self, empty):
        _name, password, path = empty.create_admin()
        user_id, _ = empty.pending_admin()
        empty.check_setup_password(password)
        empty.complete_setup(user_id, "Petrit", "Fjalekalimi1", path)

        user = empty.users()[0]
        assert user.name == "Petrit"
        assert user.has_password
        assert user.is_admin

    def test_completing_it_clears_the_forced_change(self, empty):
        _name, password, path = empty.create_admin()
        user_id, _ = empty.pending_admin()
        empty.check_setup_password(password)
        empty.complete_setup(user_id, "Petrit", "Fjalekalimi1", path)
        assert not empty.users()[0].must_change

    def test_completing_it_deletes_the_credentials_file(self, empty):
        _name, password, path = empty.create_admin()
        user_id, _ = empty.pending_admin()
        empty.check_setup_password(password)
        empty.complete_setup(user_id, "Petrit", "Fjalekalimi1", path)
        assert not os.path.exists(path)

    def test_the_new_password_signs_in(self, empty):
        _name, password, path = empty.create_admin()
        user_id, _ = empty.pending_admin()
        empty.check_setup_password(password)
        empty.complete_setup(user_id, "Petrit", "Fjalekalimi1", path)
        assert auth.authenticate(empty.db, user_id, "Fjalekalimi1")


class TestAnAbandonedSetup:
    """A setup begun and never finished must not leave the database open.

    It leaves a user row with no password on it, which the ordinary path read
    as a single-user installation that never wanted one - and let the next
    person straight in.
    """

    def test_it_is_still_pending(self, empty):
        empty.create_admin()
        assert empty.setup_pending

    def test_the_user_has_no_password_yet(self, empty):
        empty.create_admin()
        assert not empty.users()[0].has_password

    def test_a_finished_setup_is_not_pending(self, empty):
        _name, password, path = empty.create_admin()
        user_id, _ = empty.pending_admin()
        empty.check_setup_password(password)
        empty.complete_setup(user_id, "Petrit", "Fjalekalimi1", path)
        assert not empty.setup_pending

    def test_reopening_finds_the_same_pending_account(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        path = str(tmp_path / "finance.db")

        first = FinanceApp(path=path, quiet=True)
        with first.db.connection as conn:
            conn.execute("DELETE FROM users")
        name, _password, _file = first.create_admin()
        first.close()

        second = FinanceApp(path=path, quiet=True)
        assert second.setup_pending
        assert second.pending_admin()[1] == name
        second.close()


class TestWhoMayDoWhat:
    @pytest.fixture
    def two(self, tmp_path):
        app = FinanceApp(path=str(tmp_path / "finance.db"), quiet=True)
        admin = app.users()[0].id
        app.set_admin(admin, True)
        ordinary = app.add_user("Mami", "Fjalekalimi2")
        return app, admin, ordinary

    def test_an_administrator_may_manage_users(self, two):
        app, admin, _ordinary = two
        app.use_user(admin)
        assert app.is_admin

    def test_an_ordinary_user_may_not(self, two):
        app, _admin, ordinary = two
        app.use_user(ordinary)
        assert not app.is_admin

    def test_a_new_user_is_not_an_administrator(self, two):
        app, _admin, ordinary = two
        assert not app.db.user(ordinary).is_admin

    def test_the_role_can_be_granted(self, two):
        app, _admin, ordinary = two
        app.set_admin(ordinary, True)
        assert app.db.user(ordinary).is_admin

    def test_the_role_can_be_taken_away(self, two):
        app, admin, ordinary = two
        app.set_admin(ordinary, True)
        app.set_admin(ordinary, False)
        assert not app.db.user(ordinary).is_admin

    def test_the_administrators_can_be_counted(self, two):
        app, _admin, ordinary = two
        assert app.admin_count() == 1
        app.set_admin(ordinary, True)
        assert app.admin_count() == 2

    def test_data_is_still_separate_regardless_of_role(self, two):
        """A role governs managing users, never seeing another's money."""
        from decimal import Decimal

        from personal_finance.schema import EXPENSE

        app, admin, ordinary = two
        app.use_user(ordinary)
        app.add_transaction(EXPENSE, "Ushqime", Decimal("45"), "01-09-2026", "Ushqim")

        app.use_user(admin)
        assert app.count() == 0


class TestMigrationFromVersionEight:
    @staticmethod
    def build_v8(path):
        import sqlite3

        from personal_finance.schema import SCHEMA, all_audit_triggers

        connection = sqlite3.connect(path)
        text = SCHEMA
        for fragment in (
            "    -- Whether this user may manage other users. Everything else in the\n",
            "    -- program is already scoped to its owner; this is the one thing that\n",
            "    -- reaches across people, so it is the one thing that needs a role.\n",
            "    is_admin       INTEGER NOT NULL DEFAULT 0,\n",
            "    -- Set when an account is created with a generated password, and cleared\n",
            "    -- once the user has chosen their own.\n",
            "    must_change    INTEGER NOT NULL DEFAULT 0,\n",
        ):
            text = text.replace(fragment, "")
        start = text.index("CREATE TABLE admin_setup (")
        end = text.index("-- A logged-in session.")
        text = text[:start] + text[end:]

        connection.executescript(text)
        # Passed the connection so no trigger is built for a column that
        # version 8 does not have yet.
        connection.executescript(all_audit_triggers(connection))
        connection.execute("PRAGMA user_version = 8")
        connection.execute("INSERT INTO users (name, name_key) VALUES ('Une','une')")
        connection.execute("INSERT INTO users (name, name_key) VALUES ('Mami','mami')")
        connection.execute(
            "INSERT INTO transactions (user_id,kind,description,amount_cents,occurred_on)"
            " VALUES (1,'Shpenzime','Qera',30000,'2026-08-01')"
        )
        connection.commit()
        connection.close()

    def test_everyone_who_already_existed_becomes_an_administrator(self, tmp_path):
        """They had every power a program with no roles offered."""
        path = str(tmp_path / "finance.db")
        self.build_v8(path)

        db = Database(path)
        assert all(user.is_admin for user in db.users())
        db.close()

    def test_the_data_survives(self, tmp_path):
        from personal_finance.schema import SCHEMA_VERSION

        path = str(tmp_path / "finance.db")
        self.build_v8(path)

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        assert db.count_transactions() == 1
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        db.close()

    def test_nobody_is_asked_to_change_their_password(self, tmp_path):
        """That flag is for generated accounts, not existing ones."""
        path = str(tmp_path / "finance.db")
        self.build_v8(path)

        db = Database(path)
        assert not any(user.must_change for user in db.users())
        db.close()


class TestUserChangesAreRecorded:
    """Renaming, granting the role and changing a password reach across
    people, so they belong in the history. The hash never does.

    This is what justifies an administrator being able to reset someone
    else's password at all: it cannot be prevented, but it cannot be hidden
    either - the account's owner sees that it happened and when.
    """

    @pytest.fixture
    def two(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        app = FinanceApp(path=str(tmp_path / "finance.db"), quiet=True)
        admin = app.users()[0].id
        app.set_admin(admin, True)
        mami = app.add_user("Mami", "Fjalekalimi2")
        app.use_user(admin)
        return app, admin, mami

    def test_creating_a_user_is_recorded(self, two):
        app, _admin, mami = two
        app.use_user(mami)
        assert any(e.action == "create" for e in app.history(entity="users"))

    def test_a_rename_is_recorded(self, two):
        app, _admin, mami = two
        app.rename_user(mami, "Nena")
        app.use_user(mami)
        changed = [f for e in app.history(entity="users") for f, _b, _a in e.changes()]
        assert "name" in changed

    def test_granting_the_role_is_recorded(self, two):
        app, _admin, mami = two
        app.set_admin(mami, True)
        app.use_user(mami)
        changed = [f for e in app.history(entity="users") for f, _b, _a in e.changes()]
        assert "is_admin" in changed

    def test_an_administrator_resetting_a_password_is_recorded(self, two):
        """The account's owner can see it happened, even though they could
        not have stopped it."""
        app, _admin, mami = two
        code, path = app.begin_reset(mami)
        app.check_reset_code(mami, code)
        app.finish_reset(mami, "Fjalekalimi3", path)

        app.use_user(mami)
        changed = [f for e in app.history(entity="users") for f, _b, _a in e.changes()]
        assert "password_set_at" in changed

    def test_two_password_changes_in_quick_succession_both_show(self, two):
        """Recorded to the microsecond; a whole second would collapse the two
        into a change with nothing in it."""
        app, _admin, mami = two
        app.db.set_password(mami, "Fjalekalimi3")
        app.db.set_password(mami, "Fjalekalimi4")

        app.use_user(mami)
        stamps = [
            after
            for e in app.history(entity="users")
            for field, _b, after in e.changes()
            if field == "password_set_at"
        ]
        assert len(set(stamps)) == len(stamps)

    def test_no_password_hash_is_ever_written_to_the_log(self, two):
        """An append-only log outlives the password it would record."""
        app, _admin, mami = two
        app.db.set_password(mami, "Fjalekalimi3")

        stored = app.db.user(mami).password_hash
        rows = app.db.connection.execute(
            "SELECT COALESCE(before_json, '') || COALESCE(after_json, '') FROM audit_log"
        ).fetchall()
        assert stored
        assert not any(stored in row[0] for row in rows)

    def test_the_new_fields_read_as_labels_not_column_names(self):
        from personal_finance import i18n
        from personal_finance.display import field_label

        assert field_label("is_admin") == "Administrator"
        assert field_label("password_set_at") == "Fjalekalimi ndryshuar"
        i18n.set_language("en")
        assert field_label("password_set_at") == "Password changed"
        i18n.set_language("sq")


class TestTheSetupScreenIsSpacedOut:
    """Each fact stands on its own line, separated.

    The name and the password are read off the screen and typed back, so
    crowding them together is how a character gets misread - and a misread
    character costs one of only three attempts.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_the_credentials_each_stand_apart(self, empty, capsys, monkeypatch):
        from personal_finance.ui import run_first_setup

        monkeypatch.setattr("builtins.input", lambda _prompt="": "anulo")
        capsys.readouterr()
        run_first_setup(empty)

        lines = capsys.readouterr().out.split("\n")
        for marker in ("u shkruan ne:", "Administratori:", "Skadojne pas"):
            position = next(i for i, line in enumerate(lines) if marker in line)
            assert lines[position - 1] == "", f"no blank line before {marker!r}"

    def test_a_blank_line_precedes_the_password_prompt(self, empty, capsys, monkeypatch):
        from personal_finance.ui import run_first_setup

        monkeypatch.setattr("builtins.input", lambda _prompt="": "anulo")
        capsys.readouterr()
        run_first_setup(empty)

        lines = capsys.readouterr().out.split("\n")
        position = next(i for i, line in enumerate(lines) if "Skadojne pas" in line)
        assert lines[position + 1] == ""


class TestAnUnclaimedDatabaseCannotBeUsed:
    """A database nobody has claimed belongs to nobody.

    Until this was fixed, any flag on an empty database invented an
    administrator with no password on it, and the generated-credentials flow
    then never ran because users existed. One `--lista` claimed the database
    silently, and whoever opened it afterwards walked straight in.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    @pytest.fixture
    def unclaimed(self, tmp_path, monkeypatch):
        """A database file with no users in it."""
        from personal_finance.app import FinanceApp

        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        app = FinanceApp(path=str(tmp_path / "finance.db"), quiet=True)
        with app.db.connection as conn:
            conn.execute("DELETE FROM users")
        app.close()
        return str(tmp_path / "finance.db")

    def test_a_flag_is_refused(self, unclaimed, capsys):
        from personal_finance.cli import main

        assert main(["--baza", unclaimed, "--lista"]) == 1
        assert "nuk ka asnje perdorues" in capsys.readouterr().out

    def test_it_says_what_to_do(self, unclaimed, capsys):
        from personal_finance.cli import main

        main(["--baza", unclaimed, "--lista"])
        assert "pa asnje opsion" in capsys.readouterr().out

    def test_no_user_is_invented(self, unclaimed, capsys):
        """The whole point: a flag must not quietly become the owner."""
        import sqlite3

        from personal_finance.cli import main

        main(["--baza", unclaimed, "--lista"])
        connection = sqlite3.connect(unclaimed)
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        connection.close()

    def test_a_writing_flag_is_refused_too(self, unclaimed, capsys):
        from personal_finance.cli import main

        assert main(["--baza", unclaimed, "--shto-llogari", "Banka", "Banke", "0"]) == 1

    def test_an_abandoned_setup_is_refused_as_well(self, tmp_path, monkeypatch, capsys):
        """It leaves a user with no password, which is not a claim either."""
        from personal_finance.app import FinanceApp
        from personal_finance.cli import main

        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        path = str(tmp_path / "finance.db")
        app = FinanceApp(path=path, quiet=True)
        with app.db.connection as conn:
            conn.execute("DELETE FROM users")
        app.create_admin()
        app.close()

        assert main(["--baza", path, "--lista"]) == 1

    def test_a_claimed_database_works_normally(self, tmp_path, monkeypatch, capsys):
        from personal_finance.app import FinanceApp
        from personal_finance.cli import main

        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        path = str(tmp_path / "finance.db")
        FinanceApp(path=path, quiet=True).close()

        capsys.readouterr()
        assert main(["--baza", path, "--lista"]) == 0
        assert "nuk ka asnje perdorues" not in capsys.readouterr().out
