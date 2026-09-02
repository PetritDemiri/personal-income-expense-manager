"""Tests for the change history.

Every create, update and delete on a financial table is recorded by database
triggers. Triggers rather than application code for the same reason the
timestamps use them: the writes are spread across two modules, two of them raw
SQL, and a missed site would leave a silent gap in a record whose whole value
is being complete.

The counting tests carry the most weight. Measured during design, a separate
timestamp trigger beside the audit trigger recorded two entries for every edit
- the change, then the timestamp the change caused.
"""

import sqlite3
import time
from decimal import Decimal

import pytest

from personal_finance.database import Database
from personal_finance.models import Account, Category, RecurringRule, Transaction
from personal_finance.schema import (
    AUDITED_TABLES,
    EXPENSE,
    SCHEMA_VERSION,
    all_audit_triggers,
)


def entries(db, entity=None, entity_id=None):
    return db.audit_entries(entity=entity, entity_id=entity_id, limit=100)


class TestOneEntryPerChange:
    def test_creating_records_one_entry(self, db):
        db.add_transaction(Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026"))
        found = entries(db, "transactions")
        assert len(found) == 1
        assert found[0].action == "create"

    def test_editing_records_exactly_one_entry(self, db):
        """A second trigger on the same UPDATE would record two."""
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"))
        updates = [e for e in entries(db, "transactions") if e.action == "update"]
        assert len(updates) == 1

    def test_three_edits_record_three_entries(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        for amount in ("310", "320", "330"):
            db.update_transaction(transaction_id, amount=Decimal(amount))
        updates = [e for e in entries(db, "transactions") if e.action == "update"]
        assert len(updates) == 3

    def test_deleting_records_one_entry(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.delete_transaction(transaction_id)
        deletes = [e for e in entries(db, "transactions") if e.action == "delete"]
        assert len(deletes) == 1

    def test_a_full_lifecycle_records_three(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"))
        db.delete_transaction(transaction_id)
        assert len(entries(db, "transactions")) == 3

    def test_the_timestamp_still_advances(self, db):
        """The update trigger does both jobs; neither may displace the other."""
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        before = db.connection.execute(
            "SELECT updated_at FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()[0]
        time.sleep(1.1)
        db.update_transaction(transaction_id, amount=Decimal("350"))
        after = db.connection.execute(
            "SELECT updated_at FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()[0]
        assert after > before


class TestEveryTableIsCovered:
    def test_every_audited_table_has_three_triggers(self, db):
        names = {
            row[0]
            for row in db.connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        for table in AUDITED_TABLES:
            for action in ("insert", "update", "delete"):
                assert f"audit_{table}_{action}" in names, f"{table} {action}"

    def test_accounts_are_recorded(self, db):
        account_id = db.add_account(Account(name="Banka"))
        db.update_account(account_id, name="BKT")
        db.delete_account(account_id)
        assert len(entries(db, "accounts")) == 3

    def test_categories_are_recorded(self, db):
        category_id = db.add_category(Category(name="Ushqim", kind=EXPENSE))
        db.update_category(category_id, "Ushqime")
        assert len(entries(db, "categories")) == 2

    def test_budgets_are_recorded(self, db):
        category_id = db.ensure_category("Ushqim", EXPENSE)
        db.set_budget(category_id, Decimal("200"))
        assert len(entries(db, "budgets")) == 1

    def test_recurring_rules_are_recorded(self, db):
        db.add_recurring_rule(
            RecurringRule(
                kind=EXPENSE, description="Qera", amount=Decimal("300"), starts_on="01-01-2026"
            )
        )
        assert len(entries(db, "recurring_rules")) == 1

    def test_a_raw_update_is_recorded_too(self, db):
        """The service layer writes raw SQL; the trigger covers it regardless."""
        account_id = db.add_account(Account(name="Banka"))
        with db.connection as conn:
            conn.execute("UPDATE accounts SET name = 'BKT' WHERE id = ?", (account_id,))
        updates = [e for e in entries(db, "accounts") if e.action == "update"]
        assert len(updates) == 1


class TestWhatIsRecorded:
    def test_a_create_has_no_before(self, db):
        db.add_transaction(Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026"))
        entry = entries(db, "transactions")[0]
        assert entry.before is None
        assert entry.after is not None

    def test_a_delete_has_no_after(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.delete_transaction(transaction_id)
        entry = [e for e in entries(db, "transactions") if e.action == "delete"][0]
        assert entry.before is not None
        assert entry.after is None

    def test_an_update_has_both_sides(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"))
        entry = [e for e in entries(db, "transactions") if e.action == "update"][0]
        assert entry.before["amount_cents"] == 30000
        assert entry.after["amount_cents"] == 35000

    def test_changes_lists_only_what_differed(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"))
        entry = [e for e in entries(db, "transactions") if e.action == "update"][0]
        fields = [field for field, _, _ in entry.changes()]
        assert fields == ["amount_cents"]

    def test_changes_reports_several_fields(self, db):
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"), description="Qera e gushtit")
        entry = [e for e in entries(db, "transactions") if e.action == "update"][0]
        fields = {field for field, _, _ in entry.changes()}
        assert fields == {"amount_cents", "description"}

    def test_timestamps_are_not_part_of_the_record(self, db):
        """Otherwise every entry would show a timestamp change beside the real one."""
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.update_transaction(transaction_id, amount=Decimal("350"))
        entry = [e for e in entries(db, "transactions") if e.action == "update"][0]
        assert "updated_at" not in entry.after
        assert "created_at" not in entry.after

    def test_the_entry_is_timestamped(self, db):
        db.add_transaction(Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026"))
        assert entries(db, "transactions")[0].at

    def test_the_record_survives_the_row_being_deleted(self, db):
        """A deleted transaction still has a history."""
        transaction_id = db.add_transaction(
            Transaction(EXPENSE, "Qera", Decimal("300"), "01-08-2026")
        )
        db.delete_transaction(transaction_id)
        assert db.transaction(transaction_id) is None
        assert len(entries(db, "transactions", transaction_id)) == 2


class TestQuerying:
    def test_newest_first(self, db):
        first = db.add_transaction(Transaction(EXPENSE, "A", Decimal("1"), "01-08-2026"))
        db.add_transaction(Transaction(EXPENSE, "B", Decimal("1"), "01-08-2026"))
        db.update_transaction(first, amount=Decimal("2"))
        assert entries(db, "transactions")[0].action == "update"

    def test_filtering_to_one_row(self, db):
        first = db.add_transaction(Transaction(EXPENSE, "A", Decimal("1"), "01-08-2026"))
        second = db.add_transaction(Transaction(EXPENSE, "B", Decimal("1"), "01-08-2026"))
        db.update_transaction(first, amount=Decimal("2"))
        assert len(entries(db, "transactions", first)) == 2
        assert len(entries(db, "transactions", second)) == 1

    def test_the_limit_is_respected(self, db):
        for index in range(10):
            db.add_transaction(Transaction(EXPENSE, f"T{index}", Decimal("1"), "01-08-2026"))
        assert len(db.audit_entries(limit=4)) == 4

    def test_count(self, db):
        db.add_transaction(Transaction(EXPENSE, "A", Decimal("1"), "01-08-2026"))
        assert db.audit_count() == 1

    def test_an_empty_log(self, db):
        assert db.audit_entries() == []
        assert db.audit_count() == 0


class TestMigrationFromVersionFour:
    """The path a database on 3.2.0 actually takes."""

    @staticmethod
    def build_v4(path):
        """A database as 3.2.0 left it: tables, indexes and the touch triggers."""
        from .conftest import schema_before_users

        connection = sqlite3.connect(path)
        connection.executescript(schema_before_users())
        for table in AUDITED_TABLES:
            connection.executescript(f"""
CREATE TRIGGER touch_{table} AFTER UPDATE ON {table} FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE {table} SET updated_at = datetime('now') WHERE id = NEW.id;
END;
""")
        connection.execute("PRAGMA user_version = 4")
        connection.execute(
            "INSERT INTO categories (name,name_key,kind) VALUES ('Ushqim','ushqim','Shpenzime')"
        )
        connection.execute(
            "INSERT INTO transactions "
            "(kind,description,amount_cents,occurred_on,category_id) "
            "VALUES ('Shpenzime','Ushqime',4550,'2026-08-03',1)"
        )
        connection.commit()
        connection.close()

    def test_the_touch_triggers_are_dropped(self, tmp_path):
        """Left in place they would record two entries for every edit."""
        path = str(tmp_path / "finance.db")
        self.build_v4(path)

        db = Database(path)
        names = {
            row[0]
            for row in db.connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        assert not [name for name in names if name.startswith("touch_")]
        assert len(names) == len(AUDITED_TABLES) * 3
        db.close()

    def test_the_data_survives(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v4(path)

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        rows = db.transactions()
        assert len(rows) == 1
        assert rows[0].amount == Decimal("45.50")
        assert rows[0].category == "Ushqim"
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        db.close()

    def test_editing_a_pre_existing_row_records_one_entry(self, tmp_path):
        """The case the dropped triggers would have doubled."""
        path = str(tmp_path / "finance.db")
        self.build_v4(path)

        db = Database(path)
        db.update_transaction(1, amount=Decimal("50.00"))
        updates = [e for e in entries(db, "transactions") if e.action == "update"]
        assert len(updates) == 1
        db.close()

    def test_the_timestamp_still_advances_after_migrating(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v4(path)

        db = Database(path)
        before = db.connection.execute(
            "SELECT updated_at FROM transactions WHERE id = 1"
        ).fetchone()[0]
        time.sleep(1.1)
        db.update_transaction(1, amount=Decimal("50.00"))
        after = db.connection.execute(
            "SELECT updated_at FROM transactions WHERE id = 1"
        ).fetchone()[0]
        assert after > before
        db.close()

    def test_history_before_the_upgrade_is_simply_absent(self, tmp_path):
        """Nothing is invented for changes made before the log existed."""
        path = str(tmp_path / "finance.db")
        self.build_v4(path)

        db = Database(path)
        assert db.audit_count() == 0
        db.close()


def test_the_trigger_script_covers_every_audited_table():
    script = all_audit_triggers()
    for table in AUDITED_TABLES:
        assert f"audit_{table}_insert" in script
        assert f"audit_{table}_update" in script
        assert f"audit_{table}_delete" in script


class TestHistoryIsReadable:
    """The log stores a row as the database holds it; nobody reads it that way."""

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_column_names_are_translated(self):
        from personal_finance import i18n
        from personal_finance.display import field_label

        assert field_label("occurred_on") == "Data"
        assert field_label("amount_cents") == "Shuma"
        assert field_label("category_id") == "Kategoria"
        i18n.set_language("en")
        assert field_label("occurred_on") == "Date"
        i18n.set_language("sq")

    def test_an_unmapped_column_falls_back_to_its_own_name(self):
        from personal_finance.display import field_label

        assert field_label("something_new") == "something_new"

    def test_every_audited_column_has_a_label(self):
        """A new column must not appear in the history as a raw name."""
        from personal_finance.display import _FIELD_LABELS

        for columns in AUDITED_TABLES.values():
            for column in columns:
                assert column in _FIELD_LABELS, column

    def test_cents_are_shown_as_euros(self):
        from personal_finance.display import audit_value

        assert audit_value("amount_cents", 30000) == "€300.00"

    def test_dates_are_shown_in_display_form(self):
        from personal_finance.display import audit_value

        assert audit_value("occurred_on", "2026-08-05") == "05-08-2026"
        assert audit_value("starts_on", "2026-01-01") == "01-01-2026"

    def test_references_are_shown_as_names(self):
        from personal_finance.display import audit_value

        names = {"accounts": {1: "Banka"}, "categories": {2: "Ushqim"}}
        assert audit_value("account_id", 1, names) == "Banka"
        assert audit_value("category_id", 2, names) == "Ushqim"

    def test_a_deleted_reference_falls_back_to_its_id(self):
        """There is no name left to show once the row is gone."""
        from personal_finance.display import audit_value

        assert audit_value("account_id", 99, {"accounts": {}}) == "#99"

    def test_absence_is_a_dash(self):
        from personal_finance.display import audit_value

        assert audit_value("category_id", None) == "-"

    def test_the_kind_is_translated(self):
        from personal_finance import i18n
        from personal_finance.display import audit_value

        assert audit_value("kind", "Shpenzime") == "Shpenzime"
        i18n.set_language("en")
        assert audit_value("kind", "Shpenzime") == "Expenses"
        i18n.set_language("sq")

    def test_reference_names_covers_every_referenced_table(self, app):
        names = app.reference_names()
        assert set(names) == {"categories", "accounts", "subcategories"}

    def test_the_printed_history_uses_names_not_ids(self, app, capsys):
        from personal_finance.display import print_history

        bank = app.add_account("Banka", "Banke", Decimal("0"))
        cash = app.add_account("Kesh", "Kesh", Decimal("0"))
        transaction = app.add_transaction(
            EXPENSE, "Qera", Decimal("300"), "01-08-2026", "Qera", None, bank
        )
        app.update_transaction(transaction.id, account_id=cash)
        capsys.readouterr()

        print_history(app.transaction_history(transaction.id), names=app.reference_names())
        output = capsys.readouterr().out
        assert "Banka  ->  Kesh" in output
        assert "account_id" not in output
        assert "occurred_on" not in output
