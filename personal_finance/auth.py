"""Hyrja / Authentication.

Sessions and password resets. The command line asks for a password only from a
user who has set one, so a single-person installation never sees any of this.

What this is for, stated plainly: on a shared machine it keeps one person from
casually reading another's finances. It is not protection against someone with
the database file, who can open it in any SQLite browser regardless. The
mechanism is here because the web interface will need exactly this, and
building it against the command line proves it works before anything depends
on it.

Sessions exist so a password does not make the program unscriptable. Log in
once and every command works for twelve hours; a script running inside that
window is never prompted.
"""

import datetime
import os
import sqlite3
import stat

from .models import name_key
from .passwords import (
    admin_name,
    format_code,
    generate_code,
    generate_setup_password,
    hash_token,
    needs_rehash,
    normalise_code,
    tokens_match,
    verify_password,
)

# How long a login lasts. Long enough for a working day, short enough that a
# machine left alone overnight is not still open in the morning.
SESSION_HOURS = 12

# How long a reset code is good for, and how many guesses it allows. A wrong
# code costs one of three; the fourth cancels the reset entirely.
RESET_MINUTES = 5
RESET_ATTEMPTS = 3

SESSION_FILE = ".session"


def _now():
    return datetime.datetime.now()


def _stamp(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _expiry(**delta):
    return _stamp(_now() + datetime.timedelta(**delta))


def _expired(stamp):
    try:
        return datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S") < _now()
    except (ValueError, TypeError):
        return True


def _own_only(path):
    """Restrict a file to its owner, where the platform supports it.

    Windows ignores these bits; there it is the account's own profile
    directory doing the work instead.
    """
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# The first run of an empty database
# ---------------------------------------------------------------------------

SETUP_MINUTES = 5
SETUP_ATTEMPTS = 3


# Written into the credentials file in both languages, since the file is read
# before anyone has chosen one.
UPPERCASE_WARNING_SQ = "Kujdes: fjalekalimi duhet te shkruhet i gjithi me shkronja te medha."
UPPERCASE_WARNING_EN = "Warning: the password should be typed in all uppercase letters."


def setup_file_path(directory):
    return os.path.join(directory, "administratori.txt")


def needs_setup(db):
    """Whether this database has nobody in it yet."""
    return db.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def pending_setup(db):
    """The administrator awaiting their generated credentials, or None."""
    row = db.connection.execute(
        "SELECT s.*, u.name FROM admin_setup s JOIN users u ON u.id = s.user_id "
        "WHERE s.used = 0 ORDER BY s.id DESC LIMIT 1"
    ).fetchone()
    return row


def create_admin(db, directory):
    """Generate the first administrator and write the credentials to a file.

    Returns (name, password, path). The account exists but cannot be used for
    anything until the generated password has been replaced, which is what
    `must_change` records.
    """
    taken = [row[0] for row in db.connection.execute("SELECT name FROM users")]
    name = admin_name(taken)
    password = generate_setup_password()

    with db.connection as conn:
        cursor = conn.execute(
            "INSERT INTO users (name, name_key, is_admin, must_change) VALUES (?, ?, 1, 1)",
            (name, name.casefold()),
        )
        user_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO admin_setup (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, hash_token(password), _expiry(minutes=SETUP_MINUTES)),
        )

    os.makedirs(directory, exist_ok=True)
    path = setup_file_path(directory)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            f"{name}\n{format_code(password)}\n\n"
            f"Ky fjalekalim skadon pas {SETUP_MINUTES} minutash.\n"
            f"This password expires in {SETUP_MINUTES} minutes.\n\n"
            # The boxes it is typed into accept only capitals and digits, so a
            # lowercase letter does nothing at all - which looks, to someone
            # who does not know that, like the program has frozen.
            f"{UPPERCASE_WARNING_SQ}\n"
            f"{UPPERCASE_WARNING_EN}\n"
        )
    _own_only(path)
    return name, password, path


def discard_setup(db):
    """Throw away an unused set of generated credentials and its account.

    Safe because the database is empty at this point: an expired or exhausted
    setup leaves nothing behind worth keeping, and the next run generates
    fresh credentials rather than leaving anyone locked out of a file with
    nothing in it.
    """
    row = pending_setup(db)
    if row is None:
        return
    with db.connection as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (row["user_id"],))


def unclaimed_admins(connection):
    """Generated administrators nobody has finished claiming.

    Counted by the setup row that complete_setup removes, rather than by
    whether the code has been typed: a setup abandoned after the right code
    but before a name and password were chosen leaves an administrator with no
    password on it, and that is no more claimed than one whose code was never
    typed at all. A user with a password is never counted, whatever else is
    true of it.
    """
    rows = connection.execute(
        "SELECT DISTINCT s.user_id FROM admin_setup s JOIN users u ON u.id = s.user_id "
        "WHERE u.password_hash IS NULL"
    ).fetchall()
    return [row[0] for row in rows]


