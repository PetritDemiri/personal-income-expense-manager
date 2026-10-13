"""Tests for where the program keeps what it writes for itself.

Everything lives in one folder inside Documents, each kind in a folder of its
own: the database in Te dhenat, the record of the first-launch tests in
Testet, the error log in Gabimet. Before 3.10.0 the database sat in whichever
folder the program was started from, which for a double-clicked program or a
shortcut depends on how it was opened - so the data could seem to vanish.
"""

import argparse
import os
import sqlite3
from decimal import Decimal

import pytest

from personal_finance import i18n, locations
from personal_finance.app import FinanceApp
from personal_finance.cli import database_location, main
from personal_finance.config import DATABASE_FILE, data_directory, data_path
from personal_finance.database import carry_over
from personal_finance.locations import (
    APP_FOLDER,
    DATA_FOLDER,
    ERRORS_FOLDER,
    TESTS_FOLDER,
    app_directory,
    app_subdirectory,
)
from personal_finance.schema import EXPENSE


@pytest.fixture
def documents(tmp_path, monkeypatch):
    """A Documents folder of the test's own, with the program's defaults restored."""
    folder = tmp_path / "Documents"
    folder.mkdir()
    monkeypatch.delenv("FINANCE_HOME", raising=False)
    monkeypatch.delenv("FINANCE_DATA_DIR", raising=False)
    monkeypatch.setattr(locations, "user_documents", lambda: str(folder))
    return folder


class TestTheProgramsOwnFolder:
    def test_it_is_called_financat_and_sits_in_documents(self, documents):
        assert app_directory() == str(documents / "Financat")

    def test_each_kind_of_file_has_a_folder_of_its_own(self, documents):
        folders = {app_subdirectory(name) for name in (DATA_FOLDER, TESTS_FOLDER, ERRORS_FOLDER)}
        assert len(folders) == 3
        for folder in folders:
            assert os.path.dirname(folder) == str(documents / APP_FOLDER)

    def test_the_folder_names(self):
        assert (APP_FOLDER, DATA_FOLDER, TESTS_FOLDER, ERRORS_FOLDER) == (
            "Financat",
            "Te dhenat",
            "Testet",
            "Gabimet",
        )

    def test_the_names_do_not_follow_the_interface_language(self, documents):
        """A folder that changed name with the language would leave the data
        behind whenever the language did."""
        i18n.set_language("en")
        try:
            assert data_directory().endswith(os.path.join("Financat", "Te dhenat"))
        finally:
            i18n.set_language("sq")

    def test_finance_home_moves_all_of_it(self, documents, tmp_path, monkeypatch):
        elsewhere = tmp_path / "elsewhere"
        monkeypatch.setenv("FINANCE_HOME", str(elsewhere))
        assert app_directory() == str(elsewhere)
        assert data_directory() == str(elsewhere / DATA_FOLDER)

    def test_the_export_setting_does_not_move_it(self, documents, tmp_path, monkeypatch):
        """A setting meant for exports must never move someone's database."""
        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path / "exports"))
        assert data_directory() == str(documents / "Financat" / "Te dhenat")


class TestTheDatabaseLocation:
    def test_it_is_in_te_dhenat(self, documents):
        expected = documents / "Financat" / "Te dhenat" / DATABASE_FILE
        assert data_path(DATABASE_FILE) == str(expected)

    def test_finance_data_dir_still_overrides_it(self, documents, tmp_path, monkeypatch):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path / "mine"))
        assert data_path(DATABASE_FILE) == str(tmp_path / "mine" / DATABASE_FILE)

    def test_an_empty_override_is_ignored(self, documents, monkeypatch):
        monkeypatch.setenv("FINANCE_DATA_DIR", "")
        assert data_directory() == str(documents / "Financat" / "Te dhenat")

    def test_the_folder_is_created_when_the_database_is(self, documents):
        app = FinanceApp(path=data_path(DATABASE_FILE), quiet=True)
        app.close()
        assert (documents / "Financat" / "Te dhenat" / DATABASE_FILE).exists()


def make_database(path, description="Ushqime"):
    """A database with one transaction in it, as an older version left it."""
    app = FinanceApp(path=str(path), quiet=True)
    app.add_transaction(EXPENSE, description, Decimal("12.50"), "01-09-2026", "Ushqim")
    app.close()


def descriptions(path):
    app = FinanceApp(path=str(path), quiet=True)
    try:
        return [view.description for view in app.transactions()]
    finally:
        app.close()


