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

import re

SCHEMA_VERSION = 10

# The single user a database gains when it is upgraded from before users
# existed. Everything already stored becomes theirs.
DEFAULT_USER_NAME = "Une"

# Transaction types, as stored. Repeated in the CHECK constraints below so the
# database rejects anything else regardless of what the application believes.
INCOME = "Te Ardhura"
EXPENSE = "Shpenzime"
TRANSFER = "Transferim"

SCHEMA = f"""
-- One person's finances. Someone with a password is asked for it at the
-- sign-in screen; someone without one never is. Whoever holds this file can
-- still open it directly - the file's own permissions are that boundary.
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    name_key       TEXT    NOT NULL UNIQUE,
    password_hash  TEXT,
    password_salt  TEXT,
    password_iters INTEGER,
    -- What someone may do beyond their own data: see the other users, add,
    -- rename and remove them, and reset a password they do not know. An
    -- ordinary user can do none of that, which is the whole point of the
    -- distinction.
    is_admin       INTEGER NOT NULL DEFAULT 0,
    -- Set while the generated first-run credentials are still in force. The
    -- account cannot be used for anything until its own name and password
    -- replace them.
    must_change    INTEGER NOT NULL DEFAULT 0,
    -- When the password last changed. Audited in place of the hash itself, so
    -- the history records that a password changed and when, while no hash -
    -- current or superseded - is ever copied into the log.
    password_set_at TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    name_key    TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    opening_cents INTEGER NOT NULL DEFAULT 0,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name_key)
);

CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    name_key    TEXT    NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('{INCOME}', '{EXPENSE}')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name_key, kind)
);

CREATE TABLE subcategories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    name_key    TEXT    NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name_key, category_id)
);

CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL UNIQUE
                REFERENCES categories(id) ON DELETE CASCADE,
    limit_cents INTEGER NOT NULL CHECK (limit_cents > 0),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE category_rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern        TEXT    NOT NULL CHECK (length(trim(pattern)) > 0),
    pattern_key    TEXT    NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(id)    ON DELETE CASCADE,
    subcategory_id INTEGER          REFERENCES subcategories(id) ON DELETE SET NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, pattern_key)
);

-- The credentials generated the first time an empty database is opened.
-- Written to a file for the person at the keyboard to read, and hashed here,
-- exactly as a password reset is. The database is empty at this point, so if
-- these expire unused the next run generates fresh ones rather than locking
-- anyone out of a file with nothing in it.
CREATE TABLE admin_setup (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT    NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);

-- A logged-in session. The token is stored hashed, so the database never
-- holds a usable one - anyone reading this table finds nothing they can
-- present as a login.
CREATE TABLE sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);

-- A password reset in progress. Hashed for the same reason, with the attempts
-- counted so a code cannot be guessed by repetition, and `used` so a correct
-- code works exactly once.
CREATE TABLE password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT    NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);

-- Append only. Nothing in the application updates or deletes a row here, and
-- the row it describes may since have been deleted, so entity_id is recorded
-- as a plain integer rather than as a foreign key.
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    entity      TEXT    NOT NULL,
    entity_id   INTEGER,
    action      TEXT    NOT NULL CHECK (action IN ('create', 'update', 'delete')),
    before_json TEXT,
    after_json  TEXT,
    at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_transactions_user       ON transactions(user_id, occurred_on);
CREATE INDEX idx_accounts_user            ON accounts(user_id);
CREATE INDEX idx_categories_user          ON categories(user_id);
CREATE INDEX idx_audit_user               ON audit_log(user_id);
CREATE INDEX idx_transactions_date       ON transactions(occurred_on);
CREATE INDEX idx_transactions_kind_date  ON transactions(kind, occurred_on);
CREATE INDEX idx_transactions_category   ON transactions(category_id);
CREATE INDEX idx_transactions_account    ON transactions(account_id);
CREATE INDEX idx_transactions_to_account ON transactions(to_account_id);
CREATE INDEX idx_subcategories_category  ON subcategories(category_id);
CREATE INDEX idx_audit_entity            ON audit_log(entity, entity_id);
CREATE INDEX idx_rules_category           ON category_rules(category_id);
CREATE INDEX idx_sessions_user            ON sessions(user_id);
CREATE INDEX idx_resets_user              ON password_resets(user_id);
"""


# Every audited table, and the columns worth recording. created_at, updated_at
# and the name_key columns are left out: they are bookkeeping rather than
# anything the user entered, and including updated_at would make every entry
# show a timestamp change on top of the real one.
AUDITED_TABLES = {
    "transactions": (
        "kind",
        "description",
        "amount_cents",
        "occurred_on",
        "category_id",
        "subcategory_id",
        "account_id",
        "to_account_id",
    ),
    "accounts": ("name", "kind", "opening_cents", "position"),
    "categories": ("name", "kind"),
    "subcategories": ("name", "category_id"),
    "recurring_rules": (
        "kind",
        "description",
        "amount_cents",
        "category_id",
        "subcategory_id",
        "account_id",
        "to_account_id",
        "frequency",
        "starts_on",
        "generated_upto",
    ),
    "budgets": ("category_id", "limit_cents"),
    "category_rules": ("pattern", "category_id", "subcategory_id"),
    # Deliberately not the hash, the salt or the iteration count. Recording
    # those would copy a superseded password hash into an append-only log that
    # outlives the change.
    "users": ("name", "is_admin", "password_set_at"),
}

