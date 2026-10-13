"""Konfigurimi / Configuration.

Every tunable value lives here so the rest of the package never hard-codes a
filename, a symbol, or a transaction type.
"""

import os

# ---------------------------------------------------------------------------
# Canonical transaction types
# ---------------------------------------------------------------------------
# These are the values written to and read from the CSV files. They stay in
# Albanian so that existing data files keep working unchanged.
#
# They are defined once, here, rather than repeated as literals across the
# package: every module and every test compares against the same object, so a
# typo becomes an ImportError instead of a silently wrong total.
#
# The *displayed* label is a separate concern - see i18n.type_label() - which
# is what allows an English interface without touching stored data.
INCOME = "Te Ardhura"
EXPENSE = "Shpenzime"
# A movement between two of the user's own accounts. Neither income nor an
# expense: the money never leaves, so it must never reach either total.
TRANSFER = "Transferim"

TRANSACTION_TYPES = (INCOME, EXPENSE, TRANSFER)

# The two types a user picks between when adding an ordinary transaction.
# Transfers are created through their own flow, which needs two accounts.
ENTRY_TYPES = (INCOME, EXPENSE)

# Values written by much older versions of the program, mapped onto the
# canonical ones when a file is loaded.
LEGACY_TYPE_ALIASES = {
    "income": INCOME,
    "expense": EXPENSE,
    "te ardhura": INCOME,
    "shpenzime": EXPENSE,
    "transfer": TRANSFER,
    "transferim": TRANSFER,
}

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
# The database lives in Documents\Financat\Te dhenat. Every version before
# 3.10.0 kept it in whichever folder the program was started from, which for a
# double-clicked program or a shortcut depends on how it was opened - so the
# data could seem to vanish. FINANCE_DATA_DIR still overrides it, which is how
# the tests and the demo recordings stay away from anyone's real data.
DATA_DIR_ENV = "FINANCE_DATA_DIR"

DATABASE_FILE = "finance.db"

TRANSACTIONS_FILE = "transactions.csv"
RECURRING_FILE = "recurring.csv"
BUDGETS_FILE = "budgets.csv"
ACCOUNTS_FILE = "accounts.csv"


def data_directory():
    """Where the database is kept: FINANCE_DATA_DIR, or Documents\\Financat\\Te dhenat."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return override
    from .locations import DATA_FOLDER, app_subdirectory

    return app_subdirectory(DATA_FOLDER)


def data_path(filename):
    """Full path to a data file inside the configured data directory."""
    return os.path.join(data_directory(), filename)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
CURRENCY_SYMBOL = "€"
DATE_FORMAT = "%d-%m-%Y"
MONTH_FORMAT = "%m-%Y"

DEFAULT_CATEGORY = "Pa kategori"

# The catch-all category. Kept last in every suggestion list, no matter how
# many categories the user adds of their own - a list that ends in "other"
# reads correctly, one that ends in a specific category does not.
OTHER_CATEGORY = "Te tjera"

# Typed at an edit prompt to clear an existing subcategory or account, since
# pressing Enter there means "leave unchanged". Purely an input key - the empty
# state is displayed as readable text, not as a dash.
CLEAR_MARKER = "-"

# ---------------------------------------------------------------------------
# Suggested categories offered when adding a transaction. The user can always
# type something else; anything already used in the data is suggested too.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Suggested subcategories, keyed by category. Subcategories are optional: a
# transaction can sit directly in its category with none at all.
#
# A category missing from this table simply has no suggestions - the user can
# still type a subcategory for it, and it will be remembered and suggested
# from then on.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
# Accounts are optional. With none defined the program behaves exactly as it
# did before: no account prompt, no account column, one combined balance.
CASH = "Kesh"
BANK = "Banke"
CARD = "Karte"

ACCOUNT_TYPES = (CASH, BANK, CARD)

# Fraction of a budget at which a warning is shown before it is exceeded.
BUDGET_WARNING_THRESHOLD = 0.8
