"""Raportet dhe llogaritjet / Reports and calculations.

Pure functions over lists of transactions: no printing, no input, no files.
That is what makes this module straightforward to test.
"""

from decimal import Decimal

from .collation import sort_names
from .config import EXPENSE, INCOME
from .dates import month_bounds, month_of, previous_month

ZERO = Decimal("0.00")


class Totals:
    """Income, expenses, balance and count for a set of transactions."""

    def __init__(self, income=ZERO, expenses=ZERO, count=0):
        self.income = income
        self.expenses = expenses
        self.count = count

    @property
    def balance(self):
        return self.income - self.expenses

    def __eq__(self, other):
        return (
            isinstance(other, Totals)
            and self.income == other.income
            and self.expenses == other.expenses
            and self.count == other.count
        )

    def __repr__(self):
        return (
            f"Totals(income={self.income}, expenses={self.expenses}, "
            f"balance={self.balance}, count={self.count})"
        )


def calculate_totals(transactions):
    """Total income, expenses, balance and count for a list of transactions.

    Transfers are deliberately counted as neither. Money moved between the
    user's own accounts has not been earned or spent, and an `else` branch
    here would quietly file every one of them as an expense.
    """
    income = ZERO
    expenses = ZERO
    for t in transactions:
        if t.lloji == INCOME:
            income += t.shuma
        elif t.lloji == EXPENSE:
            expenses += t.shuma
    return Totals(income=income, expenses=expenses, count=len(transactions))


def sort_by_date(transactions):
    """Chronological order, with undated entries last and ties kept stable.

    Recurring rules append their occurrences in rule order rather than date
    order, so any listing that cares about chronology sorts through here.
    """

    def key(item):
        parsed = item.date
        return (parsed is None, parsed or ())

    return sorted(transactions, key=key)


def filter_by_dates(transactions, start=None, end=None):
    """Transactions falling within an inclusive date range.

    Passing the same date as both bounds selects a single day. Entries with an
    unparseable date are excluded rather than raising.
    """
    matched = []
    for t in transactions:
        parsed = t.date
        if parsed is None:
            continue
        if start is not None and parsed < start:
            continue
        if end is not None and parsed > end:
            continue
        matched.append(t)
    return matched


def filter_by_month(transactions, year, month):
    """Transactions falling inside one calendar month."""
    start, end = month_bounds(year, month)
    return filter_by_dates(transactions, start, end)


def search(transactions, term):
    """Transactions whose description, category or subcategory contains `term`.

    Case-insensitive; an empty term matches nothing rather than everything, so
    a stray Enter cannot look like a successful search over the whole file.
    """
    needle = (term or "").strip().lower()
    if not needle:
        return []
    return [
        t
        for t in transactions
        if needle in t.pershkrimi.lower()
        or needle in t.kategoria.lower()
        or needle in t.nenkategoria.lower()
    ]


def ordered_options(options):
    """Sort names in Albanian alphabetical order, keeping the catch-all last.

    Applied to every suggestion list, so a category the user types themselves
    takes its alphabetical place rather than being appended to the end - and
    "Te tjera" stays at the bottom where a catch-all belongs, however many
    names are added around it.

    Ordering follows the Albanian alphabet, digraphs included: see collation.
    """
    from .config import OTHER_CATEGORY

    rest = sort_names(o for o in options if o != OTHER_CATEGORY)
    catch_all = [o for o in options if o == OTHER_CATEGORY]
    # Deduplicated in case the catch-all appears both as a suggestion and in
    # the user's own data.
    return rest + catch_all[:1]


def totals_by_category(transactions, trans_type):
    """Per-category totals for one transaction type, largest first."""
    totals = {}
    for t in transactions:
        if t.lloji != trans_type:
            continue
        totals[t.kategoria] = totals.get(t.kategoria, ZERO) + t.shuma
    return sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))


def totals_by_subcategory(transactions, trans_type, category):
    """Per-subcategory totals within one category, largest first.

    Amounts with no subcategory are grouped under the empty string, which the
    display layer renders as a dash.
    """
    totals = {}
    for t in transactions:
        if t.lloji != trans_type or t.kategoria != category:
            continue
        totals[t.nenkategoria] = totals.get(t.nenkategoria, ZERO) + t.shuma
    # Unsubcategorised amounts sort last regardless of size, so the named
    # subcategories read as the breakdown and the remainder as leftovers.
    return sorted(totals.items(), key=lambda pair: (pair[0] == "", -pair[1], pair[0]))


def has_subcategories(transactions):
    """Whether any transaction uses a subcategory.

    Lets the display layer leave the column out entirely for users who do not
    use subcategories, instead of padding every row with dashes.
    """
    return any(t.nenkategoria for t in transactions)


def percent_change(current, previous):
    """Percent change from previous to current, or None if undefined.

    Returns None when the previous value is zero, since "up 100%" from nothing
    is misleading - the caller should say "new" instead.
    """
    if previous == ZERO:
        return None
    return (current - previous) / previous * Decimal("100")


class MonthlyReport:
    """One month's totals, category breakdown, and comparison with the month before."""

    def __init__(self, year, month, transactions):
        self.year = year
        self.month = month
        self.transactions = filter_by_month(transactions, year, month)
        self.totals = calculate_totals(self.transactions)

        prev_year, prev_month = previous_month(year, month)
        self.previous_transactions = filter_by_month(transactions, prev_year, prev_month)
        self.previous_totals = calculate_totals(self.previous_transactions)

        self.income_by_category = totals_by_category(self.transactions, INCOME)
        self.expenses_by_category = totals_by_category(self.transactions, EXPENSE)

    @property
    def is_empty(self):
        return self.totals.count == 0

    @property
    def income_change(self):
        return percent_change(self.totals.income, self.previous_totals.income)

    @property
    def expense_change(self):
        return percent_change(self.totals.expenses, self.previous_totals.expenses)

    @property
    def has_previous(self):
        return self.previous_totals.count > 0


def month_report(transactions, year, month):
    """Build a MonthlyReport for the given month."""
    return MonthlyReport(year, month, transactions)


def current_month_report(transactions, as_of):
    """Report for the month containing `as_of`."""
    year, month = month_of(as_of)
    return month_report(transactions, year, month)


def known_categories(transactions, trans_type, suggested):
    """Suggested categories for a type, plus any already used in the data."""
    from .config import DEFAULT_CATEGORY

    options = list(suggested.get(trans_type, []))
    for t in transactions:
        if t.lloji != trans_type:
            continue
        if t.kategoria and t.kategoria not in options and t.kategoria != DEFAULT_CATEGORY:
            options.append(t.kategoria)
    return ordered_options(options)


def known_subcategories(transactions, trans_type, category, suggested):
    """Suggested subcategories for a category, plus any already used with it."""
    options = list(suggested.get(category, []))
    for t in transactions:
        if t.lloji != trans_type or t.kategoria != category:
            continue
        if t.nenkategoria and t.nenkategoria not in options:
            options.append(t.nenkategoria)
    return ordered_options(options)