# Tables whose owning user is the row itself rather than a user_id column.
SELF_OWNED = ("users",)

# Tables carrying a user_id, so the audit trigger can record who changed what.
USER_OWNED = tuple(AUDITED_TABLES)

# Tables carrying an updated_at, maintained by the update trigger below.
TOUCHED_TABLES = tuple(AUDITED_TABLES)


def _json_of(alias, columns):
    """A json_object() call over one row of a trigger, OLD or NEW."""
    pairs = ", ".join(f"'{column}', {alias}.{column}" for column in columns)
    return f"json_object({pairs})"


def audit_triggers(table, columns):
    """The three triggers that record every change to one table.

    A row's owner is normally its user_id. The users table has no such column
    - a user is their own owner - so there the row's own id is recorded
    instead.

    The update trigger also advances updated_at, rather than leaving that to a
    separate trigger. Two triggers on the same UPDATE means the second fires
    again on the first one's write - measured, that produced two audit entries
    for every edit. One trigger cannot re-fire itself while recursive_triggers
    is off, which is SQLite's default, so a single logical change records
    exactly one entry.
    """
    owner = "id" if table in SELF_OWNED else "user_id"
    new_json = _json_of("NEW", columns)
    old_json = _json_of("OLD", columns)
    return f"""
CREATE TRIGGER IF NOT EXISTS audit_{table}_insert AFTER INSERT ON {table}
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, entity, entity_id, action, before_json, after_json)
    VALUES (NEW.{owner}, '{table}', NEW.id, 'create', NULL, {new_json});
END;

CREATE TRIGGER IF NOT EXISTS audit_{table}_update AFTER UPDATE ON {table}
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, entity, entity_id, action, before_json, after_json)
    VALUES (NEW.{owner}, '{table}', NEW.id, 'update', {old_json}, {new_json});
    UPDATE {table} SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS audit_{table}_delete AFTER DELETE ON {table}
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, entity, entity_id, action, before_json, after_json)
    VALUES (OLD.{owner}, '{table}', OLD.id, 'delete', {old_json}, NULL);
END;
"""


def all_audit_triggers(connection=None):
    """Every audit trigger, as one script.

    Given a connection, only tables that actually exist are included. The
    table list always describes the current version, so a migration replaying
    an older step would otherwise build a trigger on a table several versions
    away and fail. Called without one, every trigger is produced - which is
    what a fresh database wants.
    """

    def usable(table, columns):
        """Whether this table exists with every column the trigger reads."""
        if connection is None:
            return True
        found = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not found:
            return False
        # A column added in a later version means the trigger cannot be built
        # yet, even though the table itself is already there.
        return set(columns).issubset(found)

    return "".join(
        audit_triggers(table, columns)
        for table, columns in AUDITED_TABLES.items()
        if usable(table, columns)
    )


def _migration_4(connection):
    """Timestamp triggers. Superseded by migration 5, which folds them in."""
    return


def _migration_5(connection):
    """Record every change, and fold the timestamp bump into the same trigger.

    The standalone touch triggers from version 4 are dropped: leaving them
    beside the audit triggers would record two entries for every edit, the
    second describing nothing but the timestamp the first one caused.
    """
    for table in AUDITED_TABLES:
        connection.execute(f"DROP TRIGGER IF EXISTS touch_{table}")
    connection.executescript(all_audit_triggers(connection))


# Keyed by the version each step brings the database up to. A database created
# fresh gets the whole schema at SCHEMA_VERSION and skips these entirely.
def _migration_6(connection):
    """Add category rules.

    A rule belongs to its category: delete the category and the rule goes with
    it, because a rule pointing at nothing would silently stop working rather
    than announce itself. A subcategory is optional and merely detaches.
    """
    connection.executescript("""
CREATE TABLE IF NOT EXISTS category_rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern        TEXT    NOT NULL CHECK (length(trim(pattern)) > 0),
    pattern_key    TEXT    NOT NULL UNIQUE,
    category_id    INTEGER NOT NULL REFERENCES categories(id)    ON DELETE CASCADE,
    subcategory_id INTEGER          REFERENCES subcategories(id) ON DELETE SET NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rules_category ON category_rules(category_id);
""")
    connection.executescript(audit_triggers("category_rules", AUDITED_TABLES["category_rules"]))


# Tables whose UNIQUE constraint has to become per-user, and which therefore
# cannot be altered in place: SQLite can add a column but cannot change a
# constraint or drop the index behind one.
_REBUILT = {
    "accounts": (
        "id, user_id, name, name_key, kind, opening_cents, position, created_at, updated_at"
    ),
    "categories": "id, user_id, name, name_key, kind, created_at, updated_at",
    "subcategories": ("id, user_id, name, name_key, category_id, created_at, updated_at"),
    "category_rules": (
        "id, user_id, pattern, pattern_key, category_id, subcategory_id, created_at, updated_at"
    ),
}

