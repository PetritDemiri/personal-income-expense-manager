"""Ruajtja ne SQLite / SQLite storage backend.

Implements the same Storage interface as the CSV backend, so nothing above
this module changes when the backend does.

Three decisions worth knowing about, because they are what make the database
worth having rather than a CSV file with extra steps:

Money is stored as an INTEGER number of cents. SQLite's REAL is a float, and
storing money in a float would undo the whole reason this program uses Decimal.
Integer cents are exact, and they let SQL do the arithmetic later if wanted.

Dates are stored as ISO (yyyy-mm-dd), not in the dd-mm-yyyy form shown on
screen. A date column that does not sort chronologically cannot be indexed or
range-queried usefully, which is most of the point of moving off CSV. The
conversion happens here, at the boundary - the models and the interface keep
using dd-mm-yyyy exactly as before.

The schema carries a version in SQLite's user_version pragma, and migrations
run automatically on open. Adding a column later is then a numbered migration
step rather than a rewrite.
"""

import os
import sqlite3
from decimal import Decimal, InvalidOperation

from .config import CASH, DATABASE_FILE, DEFAULT_CATEGORY, data_path
from .dates import parse_date
from .models import Account, Budget, RecurringRule, Transaction
from .storage import LoadResult, Storage

# Bump this and add a matching entry to MIGRATIONS when the schema changes.
SCHEMA_VERSION = 2

