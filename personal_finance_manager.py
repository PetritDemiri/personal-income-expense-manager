#!/usr/bin/env python3
"""Menaxheri i te Ardhurave dhe Shpenzimeve Personale.

Nje aplikacion konsole per te mbajtur shenim te ardhurat dhe shpenzimet
personale. Te dhenat ruhen ne skedare CSV lokale.
"""

import argparse
import calendar
import csv
import datetime
import os
import sys
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# File for saving transactions
CSV_FILE = 'transactions.csv'

# File for saving recurring transaction rules
RECURRING_FILE = 'recurring.csv'

# Currency symbol used for all displayed amounts
CURRENCY_SYMBOL = '€'

# Date format used everywhere (dita-muaji-viti)
DATE_FORMAT = '%d-%m-%Y'

# Category used for transactions that have none (e.g. rows from older files)
DEFAULT_CATEGORY = 'Pa kategori'

# Suggested categories, offered as a numbered list when adding a transaction.
# The user can always type a category that is not on the list.
SUGGESTED_CATEGORIES = {
    'Te Ardhura': ['Paga', 'Bonus', 'Dhurate', 'Investime', 'Te tjera'],
    'Shpenzime': ['Ushqim', 'Qera', 'Transport', 'Fatura', 'Argetim',
                  'Shendetesi', 'Veshje', 'Te tjera'],
}

# List to store transactions
transactions = []

# List to store recurring transaction rules
recurring_rules = []


# ---------------------------------------------------------------------------
# Colors (ANSI colors)
# ---------------------------------------------------------------------------

# ANSI escape codes. Empty strings are substituted when colors are disabled, so the rest of the code never has to care whether colors are on or off.

GREEN = '\033[32m'
RED = '\033[31m'
CYAN = '\033[36m'
YELLOW = '\033[33m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

COLORS_ENABLED = False


def detect_color_support():
    """Return True if it looks safe to print ANSI colors to stdout.

    Colors are disabled when output is redirected to a file or a pipe, when
    NO_COLOR is set (see no-color.org), or when the terminal is unknown.
    """
    if os.environ.get('NO_COLOR') is not None:
        return False
    if os.environ.get('FORCE_COLOR') is not None:
        return True
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    if os.environ.get('TERM') == 'dumb':
        return False
    if sys.platform == 'win32':
        # Modern Windows terminals support ANSI, but virtual terminal
        # processing has to be enabled first. If that fails, skip colors.
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # -11 = STD_OUTPUT_HANDLE, 7 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
            # combined with the default output mode flags.
            return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
        except Exception:
            return False
    return True


def paint(text, *styles):
    """Wrap text in ANSI styles, or return it unchanged if colors are off.

    Always pad/align text BEFORE calling this. ANSI codes are invisible on
    screen but still count as characters, so colorizing first would break
    every column width in the tables below.
    """
    if not COLORS_ENABLED or not styles:
        return text
    return f"{''.join(styles)}{text}{RESET}"


def color_for_type(trans_type):
    """Green for income, red for expenses."""
    return GREEN if trans_type == 'Te Ardhura' else RED


# ---------------------------------------------------------------------------
# Help with dates
# ---------------------------------------------------------------------------

def get_current_date():
    """Get current date as string"""
    return datetime.datetime.now().strftime(DATE_FORMAT)


