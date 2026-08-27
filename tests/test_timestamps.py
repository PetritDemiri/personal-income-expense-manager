"""Tests for created_at and updated_at.

A column DEFAULT fires only on INSERT, so before 3.2.0 `updated_at` recorded
the creation time forever and quietly claimed a row had never changed. The
database maintains it with triggers now, rather than the code remembering to
set it at each of eight write sites - two of which are raw SQL in the service
layer and know nothing about timestamps.
"""

import sqlite3
import time
from decimal import Decimal

from personal_finance.database import Database
from personal_finance.models import Account, RecurringRule, Transaction
from personal_finance.schema import (
    EXPENSE,
    MIGRATIONS,
    SCHEMA,
    SCHEMA_VERSION,
    TOUCHED_TABLES,
)


def stamps(db, table, row_id):
    row = db.connection.execute(
        f"SELECT created_at, updated_at FROM {table} WHERE id = ?", (row_id,)
    ).fetchone()
    return row["created_at"], row["updated_at"]


class TestSchema:
    def test_every_touched_table_has_a_trigger(self, db):
        names = {
            row[0]
            for row in db.connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        for table in TOUCHED_TABLES:
            assert f"touch_{table}" in names, table

    def test_every_touched_table_actually_has_the_columns(self, db):
        for table in TOUCHED_TABLES:
            columns = {row[1] for row in db.connection.execute(f"PRAGMA table_info({table})")}
            assert "created_at" in columns and "updated_at" in columns, table

    def test_the_schema_version_is_current(self, db):
        assert db.schema_version == SCHEMA_VERSION


class TestTimestampsOnWrite:
    def test_both_are_set_on_insert(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        created, updated = stamps(db, "transactions", transaction_id)
        assert created and updated
        assert created == updated

    def test_updated_moves_on_edit_and_created_does_not(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        created_before, updated_before = stamps(db, "transactions", transaction_id)
        time.sleep(1.1)
        db.update_transaction(transaction_id, amount=Decimal("350"))
        created_after, updated_after = stamps(db, "transactions", transaction_id)

        assert created_after == created_before
        assert updated_after > updated_before

    def test_a_raw_update_is_stamped_too(self, db):
        """The service layer writes raw SQL in places; the trigger covers it."""
        account_id = db.add_account(Account(name="Petrit"))
        _, before = stamps(db, "accounts", account_id)
        time.sleep(1.1)
        with db.connection as conn:
            conn.execute("UPDATE accounts SET name = 'Petriti' WHERE id = ?", (account_id,))
        _, after = stamps(db, "accounts", account_id)
        assert after > before

    def test_renaming_a_category_stamps_it(self, db):
        category_id = db.ensure_category("Ushqim", EXPENSE)
        _, before = stamps(db, "categories", category_id)
        time.sleep(1.1)
        db.update_category(category_id, "Ushqime")
        _, after = stamps(db, "categories", category_id)
        assert after > before

    def test_advancing_a_recurring_rule_stamps_it(self, db):
        rule_id = db.add_recurring_rule(
            RecurringRule(
                kind=EXPENSE, description="Qera", amount=Decimal("300"), starts_on="01-01-2026"
            )
        )
        _, before = stamps(db, "recurring_rules", rule_id)
        time.sleep(1.1)
        db.set_rule_generated_upto(rule_id, "01-02-2026")
        _, after = stamps(db, "recurring_rules", rule_id)
        assert after > before

    def test_one_row_stamped_does_not_stamp_another(self, db):
        first = db.add_transaction(Transaction(EXPENSE, "A", Decimal("1"), "01-08-2026"))
        second = db.add_transaction(Transaction(EXPENSE, "B", Decimal("1"), "01-08-2026"))
        _, before = stamps(db, "transactions", second)
        time.sleep(1.1)
        db.update_transaction(first, amount=Decimal("2"))
        _, after = stamps(db, "transactions", second)
        assert after == before

    def test_the_trigger_does_not_recurse(self, db):
        """An AFTER UPDATE trigger that updates its own table could loop."""
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"))
        assert db.transaction(transaction_id).amount == Decimal("350")


class TestExposedOnTheView:
    def test_the_view_carries_both(self, db):
        db.add_transaction(Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026"))
        view = db.transactions()[0]
        assert view.created_at
        assert view.updated_at

    def test_the_view_reflects_an_edit(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        before = db.transactions()[0].updated_at
        time.sleep(1.1)
        db.update_transaction(transaction_id, amount=Decimal("350"))
        assert db.transactions()[0].updated_at > before


class TestMigrationFromVersionThree:
    """A database in daily use must upgrade in place, without losing anything."""

    @staticmethod
    def build_v3(path):
        """A database exactly as 3.1.0 left it: full schema, no triggers."""
        connection = sqlite3.connect(path)
        start = SCHEMA.index("-- updated_at is maintained")
        end = SCHEMA.index("CREATE INDEX idx_transactions_date")
        connection.executescript(SCHEMA[:start] + SCHEMA[end:])
        connection.execute("PRAGMA user_version = 3")
        connection.execute(
            "INSERT INTO accounts (name,name_key,kind,opening_cents) "
            "VALUES ('Petrit','petrit','Kesh',0)"
        )
        connection.execute(
            "INSERT INTO categories (name,name_key,kind) VALUES ('Ushqim','ushqim','Shpenzime')"
        )
        connection.execute(
            "INSERT INTO transactions "
            "(kind,description,amount_cents,occurred_on,category_id,account_id) "
            "VALUES ('Shpenzime','Ushqime',4550,'2026-08-03',1,1)"
        )
        connection.commit()
        connection.close()

    def test_a_v3_database_has_no_triggers(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v3(path)
        connection = sqlite3.connect(path)
        triggers = list(connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
        connection.close()
        assert triggers == []

    def test_opening_it_migrates_and_keeps_the_data(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v3(path)

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        rows = db.transactions()
        assert len(rows) == 1
        assert rows[0].amount == Decimal("45.50")
        assert rows[0].category == "Ushqim"
        assert rows[0].account == "Petrit"
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        db.close()

    def test_the_trigger_works_on_a_row_that_predates_it(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v3(path)

        db = Database(path)
        _, before = stamps(db, "transactions", 1)
        time.sleep(1.1)
        db.update_transaction(1, amount=Decimal("50.00"))
        _, after = stamps(db, "transactions", 1)
        assert after > before
        db.close()

    def test_reopening_does_not_migrate_again(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v3(path)

        first = Database(path)
        first.close()
        second = Database(path)
        triggers = len(
            list(second.connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
        )
        assert second.schema_version == SCHEMA_VERSION
        assert triggers == len(TOUCHED_TABLES)
        second.close()

    def test_a_fresh_database_skips_the_migrations(self, tmp_path):
        """A new file gets the whole schema at once, not step by step."""
        db = Database(str(tmp_path / "new.db"))
        assert db.schema_version == SCHEMA_VERSION
        db.close()

    def test_migrations_cover_every_version_up_to_current(self):
        assert max(MIGRATIONS) <= SCHEMA_VERSION
