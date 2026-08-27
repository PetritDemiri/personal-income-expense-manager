"""Skema e bazes se te dhenave / Database schema.

The schema as it stands, written out in full rather than assembled from a
chain of migrations. Version 3 starts from an empty database, so there is no
history to carry and no ALTER TABLE dance to perform.

Names in SQL and in Python are English. Values stored in those columns stay
Albanian, because they are the user's data and the interface language must not
rewrite them. That line - English structure, Albanian content - is the same one
the display layer already draws.

Four choices worth knowing about:

Money is an INTEGER count of cents. SQLite's REAL is a float, and a float is
the one thing this program has always refused to store money in.

Dates are ISO text, yyyy-mm-dd. SQLite has no date type; ISO is the only text
form that sorts and range-queries correctly. The dd-mm-yyyy the user sees is a
display concern, converted at the boundary.

Every named thing carries a normalised copy of its name for uniqueness.
SQLite's COLLATE NOCASE folds only A-Z, so it would happily accept "Ushqim" and
"ushqim" as two categories, and would miss "Ë" against "ë" entirely. Python's
casefold handles the whole Albanian alphabet, so the constraint sits on a
column we compute rather than on a collation we cannot trust.

Deleting a category or an account does not delete what referenced it. The
spending still happened; only the label is gone. Hence SET NULL rather than
CASCADE - except for a subcategory, which has no meaning without its parent,
and a budget, which is a limit on a category that no longer exists.

Two constraints are deliberately absent.

There is no maximum amount. Any ceiling would be arbitrary, and it would not
catch the mistake that actually happens - a digit too many is still a plausible
number. A limit that rejects real data one day to catch nothing today is a bad
trade.

There is no CHECK on an account's kind or a rule's frequency, even though
transaction kinds have one. Income and expense are what money does and that
list will not grow; cash, bank and card are a convenience taxonomy that
probably will, and so are frequencies. Both are validated by the application,
and the hand-edited CSV files that once made unvalidated values possible are
gone.
"""

SCHEMA_VERSION = 4

# Transaction types, as stored. Repeated in the CHECK constraints below so the
# database rejects anything else regardless of what the application believes.
INCOME = "Te Ardhura"
EXPENSE = "Shpenzime"
TRANSFER = "Transferim"