def parse_date(date_str):
    """Parse a dd-mm-yyyy string into a date object, or None if invalid."""
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(date_str.strip(), DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None


def format_date(date_obj):
    """Format a date object back into a dd-mm-yyyy string."""
    return date_obj.strftime(DATE_FORMAT)


def add_months(start_date, months):
    """Return start_date shifted forward by a number of months.

    The day is clamped to the last valid day of the target month, so a rule
    anchored on the 31st still fires on 28/29 February. Because every
    occurrence is computed from the original start date rather than from the
    previous occurrence, clamping never causes the day to drift permanently.
    """
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


# Recurrence frequencies. Each entry maps a name to a function that returns the k-th occurrence counted from the start date (k=0 is the start date itself). Adding a new frequency later is a one-line change here.
FREQUENCIES = {
    'mujore': lambda start, k: add_months(start, k),
    'javore': lambda start, k: start + datetime.timedelta(weeks=k),
    'vjetore': lambda start, k: add_months(start, 12 * k),
}


# ---------------------------------------------------------------------------
# Leximi dhe ruajtja e transaksioneve
# ---------------------------------------------------------------------------

def load_transactions():
    """Load transactions from CSV file if it exists, skipping any corrupted rows.

    Files written by earlier versions had no 'kategoria' column. Those rows
    load fine and are given the default category; the column is added back the
    next time the file is saved.
    """
    global transactions
    transactions = []
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                skipped = 0
                for row in reader:
                    try:
                        row['shuma'] = Decimal(row['shuma'])
                        # Older files have no category column at all.
                        if not row.get('kategoria'):
                            row['kategoria'] = DEFAULT_CATEGORY
                        transactions.append(row)
                    except (InvalidOperation, KeyError, TypeError):
                        skipped += 1
            print(f"Jane lexuar {len(transactions)} transaksione nga {CSV_FILE}")
            if skipped:
                print(paint(f"Kujdes: {skipped} rreshta te demtuar u anashkaluan.",
                            YELLOW))
        except Exception as e:
            print(paint(f"Ka ndodhur nje gabim ne leximin e transaksioneve: {e}", RED))
            transactions = []


def save_transactions(quiet=False):
    """Save transactions to CSV file."""
    try:
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as file:
            fieldnames = ['lloji', 'pershkrimi', 'shuma', 'data', 'kategoria']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(transactions)
        if not quiet:
            print(f"Jane ruajtur {len(transactions)} transaksione ne {CSV_FILE}")
    except Exception as e:
        print(paint(f"Ka ndodhur nje gabim ne ruajtjen e transaksione: {e}", RED))


def load_recurring():
    """Load recurring transaction rules, skipping any corrupted rows."""
    global recurring_rules
    recurring_rules = []
    if os.path.exists(RECURRING_FILE):
        try:
            with open(RECURRING_FILE, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                skipped = 0
                for row in reader:
                    try:
                        row['shuma'] = Decimal(row['shuma'])
                        if not row.get('kategoria'):
                            row['kategoria'] = DEFAULT_CATEGORY
                        if row.get('frekuenca') not in FREQUENCIES:
                            raise ValueError('frekuence e panjohur')
                        if parse_date(row.get('data_fillimit')) is None:
                            raise ValueError('date fillimi e pavlefshme')
                        recurring_rules.append(row)
                    except (InvalidOperation, KeyError, TypeError, ValueError):
                        skipped += 1
            if skipped:
                print(paint(f"Kujdes: {skipped} rregulla te perseritura te demtuara "
                            f"u anashkaluan.", YELLOW))
        except Exception as e:
            print(paint(f"Ka ndodhur nje gabim ne leximin e perseritjeve: {e}", RED))
            recurring_rules = []


def save_recurring(quiet=False):
    """Save recurring transaction rules to CSV file."""
    try:
        with open(RECURRING_FILE, mode='w', newline='', encoding='utf-8') as file:
            fieldnames = ['lloji', 'pershkrimi', 'shuma', 'kategoria',
                          'frekuenca', 'data_fillimit', 'data_e_fundit']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recurring_rules)
        if not quiet:
            print(f"Jane ruajtur {len(recurring_rules)} perseritje ne {RECURRING_FILE}")
    except Exception as e:
        print(paint(f"Ka ndodhur nje gabim ne ruajtjen e perseritjeve: {e}", RED))


# ---------------------------------------------------------------------------
# Questions and validation (shared between adding and modifying)
# ---------------------------------------------------------------------------

def prompt_description(current=None):
    """Ask for a description. Returns None if the user cancels."""
    while True:
        if current is None:
            value = input("Vendosni pershkrimin: ").strip()
        else:
            value = input(f"Pershkrimi [{current}]: ").strip()
            if not value:
                return current
        if value:
            return value
        print(paint("Pershkrimi nuk mund te jete i zbrazet.", RED))


def validate_amount(amount_str):
    """Convert a string to a non-negative Decimal, or None if invalid."""
    try:
        amount = Decimal(amount_str.strip())
    except (InvalidOperation, AttributeError):
        return None
    if amount < 0:
        return None
    return amount


def prompt_amount(current=None):
    """Ask for an amount, validating it the same way everywhere."""
    while True:
        if current is None:
            raw = input("Vendosni shumen: ").strip()
        else:
            raw = input(f"Shuma [{current:.2f}]: ").strip()
            if not raw:
                return current
        amount = validate_amount(raw)
        if amount is None:
            print(paint("Shuma eshte e pavlefshme. Ju lutem, vendosni nje numer "
                        "pozitiv.", RED))
            continue
        return amount


def prompt_date(current=None):
    """Ask for a date, offering today's date as a shortcut."""
    if current is None:
        while True:
            choice = input("Te perdoret data e tanishme? (po/jo): ").strip().lower()
            if choice == "po":
                return get_current_date()
            if choice == "jo":
                break
            print(paint("Ju lutem shkruani vetem 'po' ose 'jo'.", RED))

    while True:
        if current is None:
            raw = input("Vendosni daten ( dite-muaj-Vit ): ").strip()
        else:
            raw = input(f"Data [{current}] (Enter = pa ndryshim): ").strip()
            if not raw:
                return current
        if parse_date(raw) is not None:
            return raw
        print(paint("Format i pavlefshem i dates. Ju lutem perdorni formatin "
                    "dita-muaji-Viti.", RED))


def known_categories(trans_type):
    """Suggested categories for a type, plus any already used in the data."""
    options = list(SUGGESTED_CATEGORIES.get(trans_type, []))
    for t in transactions:
        if t['lloji'] == trans_type:
            category = t.get('kategoria', DEFAULT_CATEGORY)
            if category and category not in options and category != DEFAULT_CATEGORY:
                options.append(category)
    return options


def prompt_category(trans_type, current=None):
    """Ask for a category: pick a number from the list, or type a new one."""
    options = known_categories(trans_type)
    print("\nKategorite e sugjeruara:")
    for i, option in enumerate(options, start=1):
        print(f"  {i}. {option}")
    print(paint("  (Ose shkruani nje kategori tuajen)", DIM))

    while True:
        if current is None:
            raw = input("Zgjidhni ose shkruani kategorine: ").strip()
        else:
            raw = input(f"Kategoria [{current}] (Enter = pa ndryshim): ").strip()
            if not raw:
                return current
        if not raw:
            return DEFAULT_CATEGORY
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1]
            print(paint("Numer i pavlefshem i kategorise.", RED))
            continue
        return raw


