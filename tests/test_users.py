"""Tests for users.

Version 7 gives every row an owner. The command line stays as it was for
anyone who never creates a second user, but the data model is now the one the
web interface needs, so version 4 is a new frontend rather than a new schema.

The isolation tests carry the weight. A query that forgets its user filter
shows one person another person's money, and nothing about the output would
look wrong.
"""

import sqlite3
from decimal import Decimal

import pytest

from personal_finance.app import FinanceApp
from personal_finance.database import Database, UnknownUser
from personal_finance.models import User
from personal_finance.passwords import (
    ITERATIONS,
    hash_password,
    needs_rehash,
    verify_password,
)
from personal_finance.schema import DEFAULT_USER_NAME, EXPENSE, INCOME, SCHEMA_VERSION


@pytest.fixture
def shared(tmp_path):
    """A database with two users, returned as a path to open under either."""
    return str(tmp_path / "finance.db")


class TestPasswordHashing:
    def test_a_password_verifies(self):
        digest, salt, iterations = hash_password("fjalekalimi im")
        assert verify_password("fjalekalimi im", digest, salt, iterations)

    def test_a_wrong_password_does_not(self):
        digest, salt, iterations = hash_password("fjalekalimi im")
        assert not verify_password("gabim", digest, salt, iterations)

    def test_the_password_is_not_stored(self):
        digest, salt, _ = hash_password("fjalekalimi im")
        assert "fjalekalimi" not in digest
        assert "fjalekalimi" not in salt

    def test_the_same_password_hashes_differently_each_time(self):
        """A fresh salt per password, so two people choosing the same one
        do not end up with the same hash."""
        first, _, _ = hash_password("njejte")
        second, _, _ = hash_password("njejte")
        assert first != second

    def test_an_empty_password_is_refused(self):
        with pytest.raises(ValueError):
            hash_password("")

    def test_verifying_against_nothing_fails(self):
        assert not verify_password("anything", None, None, None)
        assert not verify_password("", "x", "y", 1000)

    def test_the_iteration_count_is_stored_with_the_hash(self):
        """So it can be raised later without invalidating existing passwords."""
        digest, salt, iterations = hash_password("x", iterations=1000)
        assert iterations == 1000
        assert verify_password("x", digest, salt, 1000)
        assert not verify_password("x", digest, salt, 2000)

    def test_needs_rehash(self):
        assert needs_rehash(1000)
        assert not needs_rehash(ITERATIONS)


class TestUserRecords:
    def test_a_database_always_has_a_user(self, db):
        assert len(db.users()) == 1
        assert db.user().name == DEFAULT_USER_NAME

    def test_adding_a_user(self, db):
        db.add_user("Mami")
        assert [u.name for u in db.users()] == [DEFAULT_USER_NAME, "Mami"]

    def test_duplicate_names_are_rejected(self, db):
        db.add_user("Mami")
        with pytest.raises(sqlite3.IntegrityError):
            db.add_user("mami")

    def test_a_user_starts_without_a_password(self, db):
        db.add_user("Mami")
        assert not db.user_by_name("Mami").has_password

    def test_setting_a_password(self, db):
        user_id = db.add_user("Mami")
        db.set_password(user_id, "sekret")
        assert db.user(user_id).has_password
        assert db.check_password(user_id, "sekret")
        assert not db.check_password(user_id, "gabim")

    def test_clearing_a_password(self, db):
        user_id = db.add_user("Mami", "sekret")
        db.set_password(user_id, None)
        assert not db.user(user_id).has_password

    def test_a_user_without_a_password_never_matches(self, db):
        """Absent is not the same as empty; it must not let anyone in."""
        user_id = db.add_user("Mami")
        assert not db.check_password(user_id, "")
        assert not db.check_password(user_id, "anything")

    def test_renaming(self, db):
        user_id = db.add_user("Mami")
        db.rename_user(user_id, "Nena")
        assert db.user(user_id).name == "Nena"


class TestChoosingAUser:
    def test_the_first_user_is_the_default(self, shared):
        db = Database(shared)
        db.add_user("Mami")
        db.close()
        assert Database(shared).user().name == DEFAULT_USER_NAME

    def test_a_named_user_is_used(self, shared):
        db = Database(shared)
        db.add_user("Mami")
        db.close()
        assert Database(shared, user="Mami").user().name == "Mami"

    def test_the_name_is_matched_ignoring_case(self, shared):
        db = Database(shared)
        db.add_user("Mami")
        db.close()
        assert Database(shared, user="MAMI").user().name == "Mami"

    def test_an_unknown_user_is_refused(self, shared):
        Database(shared).close()
        with pytest.raises(UnknownUser):
            Database(shared, user="NukEkziston")


