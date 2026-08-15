"""Tests for the storage layer.

The atomicity tests matter most: the previous version opened the data file in
'w' mode, so an interrupted save truncated it and lost every transaction.
"""

import csv
import os
from decimal import Decimal

import pytest

from personal_finance.config import EXPENSE, INCOME
from personal_finance.models import Transaction
from personal_finance.storage import atomic_write_csv

from .conftest import make_budget, make_rule, make_transaction


class TestRoundTrip:
    def test_transactions_survive_save_and_load(self, storage):
        original = [
            make_transaction(INCOME, "Paga", "1000.00", "01-06-2026", "Paga"),
            make_transaction(EXPENSE, "Qera", "300.00", "02-06-2026", "Qera"),
        ]
        storage.save_transactions(original)
        assert list(storage.load_transactions()) == original

    def test_recurring_rules_survive_save_and_load(self, storage):
        original = [make_rule()]
        storage.save_recurring(original)
        assert list(storage.load_recurring()) == original

    def test_budgets_survive_save_and_load(self, storage):
        original = [make_budget()]
        storage.save_budgets(original)
        assert list(storage.load_budgets()) == original

    def test_missing_files_load_as_empty(self, storage):
        assert list(storage.load_transactions()) == []
        assert list(storage.load_recurring()) == []
        assert list(storage.load_budgets()) == []

    def test_unicode_survives_the_round_trip(self, storage):
        original = [make_transaction(EXPENSE, "Qera e banesës", "300.00")]
        storage.save_transactions(original)
        assert list(storage.load_transactions())[0].pershkrimi == "Qera e banesës"


class TestCorruptedData:
    def test_one_bad_row_does_not_lose_the_others(self, storage):
        with open(storage.transactions_file, "w", newline="", encoding="utf-8") as f:
            f.write("lloji,pershkrimi,shuma,data,kategoria\n")
            f.write(f"{INCOME},Good one,100,01-06-2026,Paga\n")
            f.write(f"{EXPENSE},Bad amount,not-a-number,02-06-2026,Ushqim\n")
            f.write(f"{EXPENSE},Good two,50,03-06-2026,Ushqim\n")

        result = storage.load_transactions()
        assert len(result.records) == 2
        assert result.skipped == 1
        assert [x.pershkrimi for x in result.records] == ["Good one", "Good two"]

    def test_old_four_column_file_still_loads(self, storage):
        # Written before the kategoria column existed.
        with open(storage.transactions_file, "w", newline="", encoding="utf-8") as f:
            f.write("lloji,pershkrimi,shuma,data\n")
            f.write(f"{INCOME},Paga,1000,01-06-2026\n")

        records = list(storage.load_transactions())
        assert len(records) == 1
        assert records[0].kategoria == "Pa kategori"

    def test_file_with_english_types_still_loads(self, storage):
        with open(storage.transactions_file, "w", newline="", encoding="utf-8") as f:
            f.write("lloji,pershkrimi,shuma,data\n")
            f.write("income,Paga,1000,01-06-2026\n")
            f.write("expense,Qera,300,02-06-2026\n")

        records = list(storage.load_transactions())
        assert [x.lloji for x in records] == [INCOME, EXPENSE]

    def test_recurring_rule_with_unknown_frequency_is_skipped(self, storage):
        with open(storage.recurring_file, "w", newline="", encoding="utf-8") as f:
            f.write("lloji,pershkrimi,shuma,kategoria,frekuenca,data_fillimit,data_e_fundit\n")
            f.write(f"{EXPENSE},Good,50,Fatura,mujore,01-01-2026,\n")
            f.write(f"{EXPENSE},Bad,50,Fatura,cdo-hene,01-01-2026,\n")

        from personal_finance.recurring import FREQUENCIES

        result = storage.load_recurring(valid_frequencies=FREQUENCIES)
        assert len(result.records) == 1
        assert result.skipped == 1


class TestAtomicWrites:
    def test_no_temp_files_left_behind(self, storage, tmp_path):
        storage.save_transactions([make_transaction()])
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
        assert leftovers == []

    def test_failed_write_leaves_original_intact(self, storage, monkeypatch):
        """A crash mid-save must not destroy existing data."""
        original = [make_transaction(INCOME, "Important", "999.00")]
        storage.save_transactions(original)

        # Simulate a failure at the moment of the final swap.
        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            storage.save_transactions([make_transaction(EXPENSE, "New", "1.00")])

        monkeypatch.undo()
        # The original file must still hold the original data.
        records = list(storage.load_transactions())
        assert len(records) == 1
        assert records[0].pershkrimi == "Important"
        assert records[0].shuma == Decimal("999.00")

    def test_failed_write_cleans_up_its_temp_file(self, storage, tmp_path, monkeypatch):
        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            storage.save_transactions([make_transaction()])
        monkeypatch.undo()

        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
        assert leftovers == []

    def test_interrupt_during_write_leaves_original_intact(self, storage, monkeypatch):
        """Ctrl+C is a BaseException, not an Exception - it must still clean up."""
        storage.save_transactions([make_transaction(INCOME, "Important", "999.00")])

        def interrupt(src, dst):
            raise KeyboardInterrupt()

        monkeypatch.setattr(os, "replace", interrupt)
        with pytest.raises(KeyboardInterrupt):
            storage.save_transactions([make_transaction(EXPENSE, "New", "1.00")])
        monkeypatch.undo()

        records = list(storage.load_transactions())
        assert records[0].pershkrimi == "Important"

    def test_creates_missing_directory(self, tmp_path):
        nested = tmp_path / "a" / "b" / "transactions.csv"
        atomic_write_csv(str(nested), ["x"], [{"x": "1"}])
        assert nested.exists()

    def test_written_file_has_a_header(self, storage):
        storage.save_transactions([make_transaction()])
        with open(storage.transactions_file, newline="", encoding="utf-8") as f:
            assert next(csv.reader(f)) == Transaction.FIELDNAMES

    def test_saving_empty_list_writes_header_only(self, storage):
        storage.save_transactions([])
        assert list(storage.load_transactions()) == []
