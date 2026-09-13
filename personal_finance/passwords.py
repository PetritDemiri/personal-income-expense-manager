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
import re
import secrets

ALGORITHM = "pbkdf2_sha256"

# Raised over time. Stored per hash, so old passwords keep working at the count
# they were created with and only new ones pay the higher cost.
ITERATIONS = 600_000

SALT_BYTES = 16


# Requirements for a new password. Applied when one is set or changed, never
# retroactively - a rule introduced later must not lock anyone out of their own
# data on upgrade.
MIN_LENGTH = 8

# Characters a one-time code is built from. O, 0, I, 1 and L are left out
# because they are the pairs people misread when copying a code by hand.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_GROUPS = 3
CODE_GROUP_SIZE = 3
CODE_LENGTH = CODE_GROUPS * CODE_GROUP_SIZE

# The password generated when an empty database is first opened. Longer than
# a reset code because it is a password rather than a one-time confirmation,
# and still built from the same unambiguous alphabet because it is read off a
# screen and typed by hand.
SETUP_GROUPS = 4
SETUP_LENGTH = SETUP_GROUPS * CODE_GROUP_SIZE

# The generated administrator's name. A fixed prefix so it is recognisable,
# with a short random tail so two databases do not end up with the same one.
ADMIN_PREFIX = "admin"


def password_problems(password):
    """Every requirement a password fails, as a list of keys.

    Returns keys rather than sentences so the caller can translate them, and
    all of them rather than the first, so someone is told everything at once
    instead of discovering the rules one rejection at a time.
    """
    problems = []
    if not password or len(password) < MIN_LENGTH:
        problems.append("password_too_short")
    if not any(character.isupper() for character in password or ""):
        problems.append("password_needs_upper")
    if not any(character.isdigit() for character in password or ""):
        problems.append("password_needs_digit")
    return problems


def is_acceptable(password):
    return not password_problems(password)


def generate_code():
    """A one-time code: nine characters, no separator.

    Drawn from an alphabet without O/0 or I/1/L because it is read off a
    screen and typed by hand, and a misread character costs one of only three
    attempts. Stored and compared without separators; the grouping is a
    display concern, applied by `format_code`.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def generate_setup_password():
    """The password generated for a brand-new database's administrator."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(SETUP_LENGTH))


def admin_name(taken=()):
    """The name for a generated administrator.

    Plainly "admin". The database is empty when one is created, so there is
    nothing to collide with, and a name the person has to read off a file and
    type back should be the obvious one rather than a string of characters
    they have to transcribe. A numbered suffix is only ever reached if a name
    somehow exists already, which the empty case rules out.
    """
    lowered = {str(name).casefold() for name in taken}
    if ADMIN_PREFIX.casefold() not in lowered:
        return ADMIN_PREFIX
    suffix = 2
    while f"{ADMIN_PREFIX}{suffix}".casefold() in lowered:
        suffix += 1
    return f"{ADMIN_PREFIX}{suffix}"


def generate_password(length=12):
    """A password strong enough to be temporary, and valid by our own rules.

    Built to contain a capital and a digit by construction rather than by
    luck, so a generated password can never be rejected by the very check it
    will be measured against.
    """
    upper = "ABCDEFGHJKMNPQRSTUVWXYZ"
    lower = "abcdefghijkmnpqrstuvwxyz"
    digits = "23456789"
    pool = upper + lower + digits

    characters = [
        secrets.choice(upper),
        secrets.choice(digits),
        *(secrets.choice(pool) for _ in range(max(0, length - 2))),
    ]
    # Shuffled so the capital and digit are not always in the same places.
    for index in range(len(characters) - 1, 0, -1):
        swap = secrets.randbelow(index + 1)
        characters[index], characters[swap] = characters[swap], characters[index]
    return "".join(characters)


def format_code(code):
    """A code split into groups for reading: K7M Q2X 9RT."""
    text = code or ""
    return " ".join(text[i : i + CODE_GROUP_SIZE] for i in range(0, len(text), CODE_GROUP_SIZE))


def normalise_code(text):
    """A typed code, with separators and surrounding space removed.

    Case is preserved: a code is uppercase as generated and must be typed
    that way. What is discarded is only the grouping - spaces or dashes a
    person might add - and whitespace around the whole thing, none of which
    is part of the code.
    """
    return re.sub(r"[\s-]", "", text or "")


def hash_token(token):
    """A session token or reset code, hashed for storage.

    Stored hashed so the database never holds a usable one. These are short
    lived and high entropy, so a single fast hash is right - the slow
    derivation used for passwords would add latency to every command for no
    gain against a random 128-bit token.
    """
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def tokens_match(candidate, stored):
    return hmac.compare_digest(hash_token(candidate), stored or "")


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
