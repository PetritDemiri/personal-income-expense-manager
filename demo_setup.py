"""Stage a database for the first-run recording.

The setup screen is worth showing: it is the most distinctive thing the program
does, and the boxes filling as a code is typed only make sense on camera. But a
recording types fixed keystrokes, and the generated password is different every
time, so the two cannot meet without arranging it.

This creates the same state `create_admin` does - an unclaimed database, an
administrator who must change their password, and the credentials file - using
a password chosen here rather than a random one. Nothing about how the program
then behaves is changed: it checks the password, counts the attempts and
expires the code exactly as it always would. The only difference is that the
recording knows what to type.

Used by demo-setup.tape. Not part of the program.
"""

import os
import sys

from personal_finance.app import FinanceApp
from personal_finance.auth import SETUP_MINUTES, _expiry, setup_file_path
from personal_finance.config import DATABASE_FILE, data_path
from personal_finance.locations import documents_directory
from personal_finance.passwords import format_code, hash_token, normalise_code

# Chosen rather than generated, and drawn from the same alphabet so it looks
# like every other one the program hands out.
PASSWORD = "HJ7KQ2M4XRTP"
NAME = "admin"


def main():
    path = data_path(DATABASE_FILE)
    app = FinanceApp(path=path, quiet=True)

    # An unclaimed database: no users, and no leftover state from a previous
    # recording.
    with app.db.connection as conn:
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM admin_setup")

    with app.db.connection as conn:
        cursor = conn.execute(
            "INSERT INTO users (name, name_key, is_admin, must_change) VALUES (?, ?, 1, 1)",
            (NAME, NAME.casefold()),
        )
        conn.execute(
            "INSERT INTO admin_setup (user_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (
                cursor.lastrowid,
                hash_token(normalise_code(PASSWORD)),
                _expiry(minutes=SETUP_MINUTES),
            ),
        )
    app.close()

    directory = documents_directory()
    os.makedirs(directory, exist_ok=True)
    with open(setup_file_path(directory), "w", encoding="utf-8") as handle:
        handle.write(
            f"{NAME}\n{format_code(PASSWORD)}\n\n"
            f"Ky fjalekalim skadon pas {SETUP_MINUTES} minutash.\n"
            f"This password expires in {SETUP_MINUTES} minutes.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