def prompt_type(current=None):
    """Ask whether a transaction is income or an expense."""
    while True:
        print("  1. Te Ardhura")
        print("  2. Shpenzime")
        if current is None:
            raw = input("Zgjidhni llojin (1-2): ").strip()
        else:
            raw = input(f"Lloji [{current}] (Enter = pa ndryshim): ").strip()
            if not raw:
                return current
        if raw == '1':
            return 'Te Ardhura'
        if raw == '2':
            return 'Shpenzime'
        print(paint("Zgjedhje e pavlefshme. Vendosni 1 ose 2.", RED))


# ---------------------------------------------------------------------------
# Adding, modifying, and deleting transactions
# ---------------------------------------------------------------------------

def add_transaction(trans_type, description=None, amount=None, date=None,
                    category=None):
    """Add a new income or expense transaction.

    Any field passed in (e.g. from a command-line flag) is validated and used
    as-is; anything left as None is asked for interactively.
    """
    print(paint(f"\nDuke shtuar {trans_type}...", BOLD, color_for_type(trans_type)))

    if description is None:
        description = prompt_description()
    else:
        description = description.strip()
        if not description:
            print(paint("Pershkrimi nuk mund te jete i zbrazet.", RED))
            return False

    if amount is None:
        amount = prompt_amount()
    else:
        validated = validate_amount(str(amount))
        if validated is None:
            print(paint("Shuma eshte e pavlefshme. Ju lutem, vendosni nje numer "
                        "pozitiv.", RED))
            return False
        amount = validated

    if date is None:
        date = prompt_date()
    else:
        if parse_date(date) is None:
            print(paint("Format i pavlefshem i dates. Ju lutem perdorni formatin "
                        "dita-muaji-Viti.", RED))
            return False
        date = date.strip()

    if category is None:
        category = prompt_category(trans_type)
    else:
        category = category.strip() or DEFAULT_CATEGORY

    transactions.append({
        'lloji': trans_type,
        'pershkrimi': description,
        'shuma': amount,
        'data': date,
        'kategoria': category,
    })
    print(paint(f"{trans_type} eshte shtuar me sukses!", GREEN))
    save_transactions()
    return True


def ask_transaction_number(action_label):
    """Show the transaction list and ask the user to pick one by number.

    Returns the index into `transactions`, or None if there is nothing to pick
    or the user cancels.
    """
    view_transactions()
    if not transactions:
        return None
    raw = input(f"\nVendosni numrin e transaksionit per ta {action_label} "
                f"(ose 'a' per te anuluar): ").strip().lower()
    if raw == 'a':
        print("Anuluar.")
        return None
    try:
        index = int(raw)
        if index < 1 or index > len(transactions):
            raise ValueError
    except ValueError:
        print(paint("Numer i pavlefshem.", RED))
        return None
    return index - 1


