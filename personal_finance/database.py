"""Baza e te dhenave / Database access.

One implementation, not an interface with several. The CSV backend is gone, and
with it the shape it imposed: every write used to replace an entire table
because that is all a text file can do.

What replaces it is row-level. Adding a transaction inserts one row. Changing
one changes one row. Filtering happens in SQL against indexes rather than in a
Python loop over everything held in memory.

Conversion lives here, at the boundary. Callers hand over and receive Decimal
amounts and dd-mm-yyyy dates; the database holds integer cents and ISO text.
Nothing above this module knows that, and nothing below it knows anything else.
"""

import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal

from .dates import parse_date
from .models import (
    Account,
    Budget,
    Category,
    RecurringRule,
    Subcategory,
    TransactionView,
    name_key,
)
from .schema import EXPENSE, SCHEMA_VERSION, create_schema, migrate

CENTS = Decimal("0.01")


# ---------------------------------------------------------------------------
# Conversion at the boundary
# ---------------------------------------------------------------------------


def to_cents(amount):
    """Decimal euros to an integer count of cents."""
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return int(amount.quantize(CENTS) * 100)


def from_cents(cents):
    """Integer cents back to a Decimal with two places."""
    return (Decimal(int(cents)) / 100).quantize(CENTS)


def to_iso(date_text):
    """dd-mm-yyyy to yyyy-mm-dd, or None if it cannot be read."""
    parsed = parse_date(date_text)
    return parsed.isoformat() if parsed else None