def forget_setup(connection, directory):
    """Discard any first-run code nobody claimed, and delete its file.

    A code lives only while the program that showed it is open. Keeping one
    until it expired let closing and reopening leave a stale file - or a copy
    of it still open in an editor - showing a code that no longer worked; and
    a setup abandoned halfway left an administrator with no password, which
    every later run walked straight into. Run when the program closes, and
    again before a setup starts, so a run that was killed outright cannot
    leave anything usable behind either.

    The file is removed whether or not a code was pending: once the program
    has closed, no copy of it is ever the right one to read.
    """
    with connection:
        for user_id in unclaimed_admins(connection):
            # Removed explicitly as well as by the cascade, which depends on a
            # pragma that every new connection starts with switched off.
            connection.execute("DELETE FROM admin_setup WHERE user_id = ?", (user_id,))
            # Before 3.10.0 a setup abandoned after the right code let the
            # next run straight in as this administrator, and someone may have
            # used it since. Their data is kept, and the account with it; only
            # the stale code goes. An account that owns nothing is just the
            # unfinished setup, and is removed so the next one starts clean.
            if not owns_anything(connection, user_id):
                connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    try:
        os.unlink(setup_file_path(directory))
    except OSError:
        pass


# Tables that hold the sign-in machinery and the log of changes rather than
# anything a person made. Every other table with a user_id is that person's
# own, including any added later - the safe default for a check whose other
# answer is deleting an account.
_NOT_BELONGINGS = frozenset(
    {"admin_setup", "audit_log", "password_resets", "preferences", "sessions"}
)


def owns_anything(connection, user_id):
    """Whether a user has any data of their own - an account, a transaction..."""
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (table,) in tables:
        if table in _NOT_BELONGINGS:
            continue
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        if "user_id" not in columns:
            continue
        found = connection.execute(
            f'SELECT 1 FROM "{table}" WHERE user_id = ? LIMIT 1', (user_id,)
        ).fetchone()
        if found:
            return True
    return False


def forget_setup_at(database_path, directory):
    """forget_setup through a connection of its own.

    For the window being closed on Windows, where the cleanup runs on a thread
    of its own and the program's connection cannot be used from there. Any
    failure is swallowed: the window is going either way, and the next launch
    clears whatever this could not.
    """
    try:
        if os.path.exists(database_path):
            connection = sqlite3.connect(database_path, timeout=3)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                forget_setup(connection, directory)
            finally:
                connection.close()
        else:
            os.unlink(setup_file_path(directory))
    except (sqlite3.Error, OSError):
        pass


def check_setup_password(db, typed):
    """Check the generated password. Returns (outcome, attempts_left)."""
    row = pending_setup(db)
    if row is None:
        return ResetOutcome.NONE, 0

    if _expired(row["expires_at"]):
        discard_setup(db)
        return ResetOutcome.EXPIRED, 0

    if tokens_match(normalise_code(typed), row["code_hash"]):
        with db.connection as conn:
            conn.execute("UPDATE admin_setup SET used = 1 WHERE id = ?", (row["id"],))
        return ResetOutcome.OK, 0

    attempts = row["attempts"] + 1
    if attempts >= SETUP_ATTEMPTS:
        discard_setup(db)
        return ResetOutcome.EXHAUSTED, 0

    with db.connection as conn:
        conn.execute("UPDATE admin_setup SET attempts = ? WHERE id = ?", (attempts, row["id"]))
    return ResetOutcome.WRONG, SETUP_ATTEMPTS - attempts


def complete_setup(db, user_id, name, password, setup_file=None):
    """Replace the generated credentials with the ones the person chooses."""
    with db.connection as conn:
        conn.execute(
            "UPDATE users SET name = ?, name_key = ?, must_change = 0 WHERE id = ?",
            (name, name_key(name), user_id),
        )
        conn.execute("DELETE FROM admin_setup WHERE user_id = ?", (user_id,))
    db.set_password(user_id, password)
    if setup_file:
        try:
            os.unlink(setup_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def session_path(database_path):
    """Where the session token is kept: beside the database it belongs to."""
    directory = os.path.dirname(os.path.abspath(database_path))
    return os.path.join(directory, SESSION_FILE)


def read_token(database_path):
    """The token from disk, or None."""
    try:
        with open(session_path(database_path), encoding="utf-8") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def write_token(database_path, token):
    path = session_path(database_path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(token)
    _own_only(path)


def clear_token(database_path):
    try:
        os.unlink(session_path(database_path))
    except OSError:
        pass


def start_session(db, user_id):
    """Record a new session and return its token.

    The token is returned once and stored only as a hash, so what is written
    to disk is the single usable copy and the database holds nothing that
    could be presented as a login.
    """
    import secrets

    token = secrets.token_urlsafe(32)
    with db.connection as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, hash_token(token), _expiry(hours=SESSION_HOURS)),
        )
    return token


