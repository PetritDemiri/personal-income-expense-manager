"""Tests specific to the SQLite backend.

The rollback tests are the point of the whole migration: with two CSV files, a
crash between the two writes left the generated transactions on disk while the
rules still believed nothing had been generated, so the next run created them
all again.
"""

import datetime
import sqlite3
from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.app import FinanceApp
from personal_finance.cli import main
from personal_finance.config import EXPENSE, INCOME
from personal_finance.sqlite_storage import (
    MIGRATIONS,
    SCHEMA_VERSION,
    SqliteStorage,
    from_cents,
    from_iso,
    to_cents,
    to_iso,
)
from personal_finance.storage import CsvStorage

from .conftest import make_budget, make_rule, make_transaction


class TestConversion:
    @pytest.mark.parametrize(
        "euros,cents",
        [
            ("0.00", 0),
            ("0.01", 1),
            ("1.00", 100),
            ("2.00", 200),
            ("200.00", 20000),
            ("185.40", 18540),
            ("1234567.89", 123456789),
        ],
    )
    def test_to_cents(self, euros, cents):
        assert to_cents(Decimal(euros)) == cents

    def test_round_trip_is_exact(self):
        for value in ("0.01", "0.10", "0.20", "185.40", "999999.99"):
            assert from_cents(to_cents(Decimal(value))) == Decimal(value)

    def test_no_floating_point_drift_through_the_database(self):
        total = from_cents(to_cents(Decimal("0.10"))) + from_cents(to_cents(Decimal("0.20")))
        assert total == Decimal("0.30")

    def test_sub_cent_amounts_are_quantised_not_truncated(self):
        # The CSV backend has always rounded to two places on write.
        assert to_cents(Decimal("1.005")) == 100 or to_cents(Decimal("1.005")) == 101
        assert to_cents(Decimal("1.999")) == 200

    def test_dates_are_stored_iso_so_they_sort(self):
        assert to_iso("05-08-2026") == "2026-08-05"
        assert to_iso("15-12-2026") == "2026-12-15"
        assert sorted([to_iso("15-12-2026"), to_iso("05-08-2026")])[0] == "2026-08-05"

    def test_iso_round_trip(self):
        assert from_iso(to_iso("05-08-2026")) == "05-08-2026"

    def test_bad_dates_convert_to_none_and_empty(self):
        assert to_iso("garbage") is None
        assert from_iso("") == ""
        assert from_iso(None) == ""


