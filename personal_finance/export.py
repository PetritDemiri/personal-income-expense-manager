"""Eksportimi ne CSV / CSV export.

Writes transactions to a CSV file for use elsewhere - a spreadsheet, an
accountant, a backup. One direction only: this is not a storage backend and
never reads.

Four decisions worth knowing about, all of them about the file being opened by
a person in a spreadsheet rather than by this program:

Headers follow the interface language, because the reader is a human. Stored
values stay as they are - only the column titles and the type labels are
translated.

Amounts are written as plain decimals with no currency symbol, so a spreadsheet
parses them as numbers rather than text. They stay positive, with the type in
its own column, exactly as the program models them. A signed column would sum
neatly but would misrepresent transfers, which are neither income nor spending.

The file is written as UTF-8 with a byte order mark. Without it Excel assumes
the system code page and mangles every ë and ç.

The delimiter is configurable. A comma is the default, but spreadsheets in
locales that use a comma for decimals expect a semicolon, and getting this
wrong puts the whole row in one cell.
"""

import csv
import os
import tempfile

from .config import CURRENCY_SYMBOL, DEFAULT_CATEGORY, TRANSFER
from .i18n import t, type_label

DEFAULT_DELIMITER = ","

# Delimiters that make sense for a spreadsheet. Anything else is almost
# certainly a mistake rather than a preference.
ALLOWED_DELIMITERS = (",", ";", "\t", "|")


def column_titles():
    """Header row, in the active interface language."""
    return [
        t("field_date"),
        t("field_type"),
        t("field_description"),
        t("field_category"),
        t("field_subcategory"),
        t("field_account"),
        t("field_destination"),
        f"{t('field_amount')} ({CURRENCY_SYMBOL})",
    ]


def transaction_row(transaction):
    """One transaction as a list of cell values.

    Empty fields are written empty rather than as the "no category" style
    labels used on screen. A blank cell is what a spreadsheet expects; a
    placeholder word would be counted as a real value by anything grouping the
    column. That includes the stored category sentinel, which is a placeholder
    held in the database rather than a category the user chose.
    """
    category = "" if transaction.kategoria == DEFAULT_CATEGORY else transaction.kategoria
    return [
        transaction.data,
        type_label(transaction.lloji),
        transaction.pershkrimi,
        category,
        transaction.nenkategoria,
        transaction.llogaria,
        transaction.llogaria_dest if transaction.lloji == TRANSFER else "",
        f"{transaction.shuma:.2f}",
    ]


def export_transactions(path, transactions, delimiter=DEFAULT_DELIMITER):
    """Write transactions to a CSV file. Returns the number of rows written.

    Written atomically, for the same reason saves are: a half-written export
    that silently replaced a good one would be worse than no export at all.
    """
    if delimiter not in ALLOWED_DELIMITERS:
        raise ValueError("ndares i pavlefshem")

    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        # utf-8-sig writes the byte order mark Excel needs to read UTF-8.
        encoding="utf-8-sig",
        dir=directory,
        prefix=".tmp-export-",
        suffix=".csv",
        delete=False,
    )
    temp_path = handle.name
    try:
        with handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerow(column_titles())
            count = 0
            for transaction in transactions:
                writer.writerow(transaction_row(transaction))
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    return count
