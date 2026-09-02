"""Fjalekalimet / Password hashing.

Passwords are stored as a PBKDF2-HMAC-SHA256 hash with a random salt, never as
text and never reversibly. The iteration count is stored beside each hash, so
it can be raised for new passwords without invalidating the ones already set.

Argon2 would be the better algorithm and is what this would use in production.
It needs a third-party package, and this project has had no runtime dependency
since version 1; PBKDF2 with a high iteration count is the right answer under
that constraint and is still what a great many systems use.

The command line never asks for a password. Anyone who can run the program can
also open the database file directly, so a prompt there would add friction
while protecting nothing - the file's own permissions are the boundary. What
the hash exists for is the web interface, where a password is the only thing
between a stranger and someone's finances.
"""

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"

# Raised over time. Stored per hash, so old passwords keep working at the count
# they were created with and only new ones pay the higher cost.
ITERATIONS = 600_000

SALT_BYTES = 16


def hash_password(password, iterations=ITERATIONS, salt=None):
    """Hash a password. Returns (hash_hex, salt_hex, iterations).

    A fresh random salt per password, so two people choosing the same one do
    not end up with the same hash.
    """
    if not password:
        raise ValueError("fjalekalimi nuk mund te jete bosh")
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return digest.hex(), salt_bytes.hex(), iterations


def verify_password(password, stored_hash, salt, iterations):
    """Whether a password matches a stored hash.

    Compared with `compare_digest`, which takes the same time whether the
    first byte differs or the last. A plain `==` leaks how much of a guess was
    correct through how long the comparison took.
    """
    if not password or not stored_hash or not salt:
        return False
    try:
        candidate, _, _ = hash_password(password, iterations=iterations, salt=salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, stored_hash)


def needs_rehash(iterations):
    """Whether a stored password was hashed at a lower cost than current.

    The web interface can use this to upgrade a hash silently, at the one
    moment it holds the plain password: a successful login.
    """
    return int(iterations or 0) < ITERATIONS
