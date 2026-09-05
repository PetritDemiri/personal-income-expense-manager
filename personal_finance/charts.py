"""Grafikët / Charts.

Aggregation for the charts, and nothing else - no printing, no bar characters,
no widths. What comes out is rows of numbers with a fraction attached, and the
display layer decides how wide a bar that is.

Bars are scaled against the largest value in their own chart, so the biggest
one always fills the width. Scaling against a fixed amount would leave most of
a terminal empty whenever the largest expense is small, which is most months.
The consequence is that bars compare within a chart and never between two, and
that is the right trade: a chart is read on its own.
"""

from decimal import Decimal

from .dates import month_of, previous_month
from .reports import ZERO, filter_by_month, totals_by_category

# Spans offered for the month-over-month chart. Three months shows a recent
# direction, six a season, twelve a year - and twelve rows still fit a terminal
# without scrolling.
SPANS = (3, 6, 12)
DEFAULT_SPAN = 6


class Bar:
    """One row of a chart: a label, an amount, and how full the bar is."""

    def __init__(self, label, amount, fraction=ZERO, share=ZERO):
        self.label = label
        self.amount = amount
        self.fraction = fraction
        self.share = share

    def __repr__(self):
        return f"Bar({self.label!r}, {self.amount}, fraction={self.fraction})"

    def __eq__(self, other):
        return isinstance(other, Bar) and self.label == other.label and self.amount == other.amount


def _scaled(pairs):
    """Turn (label, amount) pairs into bars scaled against the largest.

    `share` is each amount as a proportion of the total, which is a different
    question from how long the bar is and worth showing beside it.
    """
    amounts = [abs(amount) for _, amount in pairs]
    largest = max(amounts) if amounts else ZERO
    total = sum(amounts, ZERO)

    bars = []
    for label, amount in pairs:
        fraction = (abs(amount) / largest) if largest else ZERO
        share = (abs(amount) / total) if total else ZERO
        bars.append(Bar(label, amount, fraction, share))
    return bars


def category_bars(transactions, kind, year=None, month=None, limit=None):
    """Totals per category, largest first, optionally for one month."""
    rows = transactions
    if year is not None and month is not None:
        rows = filter_by_month(rows, year, month)

    pairs = totals_by_category(rows, kind)
    if limit:
        pairs = pairs[:limit]
    return _scaled(pairs)


def month_span(as_of, span=DEFAULT_SPAN):
    """The last `span` months ending with the one containing `as_of`.

    Oldest first, so a chart reads left to right in time like everything else.
    """
    year, month = month_of(as_of)
    months = [(year, month)]
    for _ in range(max(0, span - 1)):
        year, month = previous_month(year, month)
        months.insert(0, (year, month))
    return months


def monthly_bars(transactions, as_of, span=DEFAULT_SPAN):
    """Income and expenses for each of the last `span` months.

    Returns (months, income_bars, expense_bars). Both sets are scaled against
    the same largest value, so a month with more income than spending is
    visibly so rather than merely numerically so.
    """
    from .reports import calculate_totals

    months = month_span(as_of, span)
    totals = []
    for year, month in months:
        rows = filter_by_month(transactions, year, month)
        totals.append((f"{month:02d}-{year}", calculate_totals(rows)))

    # One scale across both series, so the two are comparable side by side.
    every = [t.income for _, t in totals] + [t.expenses for _, t in totals]
    largest = max(every) if every else ZERO

    def make(pick):
        bars = []
        for label, total in totals:
            amount = pick(total)
            fraction = (amount / largest) if largest else ZERO
            bars.append(Bar(label, amount, fraction))
        return bars

    return months, make(lambda t: t.income), make(lambda t: t.expenses)


def account_bars(balances):
    """A bar per account balance, including the unassigned row if present.

    Negative balances are kept negative: a card in debt is a real state and
    hiding the sign would misrepresent it.
    """
    pairs = [(balance.name, balance.balance) for balance in balances]
    return _scaled(pairs)


def has_data(bars):
    """Whether a chart has anything worth drawing."""
    return any(bar.amount != ZERO for bar in bars)


def percent(value):
    """A fraction as a whole-number percentage."""
    return int((value * Decimal("100")).to_integral_value())