def from_iso(iso_text):
    """yyyy-mm-dd back to the dd-mm-yyyy the rest of the program uses."""
    if not iso_text:
        return ""
    parts = str(iso_text).split("-")
    if len(parts) != 3:
        return ""
    year, month, day = parts
    return f"{day}-{month}-{year}"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class Database:
    """A SQLite database holding one person's finances."""

    def __init__(self, path):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.created = not os.path.exists(path)
        self._connection = None
        self._ensure_schema()

    # -- connection --------------------------------------------------------

    @property
    def connection(self):
        if self._connection is None:
            self._connection = sqlite3.connect(self.path)
            self._connection.row_factory = sqlite3.Row
            # Foreign keys are off by default in SQLite and must be enabled on
            # every connection; without this the ON DELETE rules do nothing.
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
        return self._connection

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    @contextmanager
    def atomic(self):
        """Run several statements as one transaction.

        Anything that touches more than one table goes through here, so a
        failure part-way leaves the database exactly as it was.
        """
        with self.connection:
            yield self.connection

    # -- schema ------------------------------------------------------------

    @property
    def schema_version(self):
        return self.connection.execute("PRAGMA user_version").fetchone()[0]

    def _ensure_schema(self):
        """Create the schema, or bring an existing database up to date.

        A fresh file gets the whole schema at the current version and skips
        every migration. An existing one runs only the steps it has not seen.
        Both happen inside one transaction, so a half-applied upgrade cannot
        be left behind.
        """
        version = self.schema_version
        if version == SCHEMA_VERSION:
            return
        with self.connection:
            if version == 0:
                create_schema(self.connection)
            else:
                migrate(self.connection, version)

    def is_empty(self):
        for table in ("transactions", "accounts", "categories", "budgets"):
            if self.connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return False
        return True

    # -- accounts ----------------------------------------------------------

    @staticmethod
    def _account(row):
        return Account(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            opening=from_cents(row["opening_cents"]),
            position=row["position"],
        )

    def accounts(self):
        rows = self.connection.execute("SELECT * FROM accounts ORDER BY position, id")
        return [self._account(row) for row in rows]

    def account(self, account_id):
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return self._account(row) if row else None

    def account_by_name(self, name):
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE name_key = ?", (name_key(name),)
        ).fetchone()
        return self._account(row) if row else None

    def add_account(self, account):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO accounts (name, name_key, kind, opening_cents, position) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    account.name,
                    account.key,
                    account.kind,
                    to_cents(account.opening),
                    account.position,
                ),
            )
        account.id = cursor.lastrowid
        return account.id

    def update_account(self, account_id, **fields):
        sets, values = [], []
        if "name" in fields:
            sets += ["name = ?", "name_key = ?"]
            values += [fields["name"], name_key(fields["name"])]
        if "kind" in fields:
            sets.append("kind = ?")
            values.append(fields["kind"])
        if "opening" in fields:
            sets.append("opening_cents = ?")
            values.append(to_cents(fields["opening"]))
        if not sets:
            return
        values.append(account_id)
        with self.connection as conn:
            conn.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE id = ?", values)

    def delete_account(self, account_id):
        """Delete an account. Its transactions survive, unassigned."""
        with self.connection as conn:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    # -- categories --------------------------------------------------------

    @staticmethod
    def _category(row):
        return Category(id=row["id"], name=row["name"], kind=row["kind"])

    def categories(self, kind=None):
        if kind is None:
            rows = self.connection.execute("SELECT * FROM categories ORDER BY name")
        else:
            rows = self.connection.execute(
                "SELECT * FROM categories WHERE kind = ? ORDER BY name", (kind,)
            )
        return [self._category(row) for row in rows]

    def category(self, category_id):
        row = self.connection.execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        return self._category(row) if row else None

    def category_by_name(self, name, kind):
        row = self.connection.execute(
            "SELECT * FROM categories WHERE name_key = ? AND kind = ?",
            (name_key(name), kind),
        ).fetchone()
        return self._category(row) if row else None

    def add_category(self, category):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO categories (name, name_key, kind) VALUES (?, ?, ?)",
                (category.name, category.key, category.kind),
            )
        category.id = cursor.lastrowid
        return category.id

    def ensure_category(self, name, kind):
        """The category with this name, creating it if it does not exist.

        This is what lets a user type a category that has never been used
        before and have it simply work, rather than having to define it first.
        """
        if not (name or "").strip():
            return None
        existing = self.category_by_name(name, kind)
        if existing is not None:
            return existing.id
        return self.add_category(Category(name=name.strip(), kind=kind))

    def update_category(self, category_id, name):
        with self.connection as conn:
            conn.execute(
                "UPDATE categories SET name = ?, name_key = ? WHERE id = ?",
                (name, name_key(name), category_id),
            )

    def delete_category(self, category_id):
        """Delete a category. Its transactions survive, uncategorised.

        Subcategories and any budget go with it - a subcategory has no meaning
        without its parent, and a limit on a category that no longer exists is
        not a limit on anything.
        """
        with self.connection as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    # -- subcategories -----------------------------------------------------

    @staticmethod
    def _subcategory(row):
        return Subcategory(id=row["id"], name=row["name"], category_id=row["category_id"])

    def subcategories(self, category_id):
        rows = self.connection.execute(
            "SELECT * FROM subcategories WHERE category_id = ? ORDER BY name",
            (category_id,),
        )
        return [self._subcategory(row) for row in rows]

    def subcategory(self, subcategory_id):
        row = self.connection.execute(
            "SELECT * FROM subcategories WHERE id = ?", (subcategory_id,)
        ).fetchone()
        return self._subcategory(row) if row else None

    def subcategory_by_name(self, name, category_id):
        row = self.connection.execute(
            "SELECT * FROM subcategories WHERE name_key = ? AND category_id = ?",
            (name_key(name), category_id),
        ).fetchone()
        return self._subcategory(row) if row else None

    def add_subcategory(self, subcategory):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO subcategories (name, name_key, category_id) VALUES (?, ?, ?)",
                (subcategory.name, subcategory.key, subcategory.category_id),
            )
        subcategory.id = cursor.lastrowid
        return subcategory.id

    def ensure_subcategory(self, name, category_id):
        if not (name or "").strip() or category_id is None:
            return None
        existing = self.subcategory_by_name(name, category_id)
        if existing is not None:
            return existing.id
        return self.add_subcategory(Subcategory(name=name.strip(), category_id=category_id))

    def update_subcategory(self, subcategory_id, name):
        with self.connection as conn:
            conn.execute(
                "UPDATE subcategories SET name = ?, name_key = ? WHERE id = ?",
                (name, name_key(name), subcategory_id),
            )

    def delete_subcategory(self, subcategory_id):
        with self.connection as conn:
            conn.execute("DELETE FROM subcategories WHERE id = ?", (subcategory_id,))

    # -- transactions ------------------------------------------------------

    @staticmethod
    def _view(row):
        return TransactionView(
            id=row["id"],
            kind=row["kind"],
            description=row["description"],
            amount=from_cents(row["amount_cents"]),
            occurred_on=from_iso(row["occurred_on"]),
            category_id=row["category_id"],
            subcategory_id=row["subcategory_id"],
            account_id=row["account_id"],
            to_account_id=row["to_account_id"],
            category=row["category_name"],
            subcategory=row["subcategory_name"],
            account=row["account_name"],
            to_account=row["to_account_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def transactions(
        self,
        start=None,
        end=None,
        kind=None,
        account_id=None,
        category_id=None,
        subcategory_id=None,
        search=None,
        limit=None,
    ):
        """Transactions matching the given filters, oldest first.

        Filtering happens in SQL, against indexes, rather than by loading
        everything and looping. `start` and `end` are date objects and both
        bounds are inclusive.
        """
        clauses, values = [], []

        # Every column is qualified with its table. The query joins categories
        # and subcategories, both of which also have a `name`, and the joined
        # tables share column names with transactions - an unqualified column
        # here is ambiguous and SQLite rejects the whole query.
        if start is not None:
            clauses.append("t.occurred_on >= ?")
            values.append(start.isoformat())
        if end is not None:
            clauses.append("t.occurred_on <= ?")
            values.append(end.isoformat())
        if kind is not None:
            clauses.append("t.kind = ?")
            values.append(kind)
        if account_id is not None:
            # A transfer touches two accounts and belongs to both.
            clauses.append("(t.account_id = ? OR t.to_account_id = ?)")
            values += [account_id, account_id]
        if category_id is not None:
            clauses.append("t.category_id = ?")
            values.append(category_id)
        if subcategory_id is not None:
            clauses.append("t.subcategory_id = ?")
            values.append(subcategory_id)
        if search:
            # Matched against the joined names too, so searching for a category
            # finds its transactions without the caller resolving it first.
            clauses.append("(t.description LIKE ? OR c.name LIKE ? OR s.name LIKE ?)")
            pattern = f"%{search}%"
            values += [pattern, pattern, pattern]

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        tail = f" LIMIT {int(limit)}" if limit else ""
        # The joins are needed for the search clause anyway, so the names come
        # back at no extra cost and callers never have to resolve an id.
        sql = (
            "SELECT t.*, "
            "  c.name  AS category_name, "
            "  s.name  AS subcategory_name, "
            "  a.name  AS account_name, "
            "  a2.name AS to_account_name "
            "FROM transactions t "
            "LEFT JOIN categories c    ON c.id  = t.category_id "
            "LEFT JOIN subcategories s ON s.id  = t.subcategory_id "
            "LEFT JOIN accounts a      ON a.id  = t.account_id "
            "LEFT JOIN accounts a2     ON a2.id = t.to_account_id "
            f"{where} ORDER BY t.occurred_on, t.id{tail}"
        )
        return [self._view(row) for row in self.connection.execute(sql, values)]

    def transaction(self, transaction_id):
        """One transaction as a view.

        A view, not a model, so every read returns the same shape - the names
        are already resolved and callers never have to check which they got.
        """
        row = self.connection.execute(
            "SELECT t.*, "
            "  c.name  AS category_name, "
            "  s.name  AS subcategory_name, "
            "  a.name  AS account_name, "
            "  a2.name AS to_account_name "
            "FROM transactions t "
            "LEFT JOIN categories c    ON c.id  = t.category_id "
            "LEFT JOIN subcategories s ON s.id  = t.subcategory_id "
            "LEFT JOIN accounts a      ON a.id  = t.account_id "
            "LEFT JOIN accounts a2     ON a2.id = t.to_account_id "
            "WHERE t.id = ?",
            (transaction_id,),
        ).fetchone()
        return self._view(row) if row else None

    def count_transactions(self):
        return self.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    def add_transaction(self, transaction, connection=None):
        """Insert one transaction. Returns its new id."""
        conn = connection or self.connection
        sql = (
            "INSERT INTO transactions (kind, description, amount_cents, occurred_on, "
            " category_id, subcategory_id, account_id, to_account_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        values = (
            transaction.kind,
            transaction.description,
            to_cents(transaction.amount),
            to_iso(transaction.occurred_on),
            transaction.category_id,
            transaction.subcategory_id,
            transaction.account_id,
            transaction.to_account_id,
        )
        if connection is not None:
            cursor = conn.execute(sql, values)
        else:
            with conn:
                cursor = conn.execute(sql, values)
        transaction.id = cursor.lastrowid
        return transaction.id

    # Column names accepted by update_transaction, mapped to how the value is
    # converted on the way in.
    _TRANSACTION_FIELDS = {
        "kind": lambda v: v,
        "description": lambda v: v,
        "amount": to_cents,
        "occurred_on": to_iso,
        "category_id": lambda v: v,
        "subcategory_id": lambda v: v,
        "account_id": lambda v: v,
        "to_account_id": lambda v: v,
    }
    _TRANSACTION_COLUMNS = {"amount": "amount_cents"}

    def update_transaction(self, transaction_id, **fields):
        """Change some fields of one transaction.

        A field passed as None sets the column to NULL, which is how a
        category or an account is cleared. Fields not passed are left alone.
        """
        sets, values = [], []
        for name, value in fields.items():
            if name not in self._TRANSACTION_FIELDS:
                raise ValueError(f"fushe e panjohur: {name}")
            column = self._TRANSACTION_COLUMNS.get(name, name)
            sets.append(f"{column} = ?")
            values.append(None if value is None else self._TRANSACTION_FIELDS[name](value))
        if not sets:
            return
        values.append(transaction_id)
        with self.connection as conn:
            conn.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE id = ?", values)

    def delete_transaction(self, transaction_id):
        with self.connection as conn:
            conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    # -- recurring rules ---------------------------------------------------

    @staticmethod
    def _rule(row):
        return RecurringRule(
            id=row["id"],
            kind=row["kind"],
            description=row["description"],
            amount=from_cents(row["amount_cents"]),
            frequency=row["frequency"],
            starts_on=from_iso(row["starts_on"]),
            generated_upto=from_iso(row["generated_upto"]) or None,
            category_id=row["category_id"],
            subcategory_id=row["subcategory_id"],
            account_id=row["account_id"],
            to_account_id=row["to_account_id"],
        )

    def recurring_rules(self):
        rows = self.connection.execute("SELECT * FROM recurring_rules ORDER BY id")
        return [self._rule(row) for row in rows]

    def add_recurring_rule(self, rule):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO recurring_rules (kind, description, amount_cents, "
                " category_id, subcategory_id, account_id, to_account_id, "
                " frequency, starts_on, generated_upto) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rule.kind,
                    rule.description,
                    to_cents(rule.amount),
                    rule.category_id,
                    rule.subcategory_id,
                    rule.account_id,
                    rule.to_account_id,
                    rule.frequency,
                    to_iso(rule.starts_on),
                    to_iso(rule.generated_upto) if rule.generated_upto else None,
                ),
            )
        rule.id = cursor.lastrowid
        return rule.id

    def set_rule_generated_upto(self, rule_id, date_text, connection=None):
        conn = connection or self.connection
        sql = "UPDATE recurring_rules SET generated_upto = ? WHERE id = ?"
        values = (to_iso(date_text), rule_id)
        if connection is not None:
            conn.execute(sql, values)
        else:
            with conn:
                conn.execute(sql, values)

    def delete_recurring_rule(self, rule_id):
        with self.connection as conn:
            conn.execute("DELETE FROM recurring_rules WHERE id = ?", (rule_id,))

    # -- budgets -----------------------------------------------------------

    @staticmethod
    def _budget(row):
        return Budget(
            id=row["id"],
            category_id=row["category_id"],
            limit=from_cents(row["limit_cents"]),
        )

    def budgets(self):
        rows = self.connection.execute(
            "SELECT b.* FROM budgets b JOIN categories c ON c.id = b.category_id ORDER BY c.name"
        )
        return [self._budget(row) for row in rows]

    def budget_for(self, category_id):
        row = self.connection.execute(
            "SELECT * FROM budgets WHERE category_id = ?", (category_id,)
        ).fetchone()
        return self._budget(row) if row else None

    def set_budget(self, category_id, amount):
        """Create or replace the limit on one category."""
        with self.connection as conn:
            conn.execute(
                "INSERT INTO budgets (category_id, limit_cents) VALUES (?, ?) "
                "ON CONFLICT(category_id) DO UPDATE SET limit_cents = excluded.limit_cents",
                (category_id, to_cents(amount)),
            )

    def delete_budget(self, category_id):
        with self.connection as conn:
            conn.execute("DELETE FROM budgets WHERE category_id = ?", (category_id,))

    # -- aggregate queries -------------------------------------------------

    def spent_in_month(self, category_id, year, month):
        """Total spent in one category during one month, summed in SQL."""
        prefix = f"{year:04d}-{month:02d}-%"
        row = self.connection.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions "
            "WHERE kind = ? AND category_id = ? AND occurred_on LIKE ?",
            (EXPENSE, category_id, prefix),
        ).fetchone()
        return from_cents(row[0])
