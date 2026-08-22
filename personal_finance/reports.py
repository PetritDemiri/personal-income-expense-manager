"""Raportet dhe llogaritjet / Reports and calculations.

Pure functions over lists of transaction views. No printing, no input, no
database. Filtering that can be pushed into SQL now lives in the database
layer; what remains here is aggregation, which has to happen in Python because
it produces Decimals and grouped structures rather than rows.

Views rather than models, because a report groups by category *name* - that is
what a reader wants to see - while an id is what the database stores. The view
carries both.
"""

from decimal import Decimal

from .collation import sort_names
from .dates import month_bounds, month_of, parse_date, previous_month
from .schema import EXPENSE, INCOME

ZERO = Decimal("0.00")

OTHER = "Te tjera"


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
    """Total income, expenses, balance and count.

    Transfers are counted as neither. Money moved between the user's own
    accounts has not been earned or spent, and an `else` branch here would
    quietly file every one of them as an expense - which it did, once.
    """
    income = ZERO
    expenses = ZERO
    for item in transactions:
        if item.kind == INCOME:
            income += item.amount
        elif item.kind == EXPENSE:
            expenses += item.amount
    return Totals(income=income, expenses=expenses, count=len(transactions))


def sort_by_date(transactions):
    """Chronological order, undated last, ties stable.

    The database returns rows in date order already, so this is for lists that
    have been filtered or combined in Python since.
    """

    def key(item):
        parsed = parse_date(item.occurred_on)
        return (parsed is None, parsed or ())

    return sorted(transactions, key=key)


def filter_by_dates(transactions, start=None, end=None):
    """Transactions within an inclusive date range.

    Prefer the database's own filtering when the list comes straight from a
    query; this narrows a list already in hand.
    """
    matched = []
    for item in transactions:
        parsed = parse_date(item.occurred_on)
        if parsed is None:
            continue
        if start is not None and parsed < start:
            continue
        if end is not None and parsed > end:
            continue
        matched.append(item)
    return matched


def filter_by_month(transactions, year, month):
    """Transactions falling inside one calendar month."""
    start, end = month_bounds(year, month)
    return filter_by_dates(transactions, start, end)


def totals_by_category(transactions, kind):
    """Per-category totals for one kind, largest first.

    Grouped by name, because that is what gets displayed. Transactions with no
    category group under None, which the display layer renders as a label.
    """
    totals = {}
    for item in transactions:
        if item.kind != kind:
            continue
        totals[item.category] = totals.get(item.category, ZERO) + item.amount
    # Unnamed last regardless of size, so the named groups read as the
    # breakdown and the remainder as leftovers.
    return sorted(totals.items(), key=lambda pair: (pair[0] is None, -pair[1], pair[0] or ""))


def totals_by_subcategory(transactions, kind, category):
    """Per-subcategory totals within one category, largest first."""
    totals = {}
    for item in transactions:
        if item.kind != kind or item.category != category:
            continue
        totals[item.subcategory] = totals.get(item.subcategory, ZERO) + item.amount
    return sorted(totals.items(), key=lambda pair: (pair[0] is None, -pair[1], pair[0] or ""))


def has_subcategories(transactions):
    """Whether any transaction uses a subcategory.

    Lets the display leave the column out entirely for someone who does not
    use them, rather than padding every row with a placeholder.
    """
    return any(item.subcategory for item in transactions)


def has_accounts_used(transactions):
    """Whether any transaction is tied to an account."""
    return any(item.account or item.to_account for item in transactions)


def search(transactions, term):
    """Transactions whose description, category or subcategory contains `term`.

    The database does this in SQL for a query; this is for a list in hand. An
    empty term matches nothing rather than everything, so a stray Enter cannot
    look like a successful search over the whole file.
    """
    needle = (term or "").strip().casefold()
    if not needle:
        return []
    return [
        item
        for item in transactions
        if needle in item.description.casefold()
        or needle in (item.category or "").casefold()
        or needle in (item.subcategory or "").casefold()
    ]


def percent_change(current, previous):
    """Percent change from previous to current, or None if undefined.

    None when the previous value is zero: "up 100%" from nothing is
    misleading, and the caller should say "new" instead.
    """
    if previous == ZERO:
        return None
    return (current - previous) / previous * Decimal("100")


class MonthlyReport:
    """One month's totals and breakdown, against the month before."""

    def __init__(self, year, month, transactions):
        self.year = year
        self.month = month
        self.transactions = filter_by_month(transactions, year, month)
        self.totals = calculate_totals(self.transactions)

        earlier_year, earlier_month = previous_month(year, month)
        self.previous_transactions = filter_by_month(transactions, earlier_year, earlier_month)
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
    return MonthlyReport(year, month, transactions)


def current_month_report(transactions, as_of):
    year, month = month_of(as_of)
    return month_report(transactions, year, month)


def ordered_options(names):
    """Sort names in Albanian alphabetical order, catch-all last.

    Categories are stored rows now rather than being inferred from usage, so
    this only orders them for display - but the rule is unchanged: a name the
    user added takes its alphabetical place, and "Te tjera" stays at the
    bottom where a catch-all belongs.
    """
    rest = sort_names(name for name in names if name != OTHER)
    catch_all = [name for name in names if name == OTHER]
    return rest + catch_all[:1]