def flags(**values):
    return argparse.Namespace(baza=values.get("baza"))


class TestCarryingOverAnOldDatabase:
    """The first run of 3.10.0 from a folder that holds an older database."""

    @pytest.fixture
    def started_from(self, documents, tmp_path, monkeypatch):
        folder = tmp_path / "Test Bench"
        folder.mkdir()
        make_database(folder / DATABASE_FILE)
        monkeypatch.chdir(folder)
        i18n.set_language("sq")
        return folder

    def new_place(self, documents):
        return documents / "Financat" / "Te dhenat" / DATABASE_FILE

    def test_it_is_copied_to_the_new_place(self, started_from, documents):
        path = database_location(flags())
        assert path == str(self.new_place(documents))
        assert descriptions(path) == ["Ushqime"]

    def test_the_original_is_left_exactly_as_it_was(self, started_from, documents):
        """Copied, never moved: if anything about the move is wrong, the data
        is still exactly where it was."""
        original = started_from / DATABASE_FILE
        before = original.read_bytes()
        database_location(flags())
        assert original.read_bytes() == before

    def test_it_says_what_happened(self, started_from, documents, capsys):
        database_location(flags())
        shown = capsys.readouterr().out
        assert "u kopjua ne vendin e saj te ri" in shown
        assert "nuk perdoret me" in shown
        assert str(self.new_place(documents)) in shown

    def test_it_happens_once(self, started_from, documents, capsys):
        database_location(flags())
        capsys.readouterr()
        assert database_location(flags()) == str(self.new_place(documents))
        assert capsys.readouterr().out == ""

    def test_a_database_already_in_the_new_place_is_used_as_it_is(
        self, started_from, documents, capsys
    ):
        new = self.new_place(documents)
        new.parent.mkdir(parents=True)
        make_database(new, description="E reja")
        assert database_location(flags()) == str(new)
        assert descriptions(new) == ["E reja"]
        assert capsys.readouterr().out == ""

    def test_not_when_the_data_folder_is_chosen(self, started_from, tmp_path, monkeypatch):
        chosen = tmp_path / "chosen"
        monkeypatch.setenv("FINANCE_DATA_DIR", str(chosen))
        assert database_location(flags()) == str(chosen / DATABASE_FILE)
        assert not (chosen / DATABASE_FILE).exists()

    def test_not_when_the_file_is_named(self, started_from, tmp_path):
        named = str(tmp_path / "other.db")
        assert database_location(flags(baza=named)) == named

    def test_a_copy_that_fails_uses_the_old_one_where_it_is(
        self, started_from, documents, monkeypatch, capsys
    ):
        def broken(_source, _target):
            raise OSError("disk full")

        monkeypatch.setattr("personal_finance.cli.carry_over", broken)
        path = database_location(flags())
        assert path == str(started_from / DATABASE_FILE)
        assert "nuk mund te kopjohej" in capsys.readouterr().out

    def test_the_program_carries_on_with_the_copied_data(self, started_from, documents, capsys):
        assert main(["--lista"]) == 0
        shown = capsys.readouterr().out
        assert "u kopjua" in shown
        assert "Ushqime" in shown


class TestCarryOver:
    def test_recent_changes_still_in_the_write_ahead_log_come_too(self, tmp_path):
        """A plain file copy would leave behind whatever is still in the WAL."""
        source = tmp_path / "old.db"
        make_database(source)
        writer = sqlite3.connect(source)
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("UPDATE transactions SET description = 'E fundit'")
        writer.commit()
        try:
            target = tmp_path / "new" / "finance.db"
            carry_over(str(source), str(target))
        finally:
            writer.close()
        assert descriptions(target) == ["E fundit"]

    def test_something_that_is_not_a_database_is_refused(self, tmp_path):
        source = tmp_path / "old.db"
        source.write_bytes(b"this is not a database" * 200)
        target = tmp_path / "new" / "finance.db"
        with pytest.raises(sqlite3.DatabaseError):
            carry_over(str(source), str(target))

    def test_nothing_half_written_is_left_behind(self, tmp_path):
        source = tmp_path / "old.db"
        source.write_bytes(b"this is not a database" * 200)
        target = tmp_path / "new" / "finance.db"
        with pytest.raises(sqlite3.DatabaseError):
            carry_over(str(source), str(target))
        assert not target.exists()
        assert not (tmp_path / "new" / "finance.db.part").exists()
