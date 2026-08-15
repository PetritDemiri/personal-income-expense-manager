"""Ruajtja e te dhenave / Storage layer.

Everything above this module talks to a Storage object and never touches a
file directly. Swapping CSV for SQLite later means writing one new class that
implements the same methods - no changes to the UI, the reports, or the CLI.

Writes are atomic: data is written to a temporary file in the same directory
and then moved over the original with os.replace(), which is atomic on both
POSIX and Windows. A crash, a full disk, or Ctrl+C during a save therefore
leaves the previous file intact instead of a half-written one.
"""

import csv
import os
import tempfile

from .config import (
    BUDGETS_FILE,
    RECURRING_FILE,
    TRANSACTIONS_FILE,
    data_path,
)
from .models import Budget, RecurringRule, Transaction


def atomic_write_csv(path, fieldnames, rows):
    """Write rows to a CSV file atomically.

    The temporary file is created in the same directory as the target so the
    final move stays on one filesystem, which is what makes it atomic.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=directory,
        prefix=".tmp-",
        suffix=".csv",
        delete=False,
    )
    temp_path = handle.name
    try:
        with handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            # Force the data to disk before the rename, so a power loss
            # cannot leave an empty file in place of the real one.
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        # Clean up the temporary file on any failure, including KeyboardInterrupt.
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def atomic_write_two_csvs(first, second):
    """Write two CSV files with the smallest possible window between them.

    Each argument is a (path, fieldnames, rows) tuple. Both temporary files are
    written and flushed to disk first, so the only thing left between the two
    renames is two consecutive syscalls with no I/O in between.

    This narrows the crash window; it does not close it. Only a backend with
    real transactions can do that, which is what SqliteStorage is for.
    """
    prepared = []
    try:
        for path, fieldnames, rows in (first, second):
            directory = os.path.dirname(os.path.abspath(path)) or "."
            os.makedirs(directory, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                newline="",
                encoding="utf-8",
                dir=directory,
                prefix=".tmp-",
                suffix=".csv",
                delete=False,
            )
            with handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            prepared.append((handle.name, path))

        for temp_path, path in prepared:
            os.replace(temp_path, path)
        prepared = []
    finally:
        for temp_path, _ in prepared:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


class Storage:
    """Interface every storage backend implements.

    Defined explicitly so an alternative backend (SQLite, an API client, an
    in-memory fake for tests) can be dropped in without the rest of the
    package knowing the difference.
    """

    def load_transactions(self):
        raise NotImplementedError

    def save_transactions(self, transactions):
        raise NotImplementedError

    def load_recurring(self, valid_frequencies=None):
        raise NotImplementedError

    def save_recurring(self, rules):
        raise NotImplementedError

    def save_recurring_run(self, transactions, rules):
        """Save generated transactions and the updated rules together.

        Backends that support real transactions make this atomic. Backends
        that do not should still make the gap between the two writes as small
        as they can - a crash in that gap regenerates the same occurrences on
        the next run.
        """
        raise NotImplementedError

    def load_budgets(self):
        raise NotImplementedError

    def save_budgets(self, budgets):
        raise NotImplementedError


class LoadResult:
    """What a load produced: the records, and how many rows were unusable."""

    def __init__(self, records, skipped=0):
        self.records = records
        self.skipped = skipped

    def __iter__(self):
        return iter(self.records)

    def __len__(self):
        return len(self.records)


class CsvStorage(Storage):
    """CSV-backed storage.

    Corrupted rows are skipped individually and counted, so one bad line never
    costs the rest of the file.
    """

    def __init__(self, transactions_file=None, recurring_file=None, budgets_file=None):
        self.transactions_file = transactions_file or data_path(TRANSACTIONS_FILE)
        self.recurring_file = recurring_file or data_path(RECURRING_FILE)
        self.budgets_file = budgets_file or data_path(BUDGETS_FILE)

    @property
    def location(self):
        return self.transactions_file

    # -- generic helpers ---------------------------------------------------

    @staticmethod
    def _read(path, build):
        """Read a CSV file into model objects, skipping unusable rows."""
        if not os.path.exists(path):
            return LoadResult([], 0)

        records = []
        skipped = 0
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    records.append(build(row))
                except (ValueError, TypeError, KeyError, AttributeError):
                    skipped += 1
        return LoadResult(records, skipped)

    @staticmethod
    def _write(path, fieldnames, records):
        atomic_write_csv(path, fieldnames, [r.to_row() for r in records])

    # -- transactions ------------------------------------------------------

    def load_transactions(self):
        return self._read(self.transactions_file, Transaction.from_row)

    def save_transactions(self, transactions):
        self._write(self.transactions_file, Transaction.FIELDNAMES, transactions)

    # -- recurring rules ---------------------------------------------------

    def load_recurring(self, valid_frequencies=None):
        return self._read(
            self.recurring_file,
            lambda row: RecurringRule.from_row(row, valid_frequencies),
        )

    def save_recurring(self, rules):
        self._write(self.recurring_file, RecurringRule.FIELDNAMES, rules)

    def save_recurring_run(self, transactions, rules):
        """Write both files back to back, with both already flushed to disk."""
        atomic_write_two_csvs(
            (
                self.transactions_file,
                Transaction.FIELDNAMES,
                [t.to_row() for t in transactions],
            ),
            (
                self.recurring_file,
                RecurringRule.FIELDNAMES,
                [r.to_row() for r in rules],
            ),
        )

    # -- budgets -----------------------------------------------------------

    def load_budgets(self):
        return self._read(self.budgets_file, Budget.from_row)

    def save_budgets(self, budgets):
        self._write(self.budgets_file, Budget.FIELDNAMES, budgets)