def edit_transaction():
    """Edit an existing transaction in place, field by field.

    Pressing Enter at any prompt keeps the current value, so a single field can
    be corrected without retyping the rest.
    """
    index = ask_transaction_number("ndryshuar")
    if index is None:
        return

    t = transactions[index]
    print(paint(f"\nDuke ndryshuar transaksionin #{index + 1}", BOLD))
    print(paint("Shtypni Enter per te lene nje fushe pa ndryshim.", DIM))

    print("\nLloji:")
    new_type = prompt_type(current=t['lloji'])
    new_description = prompt_description(current=t['pershkrimi'])
    new_amount = prompt_amount(current=t['shuma'])
    new_date = prompt_date(current=t['data'])
    new_category = prompt_category(new_type, current=t.get('kategoria',
                                                           DEFAULT_CATEGORY))

    t['lloji'] = new_type
    t['pershkrimi'] = new_description
    t['shuma'] = new_amount
    t['data'] = new_date
    t['kategoria'] = new_category

    print(paint("Transaksioni u ndryshua me sukses!", GREEN))
    save_transactions()


def delete_transaction():
    """Delete a transaction by the number shown in view_transactions()."""
    index = ask_transaction_number("fshire")
    if index is None:
        return
    removed = transactions.pop(index)
    print(paint(f"U fshi: {removed['data']} - {removed['lloji']} - "
                f"{removed['pershkrimi']}", YELLOW))
    save_transactions()


# ---------------------------------------------------------------------------
# Displaying transactions
# ---------------------------------------------------------------------------

def print_transaction_table(rows, title="Te gjitha transaksionet:"):
    """Print a table of (number, transaction) pairs.

    Columns are sized to the longest value actually present (or the header, if
    that's longer), so labels, categories and descriptions are always shown in
    full - nothing is truncated.
    """
    if not rows:
        print(paint("\nNuk u gjet asnje transaksion.", YELLOW))
        return

    amounts = {number: f"{CURRENCY_SYMBOL}{t['shuma']:.2f}" for number, t in rows}

    lloji_width = max([len('Lloji')] + [len(t['lloji']) for _, t in rows])
    pershkrimi_width = max([len('Pershkrimi')] + [len(t['pershkrimi']) for _, t in rows])
    kategoria_width = max([len('Kategoria')] +
                          [len(t.get('kategoria', DEFAULT_CATEGORY)) for _, t in rows])
    shuma_width = max([len('Shuma')] + [len(a) for a in amounts.values()])
    number_width = max(3, len(str(max(number for number, _ in rows))) + 1)

    total_width = (number_width + 12 + 1 + lloji_width + 1 + pershkrimi_width +
                   1 + kategoria_width + 1 + shuma_width)

    header = (f"{'#':<{number_width}}{'Data':<12} {'Lloji':<{lloji_width}} "
              f"{'Pershkrimi':<{pershkrimi_width}} "
              f"{'Kategoria':<{kategoria_width}} {'Shuma':>{shuma_width}}")

    print(paint(f"\n{title}", BOLD, CYAN))
    print("-" * total_width)
    print(paint(header, BOLD))
    print("-" * total_width)
    for number, t in rows:
        # Pad every field first, then apply color, so the ANSI escape codes
        # never count towards the column widths.
        line = (f"{number:<{number_width}}{t['data']:<12} "
                f"{t['lloji']:<{lloji_width}} "
                f"{t['pershkrimi']:<{pershkrimi_width}} "
                f"{t.get('kategoria', DEFAULT_CATEGORY):<{kategoria_width}} "
                f"{amounts[number]:>{shuma_width}}")
        print(paint(line, color_for_type(t['lloji'])))
    print("-" * total_width)


def view_transactions(items=None, title="Te gjitha transaksionet:"):
    """Display transactions, numbered so they can be referenced for edit/delete.

    The numbers always refer to positions in the full transaction list, so a
    number shown in a filtered view can still be used to edit or delete.
    """
    if items is None:
        rows = list(enumerate(transactions, start=1))
    else:
        rows = items
    print_transaction_table(rows, title)


def filter_transactions(start_date=None, end_date=None):
    """Return (number, transaction) pairs whose date falls in the given range.

    Both bounds are inclusive. Passing the same date as both start and end
    filters to that single day. Transactions with an unparseable date are
    skipped rather than crashing the view.
    """
    rows = []
    for number, t in enumerate(transactions, start=1):
        t_date = parse_date(t['data'])
        if t_date is None:
            continue
        if start_date is not None and t_date < start_date:
            continue
        if end_date is not None and t_date > end_date:
            continue
        rows.append((number, t))
    return rows