SCHEMA = f"""
CREATE TABLE accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    name_key    TEXT    NOT NULL UNIQUE,
    kind        TEXT    NOT NULL,
    opening_cents INTEGER NOT NULL DEFAULT 0,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    name_key    TEXT    NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('{INCOME}', '{EXPENSE}')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name_key, kind)
);

CREATE TABLE subcategories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    name_key    TEXT    NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name_key, category_id)
);

CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT    NOT NULL
                    CHECK (kind IN ('{INCOME}', '{EXPENSE}', '{TRANSFER}')),
    description     TEXT    NOT NULL CHECK (length(trim(description)) > 0),
    amount_cents    INTEGER NOT NULL CHECK (amount_cents >= 0),
    occurred_on     TEXT    NOT NULL,
    category_id     INTEGER REFERENCES categories(id)    ON DELETE SET NULL,
    subcategory_id  INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    account_id      INTEGER REFERENCES accounts(id)      ON DELETE SET NULL,
    to_account_id   INTEGER REFERENCES accounts(id)      ON DELETE SET NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    -- A transfer from an account to itself is not a transfer. Written so that
    -- either side being NULL satisfies it, because deleting an account sets
    -- these to NULL and a stricter rule would make that delete fail.
    CHECK (account_id IS NULL
           OR to_account_id IS NULL
           OR account_id != to_account_id),
    -- Shape only. The column is range-queried and sorted as text, so it has
    -- to look like an ISO date; whether it is a real calendar date is the
    -- repository's business.
    CHECK (occurred_on LIKE '____-__-__')
);

CREATE TABLE recurring_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT    NOT NULL
                    CHECK (kind IN ('{INCOME}', '{EXPENSE}', '{TRANSFER}')),
    description     TEXT    NOT NULL CHECK (length(trim(description)) > 0),
    amount_cents    INTEGER NOT NULL CHECK (amount_cents >= 0),
    category_id     INTEGER REFERENCES categories(id)    ON DELETE SET NULL,
    subcategory_id  INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    account_id      INTEGER REFERENCES accounts(id)      ON DELETE SET NULL,
    to_account_id   INTEGER REFERENCES accounts(id)      ON DELETE SET NULL,
    frequency       TEXT    NOT NULL,
    starts_on       TEXT    NOT NULL,
    generated_upto  TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (account_id IS NULL
           OR to_account_id IS NULL
           OR account_id != to_account_id),
    CHECK (starts_on LIKE '____-__-__'),
    CHECK (generated_upto IS NULL OR generated_upto LIKE '____-__-__')
);

CREATE TABLE budgets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL UNIQUE
                REFERENCES categories(id) ON DELETE CASCADE,
    limit_cents INTEGER NOT NULL CHECK (limit_cents > 0),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Append only. Nothing in the application updates or deletes a row here, and
-- the row it describes may since have been deleted, so entity_id is recorded
-- as a plain integer rather than as a foreign key.
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity      TEXT    NOT NULL,
    entity_id   INTEGER,
    action      TEXT    NOT NULL CHECK (action IN ('create', 'update', 'delete')),
    before_json TEXT,
    after_json  TEXT,
    at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- updated_at is maintained by the database rather than by the code. A column
-- DEFAULT fires only on INSERT, so without these the column would record the
-- creation time forever and quietly claim a row had never changed.
--
-- Triggers rather than eight UPDATE statements: the writes are spread across
-- two modules, two of them raw SQL, and one forgotten site would be invisible.
--
-- The WHEN guard stops the trigger firing on its own write, and lets a caller
-- set updated_at explicitly when it needs to.
CREATE TRIGGER touch_transactions AFTER UPDATE ON transactions FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE transactions SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER touch_accounts AFTER UPDATE ON accounts FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE accounts SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER touch_categories AFTER UPDATE ON categories FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE categories SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER touch_subcategories AFTER UPDATE ON subcategories FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE subcategories SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER touch_recurring_rules AFTER UPDATE ON recurring_rules FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE recurring_rules SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER touch_budgets AFTER UPDATE ON budgets FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE budgets SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE INDEX idx_transactions_date       ON transactions(occurred_on);
CREATE INDEX idx_transactions_kind_date  ON transactions(kind, occurred_on);
CREATE INDEX idx_transactions_category   ON transactions(category_id);
CREATE INDEX idx_transactions_account    ON transactions(account_id);
CREATE INDEX idx_transactions_to_account ON transactions(to_account_id);
CREATE INDEX idx_subcategories_category  ON subcategories(category_id);
CREATE INDEX idx_audit_entity            ON audit_log(entity, entity_id);
"""


# Every table that carries an updated_at, and therefore a touch trigger.
TOUCHED_TABLES = (
    "transactions",
    "accounts",
    "categories",
    "subcategories",
    "recurring_rules",
    "budgets",
)

TOUCH_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS touch_{table} AFTER UPDATE ON {table} FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE {table} SET updated_at = datetime('now') WHERE id = NEW.id;
END;
"""


def _migration_4(connection):
    """Add the touch triggers to a database created before they existed.

    Purely additive - no table is rebuilt and no row is touched, so a database
    that has been in daily use upgrades in place.
    """
    for table in TOUCHED_TABLES:
        connection.executescript(TOUCH_TRIGGER.format(table=table))


# Keyed by the version each step brings the database up to. A database created
# fresh gets the whole schema at SCHEMA_VERSION and skips these entirely.
MIGRATIONS = {
    4: _migration_4,
}


def create_schema(connection):
    """Create every table, index and trigger, and record the schema version."""
    connection.executescript(SCHEMA)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def migrate(connection, from_version):
    """Bring an existing database up to SCHEMA_VERSION, one step at a time."""
    for version in sorted(MIGRATIONS):
        if version > from_version:
            MIGRATIONS[version](connection)
            connection.execute(f"PRAGMA user_version = {int(version)}")