# Tables that only need the column, having no name uniqueness to fix.
_EXTENDED = ("transactions", "recurring_rules", "budgets", "audit_log")


def _table_sql(table):
    """The CREATE TABLE statement for one table, taken from SCHEMA."""
    start = SCHEMA.index(f"CREATE TABLE {table} (")
    end = SCHEMA.index("\n);", start) + 3
    return SCHEMA[start:end]


def _migration_7(connection):
    """Give every row an owner.

    Four tables are rebuilt because their UNIQUE constraints must become
    per-user - two people must both be able to have a category called Ushqim.
    SQLite cannot alter a constraint, so those are copied into new tables. The
    other three only gain a column, which it can do in place.

    Everything happens in one transaction, and the caller checks the totals
    before and after. A migration that rebuilds four tables holding real money
    should have to prove it changed nothing.
    """
    existing = (
        connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()[0]
        else 0
    )

    if not existing:
        connection.executescript(_table_sql("users"))
        connection.execute(
            "INSERT INTO users (id, name, name_key) VALUES (1, ?, ?)",
            (DEFAULT_USER_NAME, DEFAULT_USER_NAME.casefold()),
        )

    # The triggers reference columns that are about to move; drop them all and
    # recreate from the current definitions once the tables are right.
    for table in AUDITED_TABLES:
        for action in ("insert", "update", "delete"):
            connection.execute(f"DROP TRIGGER IF EXISTS audit_{table}_{action}")

    for table in _EXTENDED:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if "user_id" not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        connection.execute(f"UPDATE {table} SET user_id = 1 WHERE user_id IS NULL")

    for table, columns in _REBUILT.items():
        old_columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if "user_id" in old_columns:
            continue
        carried = columns.replace("user_id, ", "").replace("id, ", "", 1)

        # Build the replacement under a temporary name, then drop the original
        # and rename into place. Renaming the original first would make every
        # foreign key follow it, and dropping it would then cascade - deleting
        # the subcategories, budgets and rules that pointed at it.
        connection.executescript(
            _table_sql(table).replace(f"CREATE TABLE {table} (", f"CREATE TABLE {table}_new (")
        )
        connection.execute(
            f"INSERT INTO {table}_new ({columns}) SELECT id, 1, {carried} FROM {table}"
        )
        connection.execute(f"DROP TABLE {table}")
        connection.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

    connection.executescript(all_audit_triggers(connection))

    # Only indexes whose table exists yet. SCHEMA always describes the current
    # version, so by the time a later migration adds a table this loop would
    # otherwise try to index one that is still several steps away.
    present = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for statement in SCHEMA.split(";"):
        if "CREATE INDEX" not in statement:
            continue
        match = re.search(r"\bON\s+(\w+)\s*\(", statement)
        if match and match.group(1) not in present:
            continue
        connection.execute(statement.strip().replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS"))


def _migration_8(connection):
    """Add sessions and password resets.

    Purely additive - two tables and two indexes, nothing rebuilt - so a
    database in daily use upgrades in place. Neither table is audited: a
    session is not the user's data, and recording every login would bury the
    financial history under noise. What the audit log does record is a
    password being changed or reset, which is the part worth keeping.
    """
    connection.executescript("""
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT    NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_resets_user   ON password_resets(user_id);
""")


def _migration_9(connection):
    """Add roles, and the first-run administrator credentials.

    Everyone who already exists becomes an administrator. They were the only
    users of a program that had no roles, so they had every power the program
    offered; taking it away on upgrade would lock people out of their own
    accounts.
    """
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "is_admin" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        connection.execute("UPDATE users SET is_admin = 1")
    if "must_change" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0")

    connection.executescript("""
CREATE TABLE IF NOT EXISTS admin_setup (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT    NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);
""")


def _migration_10(connection):
    """Record changes to user accounts.

    Renaming someone, granting or removing the role, and changing a password
    are the actions that reach across people; until now none of them was
    recorded. The password hash is deliberately not audited - only the moment
    it changed - so a superseded hash is never copied into a log that outlives
    it.
    """
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "password_set_at" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN password_set_at TEXT")
        connection.execute(
            "UPDATE users SET password_set_at = created_at WHERE password_hash IS NOT NULL"
        )
    connection.executescript(audit_triggers("users", AUDITED_TABLES["users"]))


MIGRATIONS = {
    4: _migration_4,
    5: _migration_5,
    6: _migration_6,
    7: _migration_7,
    8: _migration_8,
    9: _migration_9,
    10: _migration_10,
}


def create_schema(connection):
    """Create every table, index and trigger, and record the schema version."""
    connection.executescript(SCHEMA)
    connection.executescript(all_audit_triggers())
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def migrate(connection, from_version):
    """Bring an existing database up to SCHEMA_VERSION, one step at a time."""
    for version in sorted(MIGRATIONS):
        if version > from_version:
            MIGRATIONS[version](connection)
            connection.execute(f"PRAGMA user_version = {int(version)}")