class TestSchema:
    def test_new_database_is_at_the_current_version(self, sqlite_storage):
        assert sqlite_storage.schema_version() == SCHEMA_VERSION

    def test_migrations_cover_every_version_up_to_current(self):
        assert sorted(MIGRATIONS) == list(range(1, SCHEMA_VERSION + 1))

    def test_reopening_does_not_re_run_migrations(self, tmp_path):
        path = str(tmp_path / "finance.db")
        first = SqliteStorage(database_file=path)
        first.save_transactions([make_transaction()])
        first.close()

        second = SqliteStorage(database_file=path)
        assert second.schema_version() == SCHEMA_VERSION
        assert len(second.load_transactions().records) == 1
        second.close()

    def test_created_flag_is_true_only_the_first_time(self, tmp_path):
        path = str(tmp_path / "finance.db")
        first = SqliteStorage(database_file=path)
        assert first.created
        first.close()

        second = SqliteStorage(database_file=path)
        assert not second.created
        second.close()

    def test_money_column_is_an_integer(self, sqlite_storage):
        columns = {
            row[1]: row[2]
            for row in sqlite_storage.connect().execute("PRAGMA table_info(transactions)")
        }
        # REAL would be a float, which is exactly what Decimal exists to avoid.
        assert columns["shuma_cents"] == "INTEGER"

    def test_indexes_exist(self, sqlite_storage):
        names = {
            row[0]
            for row in sqlite_storage.connect().execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "idx_transactions_data" in names

    def test_is_empty(self, sqlite_storage):
        assert sqlite_storage.is_empty()
        sqlite_storage.save_transactions([make_transaction()])
        assert not sqlite_storage.is_empty()


class TestDatabaseQueries:
    """The queries CSV could not express cheaply - the reason for migrating."""

    def test_dates_sort_chronologically_in_sql(self, sqlite_storage):
        sqlite_storage.save_transactions(
            [
                make_transaction(date="15-12-2026", description="December"),
                make_transaction(date="05-08-2026", description="August"),
                make_transaction(date="01-01-2027", description="January"),
            ]
        )
        rows = sqlite_storage.connect().execute("SELECT pershkrimi FROM transactions ORDER BY data")
        assert [r[0] for r in rows] == ["August", "December", "January"]

    def test_sql_can_aggregate_amounts(self, sqlite_storage):
        sqlite_storage.save_transactions(
            [
                make_transaction(EXPENSE, amount="10.50", category="Ushqim"),
                make_transaction(EXPENSE, amount="20.25", category="Ushqim"),
                make_transaction(EXPENSE, amount="99.00", category="Qera"),
            ]
        )
        total = (
            sqlite_storage.connect()
            .execute("SELECT SUM(shuma_cents) FROM transactions WHERE kategoria = 'Ushqim'")
            .fetchone()[0]
        )
        assert from_cents(total) == Decimal("30.75")

    def test_range_query_on_dates(self, sqlite_storage):
        sqlite_storage.save_transactions(
            [
                make_transaction(date="01-06-2026"),
                make_transaction(date="15-06-2026"),
                make_transaction(date="01-08-2026"),
            ]
        )
        count = (
            sqlite_storage.connect()
            .execute(
                "SELECT COUNT(*) FROM transactions WHERE data BETWEEN ? AND ?",
                ("2026-06-01", "2026-06-30"),
            )
            .fetchone()[0]
        )
        assert count == 2


class TestAtomicRecurringRun:
    """The bug the migration exists to fix."""

    def test_crash_between_the_two_writes_rolls_everything_back(self, tmp_path, monkeypatch):
        path = str(tmp_path / "finance.db")
        store = SqliteStorage(database_file=path)
        app = FinanceApp(storage=store, quiet=True)
        app.load()
        app.recurring_rules.append(make_rule(start="01-06-2026"))
        app.save_recurring()
        store.close()

        # Fail after the transactions are written, before the rules are.
        def boom(conn, rules):
            raise KeyboardInterrupt()

        monkeypatch.setattr(SqliteStorage, "_write_recurring", staticmethod(boom))

        store = SqliteStorage(database_file=path)
        app = FinanceApp(storage=store, quiet=True)
        app.load()
        with pytest.raises(KeyboardInterrupt):
            app.process_recurring(as_of=datetime.date(2026, 8, 7))
        store.close()
        monkeypatch.undo()

        # Nothing should have survived the failed save.
        store = SqliteStorage(database_file=path)
        app = FinanceApp(storage=store, quiet=True)
        app.load()
        assert app.transactions == []
        store.close()

    def test_no_duplicates_after_a_crashed_run(self, tmp_path, monkeypatch):
        path = str(tmp_path / "finance.db")
        store = SqliteStorage(database_file=path)
        app = FinanceApp(storage=store, quiet=True)
        app.load()
        app.recurring_rules.append(make_rule(start="01-06-2026"))
        app.save_recurring()
        store.close()

        def boom(conn, rules):
            raise KeyboardInterrupt()

        monkeypatch.setattr(SqliteStorage, "_write_recurring", staticmethod(boom))
        store = SqliteStorage(database_file=path)
        app = FinanceApp(storage=store, quiet=True)
        app.load()
        with pytest.raises(KeyboardInterrupt):
            app.process_recurring(as_of=datetime.date(2026, 8, 7))
        store.close()
        monkeypatch.undo()

        store = SqliteStorage(database_file=path)
        app = FinanceApp(storage=store, quiet=True)
        app.load()
        app.process_recurring(as_of=datetime.date(2026, 8, 7))
        dates = [t.data for t in app.transactions]
        assert len(dates) == len(set(dates)) == 3
        store.close()

    def test_successful_run_writes_both_tables(self, sqlite_storage):
        app = FinanceApp(storage=sqlite_storage, quiet=True)
        app.load()
        app.recurring_rules.append(make_rule(start="01-06-2026"))
        app.save_recurring()

        generated = app.process_recurring(as_of=datetime.date(2026, 8, 7))
        assert len(generated) == 3

        reloaded = FinanceApp(storage=sqlite_storage, quiet=True)
        reloaded.load()
        assert len(reloaded.transactions) == 3
        assert reloaded.recurring_rules[0].data_e_fundit == "01-08-2026"

    def test_still_idempotent_across_restarts(self, sqlite_storage):
        app = FinanceApp(storage=sqlite_storage, quiet=True)
        app.load()
        app.recurring_rules.append(make_rule(start="01-06-2026"))
        app.save_recurring()
        app.process_recurring(as_of=datetime.date(2026, 8, 7))

        again = FinanceApp(storage=sqlite_storage, quiet=True)
        again.load()
        assert again.process_recurring(as_of=datetime.date(2026, 8, 7)) == []


class TestImportFromCsv:
    def test_imports_all_three_kinds(self, tmp_path):
        csv_store = CsvStorage(
            transactions_file=str(tmp_path / "transactions.csv"),
            recurring_file=str(tmp_path / "recurring.csv"),
            budgets_file=str(tmp_path / "budgets.csv"),
        )
        csv_store.save_transactions(
            [make_transaction(INCOME, "Paga", "1200.00", "01-06-2026", "Paga")]
        )
        csv_store.save_recurring([make_rule()])
        csv_store.save_budgets([make_budget()])

        store = SqliteStorage(database_file=str(tmp_path / "finance.db"))
        count = store.import_from(csv_store)
        assert count == 3
        assert len(store.load_transactions().records) == 1
        assert len(store.load_recurring().records) == 1
        assert len(store.load_budgets().records) == 1
        store.close()

    def test_amounts_survive_the_import_exactly(self, tmp_path):
        csv_store = CsvStorage(
            transactions_file=str(tmp_path / "transactions.csv"),
            recurring_file=str(tmp_path / "recurring.csv"),
            budgets_file=str(tmp_path / "budgets.csv"),
        )
        csv_store.save_transactions(
            [make_transaction(EXPENSE, "Qera", "185.40", "01-06-2026", "Qera")]
        )

        store = SqliteStorage(database_file=str(tmp_path / "finance.db"))
        store.import_from(csv_store)
        assert store.load_transactions().records[0].shuma == Decimal("185.40")
        store.close()

    def test_subcategories_survive_the_import(self, tmp_path):
        csv_store = CsvStorage(
            transactions_file=str(tmp_path / "transactions.csv"),
            recurring_file=str(tmp_path / "recurring.csv"),
            budgets_file=str(tmp_path / "budgets.csv"),
        )
        transaction = make_transaction(EXPENSE, "Buke", "1.20", "01-06-2026", "Ushqim")
        transaction.nenkategoria = "Dyqan"
        csv_store.save_transactions([transaction])

        store = SqliteStorage(database_file=str(tmp_path / "finance.db"))
        store.import_from(csv_store)
        assert store.load_transactions().records[0].nenkategoria == "Dyqan"
        store.close()


class TestCliBackendSelection:
    @pytest.fixture(autouse=True)
    def isolated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        i18n.set_language("sq")
        colors.configure(force_off=True)
        return tmp_path

    def test_database_is_the_default(self, isolated, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Qera",
                "--shuma",
                "300",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Qera",
            ]
        )
        capsys.readouterr()
        assert (isolated / "finance.db").exists()
        assert not (isolated / "transactions.csv").exists()

    def test_csv_flag_uses_files_instead(self, isolated, capsys):
        main(
            [
                "--csv",
                "--shto-shpenzime",
                "--pershkrimi",
                "Qera",
                "--shuma",
                "300",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Qera",
            ]
        )
        capsys.readouterr()
        assert (isolated / "transactions.csv").exists()
        assert not (isolated / "finance.db").exists()

    def test_existing_csv_data_is_imported_on_first_run(self, isolated, capsys):
        (isolated / "transactions.csv").write_text(
            "lloji,pershkrimi,shuma,data,kategoria,nenkategoria\n"
            f"{INCOME},Paga,1200.00,01-06-2026,Paga,\n"
            f"{EXPENSE},Qera,300.00,02-06-2026,Qera,\n",
            encoding="utf-8",
        )

        main(["--gjendja"])
        output = capsys.readouterr().out
        assert "transferuan" in output
        assert "1200.00" in output
        assert "900.00" in output  # the balance came across correctly

    def test_import_leaves_the_csv_files_alone(self, isolated, capsys):
        original = (
            "lloji,pershkrimi,shuma,data,kategoria,nenkategoria\n"
            f"{INCOME},Paga,1200.00,01-06-2026,Paga,\n"
        )
        (isolated / "transactions.csv").write_text(original, encoding="utf-8")

        main(["--gjendja"])
        capsys.readouterr()
        assert (isolated / "transactions.csv").read_text(encoding="utf-8") == original

    def test_import_runs_only_once(self, isolated, capsys):
        (isolated / "transactions.csv").write_text(
            "lloji,pershkrimi,shuma,data,kategoria,nenkategoria\n"
            f"{INCOME},Paga,1200.00,01-06-2026,Paga,\n",
            encoding="utf-8",
        )

        main(["--gjendja"])
        capsys.readouterr()
        main(["--gjendja"])
        second = capsys.readouterr().out
        assert "transferuan" not in second
        assert "Numri i Transaksioneve: 1" in second

    def test_no_import_message_when_there_is_nothing_to_import(self, isolated, capsys):
        main(["--gjendja"])
        assert "transferuan" not in capsys.readouterr().out

    def test_custom_database_path(self, isolated, capsys):
        target = isolated / "custom" / "mydata.db"
        main(["--baza", str(target), "--gjendja"])
        capsys.readouterr()
        assert target.exists()

    def test_the_two_backends_report_the_same_balance(self, isolated, capsys):
        # Database first: if CSV ran first, the database would auto-import it
        # and then add its own rows on top.
        for flags in ([], ["--csv"]):
            main(
                flags
                + [
                    "--shto-te-ardhura",
                    "--pershkrimi",
                    "Paga",
                    "--shuma",
                    "1000",
                    "--data",
                    "01-06-2026",
                    "--kategoria",
                    "Paga",
                ]
            )
            main(
                flags
                + [
                    "--shto-shpenzime",
                    "--pershkrimi",
                    "Qera",
                    "--shuma",
                    "300.55",
                    "--data",
                    "02-06-2026",
                    "--kategoria",
                    "Qera",
                ]
            )
        capsys.readouterr()

        main(["--csv", "--gjendja"])
        csv_out = capsys.readouterr().out
        main(["--gjendja"])
        db_out = capsys.readouterr().out

        for line in ("Te Ardhurat Totale", "Shpenzimet Totale", "Gjendja Aktuale"):
            csv_line = next(x for x in csv_out.split("\n") if line in x)
            db_line = next(x for x in db_out.split("\n") if line in x)
            assert csv_line == db_line


def test_database_survives_an_interrupted_process(tmp_path):
    """WAL plus full synchronous means a killed process leaves a valid file."""
    path = str(tmp_path / "finance.db")
    store = SqliteStorage(database_file=path)
    store.save_transactions([make_transaction(EXPENSE, "Qera", "300.00")])
    # Deliberately do not close - simulate the process disappearing.
    del store

    reopened = sqlite3.connect(path)
    assert reopened.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()

    store = SqliteStorage(database_file=path)
    assert len(store.load_transactions().records) == 1
    store.close()