def show_filtered(start_date, end_date, title):
    """Print a filtered transaction table followed by its own totals."""
    rows = filter_transactions(start_date, end_date)
    view_transactions(items=rows, title=title)
    if rows:
        print_summary([t for _, t in rows], title="Totalet per kete filtrim:")


def prompt_single_date_filter():
    """Interactive filter for one specific date."""
    while True:
        raw = input("Vendosni daten ( dite-muaj-Vit ) ose 'a' per te anuluar: ").strip()
        if raw.lower() == 'a':
            print("Anuluar.")
            return
        target = parse_date(raw)
        if target is None:
            print(paint("Format i pavlefshem i dates. Ju lutem perdorni formatin "
                        "dita-muaji-Viti.", RED))
            continue
        show_filtered(target, target, f"Transaksionet e dates {format_date(target)}:")
        return


def prompt_date_range_filter():
    """Interactive filter between two dates (inclusive)."""
    while True:
        raw = input("Data e fillimit ( dite-muaj-Vit ) ose 'a' per te anuluar: ").strip()
        if raw.lower() == 'a':
            print("Anuluar.")
            return
        start = parse_date(raw)
        if start is None:
            print(paint("Format i pavlefshem i dates. Ju lutem perdorni formatin "
                        "dita-muaji-Viti.", RED))
            continue
        break

    while True:
        raw = input("Data e mbarimit ( dite-muaj-Vit ) ose 'a' per te anuluar: ").strip()
        if raw.lower() == 'a':
            print("Anuluar.")
            return
        end = parse_date(raw)
        if end is None:
            print(paint("Format i pavlefshem i dates. Ju lutem perdorni formatin "
                        "dita-muaji-Viti.", RED))
            continue
        if end < start:
            print(paint("Data e mbarimit nuk mund te jete para dates se fillimit.",
                        RED))
            continue
        break

    show_filtered(start, end,
                  f"Transaksionet nga {format_date(start)} deri {format_date(end)}:")


# ---------------------------------------------------------------------------
# Status and summaries
# ---------------------------------------------------------------------------

def calculate_balance(items=None):
    """Calculate current balance, total income, total expenses.

    Works on the full transaction list by default, or on any subset (for
    example the result of a date filter).
    """
    if items is None:
        items = transactions
    total_income = Decimal('0.00')
    total_expenses = Decimal('0.00')
    for t in items:
        if t['lloji'] == 'Te Ardhura':
            total_income += t['shuma']
        else:
            total_expenses += t['shuma']
    balance = total_income - total_expenses
    return balance, total_income, total_expenses


def totals_by_category(items, trans_type):
    """Sum the amounts per category for one transaction type, largest first."""
    totals = {}
    for t in items:
        if t['lloji'] != trans_type:
            continue
        category = t.get('kategoria', DEFAULT_CATEGORY)
        totals[category] = totals.get(category, Decimal('0.00')) + t['shuma']
    return sorted(totals.items(), key=lambda pair: pair[1], reverse=True)


def print_category_breakdown(items, trans_type):
    """Print a per-category breakdown for one transaction type."""
    rows = totals_by_category(items, trans_type)
    if not rows:
        return
    color = color_for_type(trans_type)
    width = max(len(category) for category, _ in rows)
    print(paint(f"\n  {trans_type} sipas kategorise:", color))
    for category, total in rows:
        amount_str = f"{CURRENCY_SYMBOL}{total:.2f}"
        print(f"    {category:<{width}}  {amount_str:>12}")


def print_summary(items=None, title="Permbledhja Financiare:"):
    """Print totals plus a per-category breakdown."""
    if items is None:
        items = transactions
    balance, total_income, total_expenses = calculate_balance(items)

    print(paint(f"\n{title}", BOLD, CYAN))
    print(f"Te Ardhurat Totale: "
          f"{paint(f'{CURRENCY_SYMBOL}{total_income:.2f}', GREEN)}")
    print(f"Shpenzimet Totale: "
          f"{paint(f'{CURRENCY_SYMBOL}{total_expenses:.2f}', RED)}")
    balance_color = GREEN if balance >= 0 else RED
    print(f"Gjendja Aktuale: "
          f"{paint(f'{CURRENCY_SYMBOL}{balance:.2f}', BOLD, balance_color)}")
    print(f"Numri i Transaksioneve: {len(items)}")

    print_category_breakdown(items, 'Te Ardhura')
    print_category_breakdown(items, 'Shpenzime')