def session_user(db, token):
    """The user a token belongs to, or None if it is unknown or expired."""
    if not token:
        return None
    row = db.connection.execute(
        "SELECT id, user_id, expires_at FROM sessions WHERE token_hash = ?",
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    if _expired(row["expires_at"]):
        end_session_by_id(db, row["id"])
        return None
    return row["user_id"]


def end_session(db, token):
    if not token:
        return
    with db.connection as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))


def end_session_by_id(db, session_id):
    with db.connection as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def end_sessions_for(db, user_id):
    """End every session a user has. Used when their password changes."""
    with db.connection as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def purge_expired(db):
    """Remove sessions that have run out, so the table does not grow forever."""
    with db.connection as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_stamp(_now()),))


# ---------------------------------------------------------------------------
# Logging in
# ---------------------------------------------------------------------------


def authenticate(db, user_id, password):
    """Check a password and upgrade its hash if the cost has since risen.

    A successful login is the one moment the plain password is in hand, so it
    is the only chance to rehash at the current iteration count without asking
    the user for anything.
    """
    user = db.user(user_id)
    if user is None or not user.has_password:
        return False
    if not verify_password(password, user.password_hash, user.password_salt, user.password_iters):
        return False
    if needs_rehash(user.password_iters):
        db.set_password(user_id, password)
    return True


# ---------------------------------------------------------------------------
# Resetting a forgotten password
# ---------------------------------------------------------------------------


def reset_file_path(directory, user_name):
    """Where the one-time code is written for the user to read."""
    safe = "".join(c for c in (user_name or "user") if c.isalnum()) or "user"
    return os.path.join(directory, f"kodi-{safe}.txt")


def begin_reset(db, user_id, directory, user_name):
    """Start a reset. Returns (code, path).

    Any reset already in progress for this user is discarded first, so
    requesting a new code invalidates the old one rather than leaving two
    live at once.
    """
    with db.connection as conn:
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))

    code = generate_code()
    with db.connection as conn:
        conn.execute(
            "INSERT INTO password_resets (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, hash_token(normalise_code(code)), _expiry(minutes=RESET_MINUTES)),
        )

    os.makedirs(directory, exist_ok=True)
    path = reset_file_path(directory, user_name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            f"{format_code(code)}\n\n"
            f"Ky kod skadon pas {RESET_MINUTES} minutash.\n"
            f"This code expires in {RESET_MINUTES} minutes.\n"
        )
    _own_only(path)
    return code, path


class ResetOutcome:
    """Why a reset code was accepted or refused."""

    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    NONE = "none"


def check_code(db, user_id, typed):
    """Check a reset code. Returns (outcome, attempts_left).

    A wrong code is counted. Once the attempts are used up the reset is
    discarded entirely, so guessing cannot continue past three tries by
    re-running the command.
    """
    row = db.connection.execute(
        "SELECT * FROM password_resets WHERE user_id = ? AND used = 0 ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return ResetOutcome.NONE, 0

    if _expired(row["expires_at"]):
        _discard_reset(db, row["id"])
        return ResetOutcome.EXPIRED, 0

    if tokens_match(normalise_code(typed), row["code_hash"]):
        with db.connection as conn:
            conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (row["id"],))
        return ResetOutcome.OK, 0

    attempts = row["attempts"] + 1
    if attempts >= RESET_ATTEMPTS:
        _discard_reset(db, row["id"])
        return ResetOutcome.EXHAUSTED, 0

    with db.connection as conn:
        conn.execute(
            "UPDATE password_resets SET attempts = ? WHERE id = ?",
            (attempts, row["id"]),
        )
    return ResetOutcome.WRONG, RESET_ATTEMPTS - attempts


def _discard_reset(db, reset_id):
    with db.connection as conn:
        conn.execute("DELETE FROM password_resets WHERE id = ?", (reset_id,))


def finish_reset(db, user_id, new_password, code_file=None):
    """Set the new password, end every session, and delete the code file.

    Existing sessions are ended because a password change should not leave a
    login granted under the old one still working.
    """
    db.set_password(user_id, new_password)
    end_sessions_for(db, user_id)
    with db.connection as conn:
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
    if code_file:
        try:
            os.unlink(code_file)
        except OSError:
            pass


def change_password(db, user_id, current, new_password):
    """Change a password, requiring the current one when there is one.

    Without that check anyone at the keyboard could take over an account they
    are already looking at, which would make the whole feature decorative.
    """
    user = db.user(user_id)
    if user is None:
        return False
    if user.has_password and not verify_password(
        current, user.password_hash, user.password_salt, user.password_iters
    ):
        return False
    db.set_password(user_id, new_password)
    end_sessions_for(db, user_id)
    return True