CENTS = Decimal("0.01")


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def to_cents(amount):
    """Decimal euros to an integer number of cents.

    Amounts are quantised to two places, which is what the CSV backend has
    always done when writing, so nothing is lost that was not already lost.
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return int(amount.quantize(CENTS) * 100)


def from_cents(cents):
    """Integer cents back to a Decimal with two places."""
    return (Decimal(int(cents)) / 100).quantize(CENTS)


def to_iso(date_str):
    """dd-mm-yyyy to yyyy-mm-dd, or None if it cannot be parsed."""
    parsed = parse_date(date_str)
    return parsed.isoformat() if parsed else None


def from_iso(iso_str):
    """yyyy-mm-dd back to the dd-mm-yyyy form the rest of the program uses."""
    if not iso_str:
        return ""
    parts = str(iso_str).split("-")
    if len(parts) != 3:
        return ""
    year, month, day = parts
    return f"{day}-{month}-{year}"


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def _migration_1(conn):
    """Initial schema."""
    conn.executescript(
        """
        CREATE TABLE transactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lloji         TEXT    NOT NULL,
            pershkrimi    TEXT    NOT NULL,
            shuma_cents   INTEGER NOT NULL,
            data          TEXT    NOT NULL,
            kategoria     TEXT    NOT NULL DEFAULT 'Pa kategori',
            nenkategoria  TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE recurring (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            lloji          TEXT    NOT NULL,
            pershkrimi     TEXT    NOT NULL,
            shuma_cents    INTEGER NOT NULL,
            kategoria      TEXT    NOT NULL DEFAULT 'Pa kategori',
            nenkategoria   TEXT    NOT NULL DEFAULT '',
            frekuenca      TEXT    NOT NULL,
            data_fillimit  TEXT    NOT NULL,
            data_e_fundit  TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE budgets (
            kategoria    TEXT    PRIMARY KEY,
            shuma_cents  INTEGER NOT NULL
        );

        CREATE INDEX idx_transactions_data ON transactions(data);
        CREATE INDEX idx_transactions_lloji_kategoria
            ON transactions(lloji, kategoria);
        """
    )


def _migration_2(conn):
    """Accounts.

    The columns are added rather than the tables rebuilt, and every existing
    row simply gets an empty account - which reads as "unassigned" and is
    exactly right for transactions recorded before accounts existed.

    This is the first use of the migration machinery added with the database
    itself, and it is what that machinery was for: a schema change is a
    numbered step, not a rewrite.
    """
    conn.executescript(
        """
        CREATE TABLE accounts (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            emri                      TEXT    NOT NULL UNIQUE,
            lloji                     TEXT    NOT NULL DEFAULT 'Kesh',
            gjendja_fillestare_cents  INTEGER NOT NULL DEFAULT 0,
            rendi                     INTEGER NOT NULL DEFAULT 0
        );

        ALTER TABLE transactions ADD COLUMN llogaria      TEXT NOT NULL DEFAULT '';
        ALTER TABLE transactions ADD COLUMN llogaria_dest TEXT NOT NULL DEFAULT '';
        ALTER TABLE recurring    ADD COLUMN llogaria      TEXT NOT NULL DEFAULT '';

        CREATE INDEX idx_transactions_llogaria ON transactions(llogaria);
        """
    )


# Keyed by the version each step brings the database up to.
MIGRATIONS = {
    1: _migration_1,
    2: _migration_2,
}


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class SqliteStorage(Storage):
    """SQLite-backed storage.

    Writes go through real transactions, so a save that touches more than one
    table either lands completely or not at all.
    """

    def __init__(self, database_file=None):
        self.database_file = database_file or data_path(DATABASE_FILE)
        directory = os.path.dirname(os.path.abspath(self.database_file))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.created = not os.path.exists(self.database_file)
        self._conn = None
        self._migrate()

    # -- connection --------------------------------------------------------

    @property
    def location(self):
        return self.database_file

    def connect(self):
        """Open the connection, creating the file if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.database_file)
            self._conn.row_factory = sqlite3.Row
            # Durability: full synchronous plus a write-ahead log keeps the
            # database consistent through a crash or power loss.
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = FULL")
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    # -- schema ------------------------------------------------------------

    def schema_version(self):
        return self.connect().execute("PRAGMA user_version").fetchone()[0]

    def _migrate(self):
        """Bring the database up to SCHEMA_VERSION, one numbered step at a time."""
        conn = self.connect()
        current = self.schema_version()
        for version in sorted(MIGRATIONS):
            if version > current:
                with conn:
                    MIGRATIONS[version](conn)
                    # The pragma will not take a bound parameter.
                    conn.execute(f"PRAGMA user_version = {int(version)}")

    def is_empty(self):
        """True when there is nothing stored yet."""
        conn = self.connect()
        for table in ("transactions", "recurring", "budgets", "accounts"):
            if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return False
        return True

    # -- row conversion ----------------------------------------------------

    @staticmethod
    def _transaction_from_row(row):
        return Transaction(
            lloji=row["lloji"],
            pershkrimi=row["pershkrimi"],
            shuma=from_cents(row["shuma_cents"]),
            data=from_iso(row["data"]),
            kategoria=row["kategoria"] or DEFAULT_CATEGORY,
            nenkategoria=row["nenkategoria"] or "",
            llogaria=row["llogaria"] or "",
            llogaria_dest=row["llogaria_dest"] or "",
        )

    @staticmethod
    def _rule_from_row(row):
        return RecurringRule(
            lloji=row["lloji"],
            pershkrimi=row["pershkrimi"],
            shuma=from_cents(row["shuma_cents"]),
            kategoria=row["kategoria"] or DEFAULT_CATEGORY,
            nenkategoria=row["nenkategoria"] or "",
            llogaria=row["llogaria"] or "",
            frekuenca=row["frekuenca"],
            data_fillimit=from_iso(row["data_fillimit"]),
            data_e_fundit=from_iso(row["data_e_fundit"]),
        )

    # -- transactions ------------------------------------------------------

    def load_transactions(self):
        conn = self.connect()
        records = []
        skipped = 0
        # Ordered by date so listings are chronological before any sorting.
        rows = conn.execute("SELECT * FROM transactions ORDER BY data, id")
        for row in rows:
            try:
                records.append(self._transaction_from_row(row))
            except (InvalidOperation, TypeError, ValueError, KeyError):
                skipped += 1
        return LoadResult(records, skipped)

    @staticmethod
    def _write_transactions(conn, transactions):
        """Replace the transactions table. Caller owns the transaction."""
        conn.execute("DELETE FROM transactions")
        conn.executemany(
            "INSERT INTO transactions "
            "(lloji, pershkrimi, shuma_cents, data, kategoria, nenkategoria, "
            " llogaria, llogaria_dest) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    t.lloji,
                    t.pershkrimi,
                    to_cents(t.shuma),
                    to_iso(t.data),
                    t.kategoria,
                    t.nenkategoria,
                    t.llogaria,
                    t.llogaria_dest,
                )
                for t in transactions
            ],
        )

    def save_transactions(self, transactions):
        conn = self.connect()
        with conn:
            self._write_transactions(conn, transactions)

    # -- recurring ---------------------------------------------------------

    def load_recurring(self, valid_frequencies=None):
        conn = self.connect()
        records = []
        skipped = 0
        for row in conn.execute("SELECT * FROM recurring ORDER BY id"):
            try:
                rule = self._rule_from_row(row)
                if valid_frequencies is not None and rule.frekuenca not in valid_frequencies:
                    raise ValueError("frekuence e panjohur")
                if rule.start_date is None:
                    raise ValueError("date fillimi e pavlefshme")
                records.append(rule)
            except (InvalidOperation, TypeError, ValueError, KeyError):
                skipped += 1
        return LoadResult(records, skipped)

    @staticmethod
    def _write_recurring(conn, rules):
        """Replace the recurring table. Caller owns the transaction."""
        conn.execute("DELETE FROM recurring")
        conn.executemany(
            "INSERT INTO recurring "
            "(lloji, pershkrimi, shuma_cents, kategoria, nenkategoria, llogaria, "
            " frekuenca, data_fillimit, data_e_fundit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.lloji,
                    r.pershkrimi,
                    to_cents(r.shuma),
                    r.kategoria,
                    r.nenkategoria,
                    r.llogaria,
                    r.frekuenca,
                    to_iso(r.data_fillimit),
                    to_iso(r.data_e_fundit) or "",
                )
                for r in rules
            ],
        )

    def save_recurring(self, rules):
        conn = self.connect()
        with conn:
            self._write_recurring(conn, rules)

    def save_recurring_run(self, transactions, rules):
        """Save generated transactions and the updated rules in one transaction.

        This is the whole reason a database is worth having here. With two
        separate files, a crash between the two writes leaves the transactions
        on disk while the rules still believe nothing was generated - so the
        next run creates them all a second time. Here both tables commit
        together or neither does.
        """
        conn = self.connect()
        with conn:
            self._write_transactions(conn, transactions)
            self._write_recurring(conn, rules)

    # -- budgets -----------------------------------------------------------

    def load_budgets(self):
        conn = self.connect()
        records = []
        skipped = 0
        for row in conn.execute("SELECT * FROM budgets ORDER BY kategoria"):
            try:
                amount = from_cents(row["shuma_cents"])
                if amount <= 0:
                    raise ValueError("shume e pavlefshme")
                records.append(Budget(kategoria=row["kategoria"], shuma=amount))
            except (InvalidOperation, TypeError, ValueError, KeyError):
                skipped += 1
        return LoadResult(records, skipped)

    def save_budgets(self, budgets):
        conn = self.connect()
        with conn:
            conn.execute("DELETE FROM budgets")
            conn.executemany(
                "INSERT INTO budgets (kategoria, shuma_cents) VALUES (?, ?)",
                [(b.kategoria, to_cents(b.shuma)) for b in budgets],
            )

    # -- accounts ----------------------------------------------------------

    def load_accounts(self):
        conn = self.connect()
        records = []
        skipped = 0
        for row in conn.execute("SELECT * FROM accounts ORDER BY rendi, id"):
            try:
                records.append(
                    Account(
                        emri=row["emri"],
                        lloji=row["lloji"] or CASH,
                        gjendja_fillestare=from_cents(row["gjendja_fillestare_cents"]),
                    )
                )
            except (InvalidOperation, TypeError, ValueError, KeyError):
                skipped += 1
        return LoadResult(records, skipped)

    @staticmethod
    def _write_accounts(conn, accounts):
        conn.execute("DELETE FROM accounts")
        conn.executemany(
            "INSERT INTO accounts (emri, lloji, gjendja_fillestare_cents, rendi) "
            "VALUES (?, ?, ?, ?)",
            [
                (a.emri, a.lloji, to_cents(a.gjendja_fillestare), index)
                for index, a in enumerate(accounts)
            ],
        )

    def save_accounts(self, accounts):
        conn = self.connect()
        with conn:
            self._write_accounts(conn, accounts)

    def save_account_change(self, accounts, transactions, rules):
        """Save an account edit and everything it repoints, in one transaction.

        Renaming or deleting an account rewrites the account rows and every
        transaction and rule that referenced it. Half of that landing would
        leave transactions pointing at an account that no longer exists.
        """
        conn = self.connect()
        with conn:
            self._write_accounts(conn, accounts)
            self._write_transactions(conn, transactions)
            self._write_recurring(conn, rules)

    # -- import ------------------------------------------------------------

    def import_from(self, other):
        """Copy everything from another backend into this one, atomically.

        Used for the one-time move off CSV. Returns the number of records
        imported. Nothing is written if any part fails.
        """
        transactions = list(other.load_transactions().records)
        rules = list(other.load_recurring().records)
        budgets = list(other.load_budgets().records)
        accounts = list(other.load_accounts().records)

        conn = self.connect()
        with conn:
            self._write_transactions(conn, transactions)
            self._write_recurring(conn, rules)
            self._write_accounts(conn, accounts)
            conn.execute("DELETE FROM budgets")
            conn.executemany(
                "INSERT INTO budgets (kategoria, shuma_cents) VALUES (?, ?)",
                [(b.kategoria, to_cents(b.shuma)) for b in budgets],
            )
        return len(transactions) + len(rules) + len(budgets) + len(accounts)