def view_balance():
    """Display current balance and summaries."""
    print_summary()


# ---------------------------------------------------------------------------
# Recurring transactions
# ---------------------------------------------------------------------------

def due_occurrences(rule, today):
    """Return every occurrence of a rule that is due but not yet generated.

    Each occurrence is computed from the rule's start date rather than from the
    previous one, so a month with fewer days can never shift the schedule
    permanently.
    """
    advance = FREQUENCIES.get(rule.get('frekuenca'))
    start = parse_date(rule.get('data_fillimit'))
    if advance is None or start is None:
        return []

    last_generated = parse_date(rule.get('data_e_fundit'))
    occurrences = []
    k = 0
    while True:
        occurrence = advance(start, k)
        if occurrence > today:
            break
        if last_generated is None or occurrence > last_generated:
            occurrences.append(occurrence)
        k += 1
        if k > 5000:  # safety valve against a malformed rule looping forever
            break
    return occurrences


def process_recurring(quiet=False):
    """Generate any recurring transactions that have become due.

    Safe to run repeatedly: each rule records the last date it generated, so
    an occurrence is never created twice.
    """
    today = datetime.date.today()
    generated = 0

    for rule in recurring_rules:
        for occurrence in due_occurrences(rule, today):
            transactions.append({
                'lloji': rule['lloji'],
                'pershkrimi': rule['pershkrimi'],
                'shuma': rule['shuma'],
                'data': format_date(occurrence),
                'kategoria': rule.get('kategoria', DEFAULT_CATEGORY),
            })
            rule['data_e_fundit'] = format_date(occurrence)
            generated += 1

    if generated:
        save_transactions(quiet=True)
        save_recurring(quiet=True)
        print(paint(f"U gjeneruan {generated} transaksione te perseritura.", GREEN))
    elif not quiet:
        print("Nuk ka transaksione te perseritura per te gjeneruar.")

    return generated


def view_recurring():
    """List all recurring rules with their next scheduled date."""
    if not recurring_rules:
        print(paint("\nNuk ka asnje transaksion te perseritur.", YELLOW))
        return

    print(paint("\nTransaksionet e perseritura:", BOLD, CYAN))
    print("-" * 88)
    print(paint(f"{'#':<4}{'Lloji':<12} {'Pershkrimi':<24} {'Kategoria':<16} "
                f"{'Frekuenca':<10} {'Shuma':>10}", BOLD))
    print("-" * 88)
    for i, rule in enumerate(recurring_rules, start=1):
        amount_str = f"{CURRENCY_SYMBOL}{rule['shuma']:.2f}"
        line = (f"{i:<4}{rule['lloji']:<12} {rule['pershkrimi']:<24} "
                f"{rule.get('kategoria', DEFAULT_CATEGORY):<16} "
                f"{rule.get('frekuenca', 'mujore'):<10} {amount_str:>10}")
        print(paint(line, color_for_type(rule['lloji'])))
        advance = FREQUENCIES.get(rule.get('frekuenca'))
        start = parse_date(rule.get('data_fillimit'))
        last = parse_date(rule.get('data_e_fundit'))
        if advance and start:
            # Find the first occurrence still in the future.
            k = 0
            next_date = advance(start, k)
            while last is not None and next_date <= last and k <= 5000:
                k += 1
                next_date = advance(start, k)
            print(paint(f"    Radha tjeter: {format_date(next_date)}", DIM))
    print("-" * 88)


