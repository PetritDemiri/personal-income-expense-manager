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

import datetime
import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal

from .dates import parse_date
from .models import (
    Account,
    AuditEntry,
    Budget,
    Category,
    CategoryRule,
    RecurringRule,
    Subcategory,
    TransactionView,
    User,
    name_key,
)
from .passwords import hash_password, verify_password
from .schema import (
    DEFAULT_USER_NAME,
    EXPENSE,
    SCHEMA_VERSION,
    create_schema,
    migrate,
)


class UnknownUser(Exception):
    """A named user that does not exist."""


CENTS = Decimal("0.01")


def carry_over(source, target):
    """Copy a database to a new place, whole and consistent, leaving the original.

    Used once, when the program moves its data from the old default location
    to the new one. SQLite's own backup is used rather than copying the file,
    because a database in WAL mode keeps recent changes in a second file that
    a plain copy would leave behind. The copy is written under a temporary
    name and only renamed into place once it is complete and checked, so an
    interruption leaves no half-written database where the program will look.
    The original is never touched: if anything about the move is wrong, the
    data is still exactly where it was.
    """
    directory = os.path.dirname(os.path.abspath(target))
    os.makedirs(directory, exist_ok=True)
    partial = f"{target}.part"
    try:
        os.remove(partial)
    except OSError:
        pass

    try:
        source_connection = sqlite3.connect(source)
        try:
            target_connection = sqlite3.connect(partial)
            try:
                source_connection.backup(target_connection)
                verdict = target_connection.execute("PRAGMA quick_check").fetchone()[0]
            finally:
                target_connection.close()
        finally:
            source_connection.close()
        if verdict != "ok":
            raise sqlite3.DatabaseError(verdict)
        os.replace(partial, target)
    except BaseException:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise


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

    def __init__(self, path, user=None, auto_user=True):
        self.path = path
        self._requested_user = user
        self._user_id = None
        # A fresh database normally gets a single user so it is usable at
        # once. The command line turns this off, because an empty database is
        # where the first administrator is generated instead, and an
        # auto-created user would take that slot before setup could run.
        self._auto_user = auto_user
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.created = not os.path.exists(path)
        self._connection = None
        self._ensure_schema()
        self._ensure_user()

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

        if version == 0:
            with self.connection:
                create_schema(self.connection)
            return

        # Foreign keys are switched off for the duration. A migration that
        # rebuilds a table has to drop the original, and with them enabled
        # that cascades into every table referencing it. The pragma is a
        # no-op inside a transaction, so it is set outside one.
        before = self._totals()
        self.connection.execute("PRAGMA foreign_keys = OFF")
        try:
            with self.connection:
                migrate(self.connection, version)
                broken = self.connection.execute("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(f"migrimi la {len(broken)} referenca te thyera")
                after = self._totals()
                # Only what existed beforehand is compared. A migration may
                # legitimately add a table, and that is not data loss; a row
                # or a cent going missing is.
                lost = {
                    key: (value, after.get(key))
                    for key, value in before.items()
                    if after.get(key) != value
                }
                if lost:
                    raise RuntimeError(f"migrimi ndryshoi te dhenat: {lost}")
        finally:
            self.connection.execute("PRAGMA foreign_keys = ON")

    # -- users -------------------------------------------------------------

    def _ensure_user(self):
        """Settle whose data this session is working with.

        A database always has at least one user. With none named, the first is
        used - which is every single-person installation, and is why the
        command line can stay unchanged for anyone who never creates a second.
        """
        rows = list(self.connection.execute("SELECT id, name_key FROM users ORDER BY id"))
        if not rows:
            if not self._auto_user:
                self._user_id = None
                return
            # The only user there is, so they hold every power the program
            # offers; anything else would lock them out of their own data.
            with self.connection:
                cursor = self.connection.execute(
                    "INSERT INTO users (name, name_key, is_admin) VALUES (?, ?, 1)",
                    (DEFAULT_USER_NAME, name_key(DEFAULT_USER_NAME)),
                )
            self._user_id = cursor.lastrowid
            return

        if self._requested_user:
            wanted = name_key(self._requested_user)
            for row in rows:
                if row["name_key"] == wanted:
                    self._user_id = row["id"]
                    return
            raise UnknownUser(self._requested_user)

        self._user_id = rows[0]["id"]

    @property
    def user_id(self):
        return self._user_id

    @staticmethod
    def _user(row):
        return User(
            id=row["id"],
            name=row["name"],
            password_hash=row["password_hash"],
            password_salt=row["password_salt"],
            password_iters=row["password_iters"],
            is_admin=bool(row["is_admin"]),
            must_change=bool(row["must_change"]),
        )

    def users(self):
        rows = self.connection.execute("SELECT * FROM users ORDER BY id")
        return [self._user(row) for row in rows]

    def user(self, user_id=None):
        row = self.connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id or self._user_id,)
        ).fetchone()
        return self._user(row) if row else None

    def user_by_name(self, name):
        row = self.connection.execute(
            "SELECT * FROM users WHERE name_key = ?", (name_key(name),)
        ).fetchone()
        return self._user(row) if row else None

    def add_user(self, name, password=None, is_admin=False, must_change=False):
        values = [name, name_key(name), None, None, None, None]
        if password:
            values[2], values[3], values[4] = hash_password(password)
            values[5] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO users (name, name_key, password_hash, password_salt, "
                " password_iters, password_set_at, is_admin, must_change) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*values, int(is_admin), int(must_change)),
            )
        return cursor.lastrowid

    def set_must_change(self, user_id, required):
        with self.connection as conn:
            conn.execute(
                "UPDATE users SET must_change = ? WHERE id = ?",
                (int(required), user_id),
            )

    def admin_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[
            0
        ]

    def set_admin(self, user_id, is_admin):
        with self.connection as conn:
            conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, user_id),
            )

    def use_user(self, user_id):
        """Work as a different user for the rest of this session."""
        self._user_id = user_id

    def set_password(self, user_id, password):
        """Store a password hash, or clear it when given nothing.

        The moment is stamped so the change history can record that a password
        changed and when, without the hash itself ever being copied into a log
        that outlives it.
        """
        if password:
            digest, salt, iterations = hash_password(password)
            stamped = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            digest = salt = iterations = stamped = None
        with self.connection as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, password_salt = ?, "
                " password_iters = ?, password_set_at = ?, must_change = 0 "
                "WHERE id = ?",
                (digest, salt, iterations, stamped, user_id),
            )

    def check_password(self, user_id, password):
        user = self.user(user_id)
        if user is None or not user.has_password:
            return False
        return verify_password(
            password, user.password_hash, user.password_salt, user.password_iters
        )

    def rename_user(self, user_id, name):
        with self.connection as conn:
            conn.execute(
                "UPDATE users SET name = ?, name_key = ? WHERE id = ?",
                (name, name_key(name), user_id),
            )

    def delete_user(self, user_id):
        """Delete a user and everything they own.

        Cascades through every table. There is no softer option: their data
        means nothing without them, and leaving it orphaned would be worse
        than removing it.
        """
        with self.connection as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def _totals(self):
        """Row counts and money totals, for checking a migration changed nothing.

        A migration that rebuilds tables holding real money should have to
        prove it moved none of it. Anything missing here rolls the whole
        upgrade back rather than leaving a database that looks fine.
        """
        counted = {}
        for table in (
            "transactions",
            "accounts",
            "categories",
            "subcategories",
            "recurring_rules",
            "budgets",
            "category_rules",
        ):
            exists = self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()
            if not exists:
                continue
            counted[table] = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        if "transactions" in counted:
            counted["amount_cents"] = self.connection.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions"
            ).fetchone()[0]
        if "accounts" in counted:
            counted["opening_cents"] = self.connection.execute(
                "SELECT COALESCE(SUM(opening_cents), 0) FROM accounts"
            ).fetchone()[0]
        return counted

    def is_empty(self):
        for table in ("transactions", "accounts", "categories", "budgets"):
            found = self.connection.execute(
                f"SELECT 1 FROM {table} WHERE user_id = ? LIMIT 1", (self._user_id,)
            ).fetchone()
            if found:
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
        rows = self.connection.execute(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY position, id",
            (self._user_id,),
        )
        return [self._account(row) for row in rows]

    def account(self, account_id):
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, self._user_id),
        ).fetchone()
        return self._account(row) if row else None

    def account_by_name(self, name):
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE name_key = ? AND user_id = ?",
            (name_key(name), self._user_id),
        ).fetchone()
        return self._account(row) if row else None

    def add_account(self, account):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO accounts (user_id, name, name_key, kind, opening_cents, position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self._user_id,
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
            rows = self.connection.execute(
                "SELECT * FROM categories WHERE user_id = ? ORDER BY name",
                (self._user_id,),
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM categories WHERE kind = ? AND user_id = ? ORDER BY name",
                (kind, self._user_id),
            )
        return [self._category(row) for row in rows]

    def category(self, category_id):
        row = self.connection.execute(
            "SELECT * FROM categories WHERE id = ? AND user_id = ?",
            (category_id, self._user_id),
        ).fetchone()
        return self._category(row) if row else None

    def category_by_name(self, name, kind):
        row = self.connection.execute(
            "SELECT * FROM categories WHERE name_key = ? AND kind = ? AND user_id = ?",
            (name_key(name), kind, self._user_id),
        ).fetchone()
        return self._category(row) if row else None

    def add_category(self, category):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO categories (user_id, name, name_key, kind) VALUES (?, ?, ?, ?)",
                (self._user_id, category.name, category.key, category.kind),
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
            "SELECT * FROM subcategories WHERE category_id = ? AND user_id = ? ORDER BY name",
            (category_id, self._user_id),
        )
        return [self._subcategory(row) for row in rows]

    def subcategory(self, subcategory_id):
        row = self.connection.execute(
            "SELECT * FROM subcategories WHERE id = ? AND user_id = ?",
            (subcategory_id, self._user_id),
        ).fetchone()
        return self._subcategory(row) if row else None

    def subcategory_by_name(self, name, category_id):
        row = self.connection.execute(
            "SELECT * FROM subcategories WHERE name_key = ? AND category_id = ? AND user_id = ?",
            (name_key(name), category_id, self._user_id),
        ).fetchone()
        return self._subcategory(row) if row else None

    def add_subcategory(self, subcategory):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO subcategories (user_id, name, name_key, category_id) "
                "VALUES (?, ?, ?, ?)",
                (self._user_id, subcategory.name, subcategory.key, subcategory.category_id),
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
        clauses, values = ["t.user_id = ?"], [self._user_id]

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
            "WHERE t.id = ? AND t.user_id = ?",
            (transaction_id, self._user_id),
        ).fetchone()
        return self._view(row) if row else None

    def count_transactions(self):
        return self.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (self._user_id,)
        ).fetchone()[0]

    def add_transaction(self, transaction, connection=None):
        """Insert one transaction. Returns its new id."""
        conn = connection or self.connection
        sql = (
            "INSERT INTO transactions (user_id, kind, description, amount_cents, "
            " occurred_on, category_id, subcategory_id, account_id, to_account_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        values = (
            self._user_id,
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
        rows = self.connection.execute(
            "SELECT * FROM recurring_rules WHERE user_id = ? ORDER BY id",
            (self._user_id,),
        )
        return [self._rule(row) for row in rows]

    def add_recurring_rule(self, rule):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO recurring_rules (user_id, kind, description, "
                " amount_cents, category_id, subcategory_id, account_id, "
                " to_account_id, frequency, starts_on, generated_upto) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._user_id,
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
            "SELECT b.* FROM budgets b JOIN categories c ON c.id = b.category_id "
            "WHERE b.user_id = ? ORDER BY c.name",
            (self._user_id,),
        )
        return [self._budget(row) for row in rows]

    def budget_for(self, category_id):
        row = self.connection.execute(
            "SELECT * FROM budgets WHERE category_id = ? AND user_id = ?",
            (category_id, self._user_id),
        ).fetchone()
        return self._budget(row) if row else None

    def set_budget(self, category_id, amount):
        """Create or replace the limit on one category."""
        with self.connection as conn:
            conn.execute(
                "INSERT INTO budgets (user_id, category_id, limit_cents) VALUES (?, ?, ?) "
                "ON CONFLICT(category_id) DO UPDATE SET limit_cents = excluded.limit_cents",
                (self._user_id, category_id, to_cents(amount)),
            )

    def delete_budget(self, category_id):
        with self.connection as conn:
            conn.execute("DELETE FROM budgets WHERE category_id = ?", (category_id,))

    # -- category rules ----------------------------------------------------

    @staticmethod
    def _rule_row(row):
        return CategoryRule(
            id=row["id"],
            pattern=row["pattern"],
            category_id=row["category_id"],
            subcategory_id=row["subcategory_id"],
            category=row["category_name"],
            subcategory=row["subcategory_name"],
        )

    def category_rules(self):
        """Every rule, with the names it points at already resolved."""
        rows = self.connection.execute(
            "SELECT r.*, c.name AS category_name, s.name AS subcategory_name "
            "FROM category_rules r "
            "LEFT JOIN categories c    ON c.id = r.category_id "
            "LEFT JOIN subcategories s ON s.id = r.subcategory_id "
            "WHERE r.user_id = ? ORDER BY length(r.pattern_key) DESC, r.pattern",
            (self._user_id,),
        )
        return [self._rule_row(row) for row in rows]

    def rule_by_pattern(self, pattern):
        row = self.connection.execute(
            "SELECT r.*, c.name AS category_name, s.name AS subcategory_name "
            "FROM category_rules r "
            "LEFT JOIN categories c    ON c.id = r.category_id "
            "LEFT JOIN subcategories s ON s.id = r.subcategory_id "
            "WHERE r.pattern_key = ? AND r.user_id = ?",
            (name_key(pattern), self._user_id),
        ).fetchone()
        return self._rule_row(row) if row else None

    def add_category_rule(self, rule):
        with self.connection as conn:
            cursor = conn.execute(
                "INSERT INTO category_rules (user_id, pattern, pattern_key, category_id, "
                " subcategory_id) VALUES (?, ?, ?, ?, ?)",
                (self._user_id, rule.pattern, rule.key, rule.category_id, rule.subcategory_id),
            )
        rule.id = cursor.lastrowid
        return rule.id

    def update_category_rule(self, rule_id, **fields):
        sets, values = [], []
        if "pattern" in fields:
            sets += ["pattern = ?", "pattern_key = ?"]
            values += [fields["pattern"], name_key(fields["pattern"])]
        for name in ("category_id", "subcategory_id"):
            if name in fields:
                sets.append(f"{name} = ?")
                values.append(fields[name])
        if not sets:
            return
        values.append(rule_id)
        with self.connection as conn:
            conn.execute(f"UPDATE category_rules SET {', '.join(sets)} WHERE id = ?", values)

    def delete_category_rule(self, rule_id):
        with self.connection as conn:
            conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))

    def count_matching(self, pattern):
        """How many stored transactions a pattern would match.

        Asked before a rule is saved: a pattern of "a" matching three hundred
        rows is something to learn beforehand, not afterwards.
        """
        needle = f"%{pattern.strip()}%"
        return self.connection.execute(
            "SELECT COUNT(*) FROM transactions "
            "WHERE user_id = ? AND description LIKE ? COLLATE NOCASE",
            (self._user_id, needle),
        ).fetchone()[0]

    # -- audit log ---------------------------------------------------------

    def audit_entries(self, entity=None, entity_id=None, limit=50):
        """Recent changes, newest first.

        Narrow to one row by passing both entity and entity_id - "what has
        happened to this transaction?" is the question this is usually asked.
        """
        clauses, values = ["user_id = ?"], [self._user_id]
        if entity is not None:
            clauses.append("entity = ?")
            values.append(entity)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            values.append(entity_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, entity, entity_id, action, before_json, after_json, at "
            f"FROM audit_log {where} ORDER BY id DESC LIMIT {int(limit)}"
        )
        return [AuditEntry.from_row(row) for row in self.connection.execute(sql, values)]

    def audit_count(self):
        return self.connection.execute(
            "SELECT COUNT(*) FROM audit_log WHERE user_id = ?", (self._user_id,)
        ).fetchone()[0]

    # -- aggregate queries -------------------------------------------------

    def spent_in_month(self, category_id, year, month):
        """Total spent in one category during one month, summed in SQL."""
        prefix = f"{year:04d}-{month:02d}-%"
        row = self.connection.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions "
            "WHERE user_id = ? AND kind = ? AND category_id = ? AND occurred_on LIKE ?",
            (self._user_id, EXPENSE, category_id, prefix),
        ).fetchone()
        return from_cents(row[0])