class TestIsolation:
    """A query that forgets its user filter shows one person another's money."""

    @pytest.fixture
    def two_users(self, shared):
        first = FinanceApp(path=shared, quiet=True)
        first.add_transaction(INCOME, "Paga e pare", Decimal("1200"), "01-08-2026", "Paga")
        first.add_account("Banka", "Banke", Decimal("500"))
        first.set_budget("Ushqim", Decimal("200"))
        first.add_category_rule("STEAM", "Argëtim", EXPENSE)
        first.add_user("Mami")
        first.close()
        return shared

    def test_a_new_user_sees_nothing(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        assert second.count() == 0
        assert second.accounts() == []
        assert second.categories(INCOME) == []
        assert second.budgets() == []
        assert second.category_rules() == []
        second.close()

    def test_what_one_adds_the_other_cannot_see(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        second.add_transaction(EXPENSE, "Ushqime", Decimal("45"), "02-08-2026", "Ushqim")
        second.close()

        first = FinanceApp(path=two_users, quiet=True)
        assert [x.description for x in first.transactions()] == ["Paga e pare"]
        first.close()

    def test_both_can_have_a_category_with_the_same_name(self, two_users):
        """The reason four tables had to be rebuilt rather than altered."""
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        second.add_transaction(INCOME, "Paga e dyte", Decimal("800"), "03-08-2026", "Paga")
        assert [c.name for c in second.categories(INCOME)] == ["Paga"]
        second.close()

    def test_both_can_have_an_account_with_the_same_name(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        second.add_account("Banka", "Banke", Decimal("100"))
        assert [a.name for a in second.accounts()] == ["Banka"]
        second.close()

        first = FinanceApp(path=two_users, quiet=True)
        assert len(first.accounts()) == 1
        assert first.accounts()[0].opening == Decimal("500.00")
        first.close()

    def test_both_can_have_a_rule_with_the_same_pattern(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        second.add_category_rule("STEAM", "Lojëra", EXPENSE)
        assert len(second.category_rules()) == 1
        second.close()

    def test_the_history_is_separate(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        before = second.db.audit_count()
        second.add_transaction(EXPENSE, "Ushqime", Decimal("45"), "02-08-2026", "Ushqim")
        assert second.db.audit_count() == before + 2  # the transaction and its category
        second.close()

    def test_the_history_records_who(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        second.add_transaction(EXPENSE, "Ushqime", Decimal("45"), "02-08-2026", "Ushqim")
        entries = second.history(entity="transactions")
        assert entries
        assert all(e.entity_id is not None for e in entries)
        second.close()

    def test_balances_do_not_mix(self, two_users):
        from personal_finance.reports import calculate_totals

        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        second.add_transaction(EXPENSE, "Ushqime", Decimal("45"), "02-08-2026", "Ushqim")
        assert calculate_totals(second.transactions()).income == Decimal("0.00")
        second.close()

        first = FinanceApp(path=two_users, quiet=True)
        assert calculate_totals(first.transactions()).income == Decimal("1200.00")
        first.close()

    def test_is_empty_is_per_user(self, two_users):
        second = FinanceApp(path=two_users, quiet=True, user="Mami")
        assert second.db.is_empty()
        second.close()

        first = FinanceApp(path=two_users, quiet=True)
        assert not first.db.is_empty()
        first.close()


class TestDeletingAUser:
    def test_their_data_goes_with_them(self, shared):
        first = FinanceApp(path=shared, quiet=True)
        user_id = first.add_user("Mami")
        first.close()

        second = FinanceApp(path=shared, quiet=True, user="Mami")
        second.add_transaction(EXPENSE, "Ushqime", Decimal("45"), "02-08-2026", "Ushqim")
        second.close()

        first = FinanceApp(path=shared, quiet=True)
        first.delete_user(user_id)
        rows = first.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        assert rows == 0
        first.close()

    def test_the_other_user_is_untouched(self, shared):
        first = FinanceApp(path=shared, quiet=True)
        first.add_transaction(INCOME, "Paga", Decimal("1200"), "01-08-2026", "Paga")
        user_id = first.add_user("Mami")
        first.delete_user(user_id)
        assert first.count() == 1
        first.close()


class TestMigrationFromVersionSix:
    """The upgrade a database in daily use actually takes."""

    @staticmethod
    def build_v6(path):
        from .conftest import audit_triggers_before_users, schema_before_users

        connection = sqlite3.connect(path)
        connection.executescript(schema_before_users())
        connection.executescript(audit_triggers_before_users())
        connection.execute("PRAGMA user_version = 6")

        connection.execute(
            "INSERT INTO accounts (name,name_key,kind,opening_cents) "
            "VALUES ('Banka','banka','Banke',85000)"
        )
        connection.execute(
            "INSERT INTO categories (name,name_key,kind) VALUES ('Ushqim','ushqim','Shpenzime')"
        )
        connection.execute(
            "INSERT INTO subcategories (name,name_key,category_id) VALUES ('Dyqan','dyqan',1)"
        )
        connection.execute(
            "INSERT INTO category_rules (pattern,pattern_key,category_id) "
            "VALUES ('STEAM','steam',1)"
        )
        connection.execute("INSERT INTO budgets (category_id,limit_cents) VALUES (1,20000)")
        connection.execute(
            "INSERT INTO transactions (kind,description,amount_cents,occurred_on,"
            "category_id,subcategory_id,account_id) "
            "VALUES ('Shpenzime','Ushqime',18540,'2026-08-10',1,1,1)"
        )
        connection.commit()
        connection.close()

    def test_everything_survives(self, tmp_path):
        """Four tables are rebuilt; nothing may be lost doing it."""
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        assert db.count_transactions() == 1
        assert len(db.accounts()) == 1
        assert len(db.categories()) == 1
        assert len(db.subcategories(1)) == 1
        assert len(db.category_rules()) == 1
        assert len(db.budgets()) == 1
        db.close()

    def test_the_money_is_unchanged(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        db = Database(path)
        assert db.transactions()[0].amount == Decimal("185.40")
        assert db.accounts()[0].opening == Decimal("850.00")
        db.close()

    def test_a_single_user_is_created_and_owns_everything(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        db = Database(path)
        assert len(db.users()) == 1
        orphans = db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id IS NULL"
        ).fetchone()[0]
        assert orphans == 0
        db.close()

    def test_the_database_is_sound_afterwards(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        db = Database(path)
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.connection.execute("PRAGMA foreign_key_check").fetchall()
        db.close()

    def test_references_still_resolve(self, tmp_path):
        """A rebuild that broke a foreign key would leave names missing."""
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        db = Database(path)
        view = db.transactions()[0]
        assert view.category == "Ushqim"
        assert view.subcategory == "Dyqan"
        assert view.account == "Banka"
        db.close()

    def test_reopening_does_not_migrate_again(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        Database(path).close()
        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        assert len(db.users()) == 1
        db.close()

    def test_a_second_user_can_be_added_after_migrating(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v6(path)

        db = Database(path)
        db.add_user("Mami")
        db.close()

        second = Database(path, user="Mami")
        assert second.count_transactions() == 0
        second.close()


class TestUserModel:
    def test_the_key_folds_case(self):
        assert User("Petrit").key == User("PETRIT").key

    def test_has_password(self):
        assert not User("Petrit").has_password
        assert User("Petrit", password_hash="x", password_salt="y").has_password


class TestNoNoteThatPasswordsAreOnlyForTheWeb:
    """The users screen and the password prompt both said the command line
    never asks for a password - untrue since 3.9.0 added signing in."""

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_not_on_the_users_screen(self, app, capsys):
        from personal_finance.ui import show_users

        show_users(app)
        shown = capsys.readouterr().out
        assert "internetit" not in shown
        assert "rreshti i komandes" not in shown

    def test_not_when_setting_a_password(self, app, monkeypatch, capsys):
        import builtins

        from personal_finance.ui import set_user_password

        replies = iter(["1", "anulo"])
        monkeypatch.setattr(builtins, "input", lambda _prompt="": next(replies))
        set_user_password(app)
        assert "internetit" not in capsys.readouterr().out

    def test_not_in_english_either(self, app, capsys):
        from personal_finance import i18n
        from personal_finance.ui import show_users

        i18n.set_language("en")
        show_users(app)
        assert "web interface" not in capsys.readouterr().out

    def test_the_message_is_gone_from_both_languages(self):
        from personal_finance.i18n import MESSAGES

        assert all("password_note" not in catalog for catalog in MESSAGES.values())