def add_recurring():
    """Create a new recurring transaction rule."""
    print(paint("\nDuke shtuar nje transaksion te perseritur...", BOLD))
    trans_type = prompt_type()
    description = prompt_description()
    amount = prompt_amount()
    category = prompt_category(trans_type)

    frequency_names = list(FREQUENCIES.keys())
    print("\nFrekuenca:")
    for i, name in enumerate(frequency_names, start=1):
        print(f"  {i}. {name}")
    while True:
        raw = input(f"Zgjidhni frekuencen (1-{len(frequency_names)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(frequency_names):
            frequency = frequency_names[int(raw) - 1]
            break
        print(paint("Zgjedhje e pavlefshme.", RED))

    print(paint("\nData e pare e ketij transaksioni:", DIM))
    start_date = prompt_date()

    recurring_rules.append({
        'lloji': trans_type,
        'pershkrimi': description,
        'shuma': amount,
        'kategoria': category,
        'frekuenca': frequency,
        'data_fillimit': start_date,
        # Empty means nothing has been generated yet, so the first occurrence is the start date itself.
        'data_e_fundit': '',
    })
    print(paint("Transaksioni i perseritur u shtua me sukses!", GREEN))
    save_recurring()
    process_recurring(quiet=True)


def delete_recurring():
    """Delete a recurring rule by its number."""
    view_recurring()
    if not recurring_rules:
        return
    raw = input("\nVendosni numrin e perseritjes per ta fshire "
                "(ose 'a' per te anuluar): ").strip().lower()
    if raw == 'a':
        print("Anuluar.")
        return
    try:
        index = int(raw)
        if index < 1 or index > len(recurring_rules):
            raise ValueError
    except ValueError:
        print(paint("Numer i pavlefshem.", RED))
        return
    removed = recurring_rules.pop(index - 1)
    print(paint(f"U fshi perseritja: {removed['pershkrimi']}", YELLOW))
    save_recurring()


def recurring_menu():
    """Submenu for managing recurring transactions."""
    while True:
        print(paint("\nTransaksionet e Perseritura:", BOLD, CYAN))
        print("1. Shiko Perseritjet")
        print("2. Shto nje Perseritje")
        print("3. Fshi nje Perseritje")
        print("4. Gjenero Perseritjet e Radhes")
        print("5. Kthehu ne menune kryesore")

        choice = input("Vendosni Zgjedhjen Tuaj (1-5): ").strip()

        if choice == '1':
            view_recurring()
        elif choice == '2':
            add_recurring()
        elif choice == '3':
            delete_recurring()
        elif choice == '4':
            process_recurring()
        elif choice == '5':
            return
        else:
            print(paint("Zgjedhje e pavlefshme. Ju lutem, vendosni nje numer "
                        "midis 1 dhe 5.", RED))


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def filter_menu():
    """Submenu for date filtering."""
    print(paint("\nFiltro sipas Dates:", BOLD, CYAN))
    print("1. Nje date e caktuar")
    print("2. Midis dy datave")
    print("3. Kthehu ne menune kryesore")

    choice = input("Vendosni Zgjedhjen Tuaj (1-3): ").strip()

    if choice == '1':
        prompt_single_date_filter()
    elif choice == '2':
        prompt_date_range_filter()
    elif choice == '3':
        return
    else:
        print(paint("Zgjedhje e pavlefshme. Ju lutem, vendosni nje numer midis "
                    "1 dhe 3.", RED))


def run_menu():
    """Main program loop."""
    print(paint("Mire se vini ne Menaxherin e te Ardhurave dhe Shpenzimeve "
                "Personale!", BOLD, CYAN))

    while True:
        print(paint("\nMenu:", BOLD))
        print("1. Shtoni Te Ardhurat")
        print("2. Shtoni Shpenzimet")
        print("3. Shiko Te Gjitha Transaksionet")
        print("4. Shiko Gjendjen Aktuale")
        print("5. Ndrysho nje Transaksion")
        print("6. Fshi nje Transaksion")
        print("7. Filtro sipas Dates")
        print("8. Transaksionet e Perseritura")
        print("9. Dil nga programi")

        choice = input("Vendosni Zgjedhjen Tuaj (1-9): ").strip()

        if choice == '1':
            add_transaction('Te Ardhura')
        elif choice == '2':
            add_transaction('Shpenzime')
        elif choice == '3':
            view_transactions()
        elif choice == '4':
            view_balance()
        elif choice == '5':
            edit_transaction()
        elif choice == '6':
            delete_transaction()
        elif choice == '7':
            filter_menu()
        elif choice == '8':
            recurring_menu()
        elif choice == '9':
            print(paint("Faleminderit qe perdoret Menaxherin e te Ardhurave dhe "
                        "Shpenzimeve Personale. Mirupafshim!", CYAN))
            break
        else:
            print(paint("Zgjedhje e pavlefshme. Ju lutem, vendosni nje numer "
                        "midis 1 dhe 9.", RED))


# ---------------------------------------------------------------------------
# Command line (argparse)
# ---------------------------------------------------------------------------

def build_parser():
    """Build the command-line parser. Albanian flags first, English aliases second."""
    parser = argparse.ArgumentParser(
        prog='personal_finance_manager.py',
        description='Menaxheri i te Ardhurave dhe Shpenzimeve Personale. '
                    'Pa asnje flamur, hapet menuja interaktive.',
        epilog='Shembuj:\n'
               '  %(prog)s --lista\n'
               '  %(prog)s --lista --data 05-08-2026\n'
               '  %(prog)s --lista --nga 01-08-2026 --deri 31-08-2026\n'
               '  %(prog)s --gjendja\n'
               '  %(prog)s --shto-shpenzime --pershkrimi "Qera" --shuma 300 '
               '--kategoria Qera\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('--ndihma', action='help',
                        help='Shfaq kete mesazh ndihme dhe dil')

    actions = parser.add_argument_group('veprimet')
    actions.add_argument('--lista', '--list', action='store_true',
                         help='Shfaq transaksionet (mund te filtrohet me --data '
                              'ose --nga/--deri)')
    actions.add_argument('--gjendja', '--balance', action='store_true',
                         help='Shfaq permbledhjen financiare')
    actions.add_argument('--shto-te-ardhura', '--add-income', action='store_true',
                         dest='shto_te_ardhura',
                         help='Shto nje te ardhur')
    actions.add_argument('--shto-shpenzime', '--add-expense', action='store_true',
                         dest='shto_shpenzime',
                         help='Shto nje shpenzim')
    actions.add_argument('--perserit', '--recurring', action='store_true',
                         help='Gjenero transaksionet e perseritura qe jane te radhes')

    fields = parser.add_argument_group('fushat e transaksionit / filtrat')
    fields.add_argument('--pershkrimi', '--description',
                        help='Pershkrimi i transaksionit te ri')
    fields.add_argument('--shuma', '--amount',
                        help='Shuma e transaksionit te ri')
    fields.add_argument('--data', '--date',
                        help='Data (dite-muaj-Vit). Me --lista filtron nje date '
                             'te vetme; me --shto-* cakton daten e transaksionit')
    fields.add_argument('--kategoria', '--category',
                        help='Kategoria e transaksionit te ri')
    fields.add_argument('--nga', '--from', dest='nga',
                        help='Data e fillimit e filtrit (perfshirese)')
    fields.add_argument('--deri', '--to', dest='deri',
                        help='Data e mbarimit e filtrit (perfshirese)')

    parser.add_argument('--pa-ngjyra', '--no-color', action='store_true',
                        dest='pa_ngjyra',
                        help='Cakto daljen pa ngjyra')

    return parser


def run_cli(args):
    """Handle command-line flags. Returns True if a flag action was performed."""
    did_something = False

    if args.perserit:
        process_recurring()
        did_something = True

    if args.shto_te_ardhura or args.shto_shpenzime:
        trans_type = 'Te Ardhura' if args.shto_te_ardhura else 'Shpenzime'
        add_transaction(trans_type,
                        description=args.pershkrimi,
                        amount=args.shuma,
                        date=args.data,
                        category=args.kategoria)
        did_something = True

    if args.lista:
        start = end = None
        if args.data:
            start = end = parse_date(args.data)
            if start is None:
                print(paint("Format i pavlefshem i dates ne --data.", RED))
                return True
        else:
            if args.nga:
                start = parse_date(args.nga)
                if start is None:
                    print(paint("Format i pavlefshem i dates ne --nga.", RED))
                    return True
            if args.deri:
                end = parse_date(args.deri)
                if end is None:
                    print(paint("Format i pavlefshem i dates ne --deri.", RED))
                    return True
            if start and end and end < start:
                print(paint("Data e mbarimit nuk mund te jete para dates se "
                            "fillimit.", RED))
                return True

        if start is None and end is None:
            view_transactions()
        else:
            if start == end:
                title = f"Transaksionet e dates {format_date(start)}:"
            elif start and end:
                title = (f"Transaksionet nga {format_date(start)} deri "
                         f"{format_date(end)}:")
            elif start:
                title = f"Transaksionet nga {format_date(start)} e tutje:"
            else:
                title = f"Transaksionet deri me {format_date(end)}:"
            show_filtered(start, end, title)
        did_something = True

    if args.gjendja:
        view_balance()
        did_something = True

    return did_something


def main():
    """Entry point: run a command-line action, or fall back to the menu."""
    global COLORS_ENABLED

    parser = build_parser()
    args = parser.parse_args()

    COLORS_ENABLED = detect_color_support() and not args.pa_ngjyra

    load_transactions()
    load_recurring()

    # Generate anything that has come due since the last run. Quiet here so a normal start-up stays clean when there is nothing to do. Skipped when --perserit was passed, since run_cli() reports the same run in full.
    if not args.perserit:
        process_recurring(quiet=True)

    if not run_cli(args):
        run_menu()


if __name__ == "__main__":
    main()
