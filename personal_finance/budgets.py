"""Buxhetet / Budgets.

A budget is a monthly spending limit on one category. This module answers "how
am I doing against it" and prints nothing.

Budgets key on a category id now rather than a category name, so renaming a
category no longer needs the budget to be found and rewritten - the reference
survives the rename by itself.
"""

from decimal import Decimal

from .reports import ZERO, filter_by_month
from .schema import EXPENSE

OK = "ok"
NEAR = "near"
OVER = "over"

# Fraction of a limit at which a warning appears before it is exceeded.
WARNING_THRESHOLD = Decimal("0.8")


class BudgetStatus:
    """How much of one category's monthly limit has been used."""

    def __init__(self, category_id, category, limit, spent):
        self.category_id = category_id
        self.category = category
        self.limit = limit
        self.spent = spent

    @property
    def remaining(self):
        """What is left. Negative once the limit is passed."""
        return self.limit - self.spent

    @property
    def overspent(self):
        """How far past the limit, or zero if still within it."""
        return max(ZERO, self.spent - self.limit)

    @property
    def fraction_used(self):
        if self.limit == ZERO:
            return ZERO
        return self.spent / self.limit

    @property
    def percent_used(self):
        return self.fraction_used * Decimal("100")

    @property
    def state(self):
        """One of OK, NEAR or OVER."""
        if self.spent > self.limit:
            return OVER
        if self.fraction_used >= WARNING_THRESHOLD:
            return NEAR
        return OK

    def __repr__(self):
        return f"BudgetStatus({self.category!r}, {self.spent}/{self.limit})"


def spent_in_month(transactions, category_id, year, month):
    """Total spent in one category during one month, from a list in hand.

    The database can do this in SQL; this is for a list already loaded.
    """
    total = ZERO
    for item in filter_by_month(transactions, year, month):
        if item.kind == EXPENSE and item.category_id == category_id:
            total += item.amount
    return total


def status_for(budget, category_name, transactions, year, month):
    """BudgetStatus for one budget in one month."""
    spent = spent_in_month(transactions, budget.category_id, year, month)
    return BudgetStatus(budget.category_id, category_name, budget.limit, spent)


def all_statuses(budgets, category_names, transactions, year, month):
    """Status for every budget, worst first.

    `category_names` maps a category id to its name, so this module never has
    to reach into the database to render a label.
    """
    statuses = [
        status_for(budget, category_names.get(budget.category_id), transactions, year, month)
        for budget in budgets
    ]
    return sorted(statuses, key=lambda s: (-s.fraction_used, s.category or ""))


def find_budget(budgets, category_id):
    """The budget on a category, or None."""
    for budget in budgets:
        if budget.category_id == category_id:
            return budget
    return None


def check_after_adding(budgets, category_names, transactions, transaction):
    """Status worth warning about after adding a transaction, or None.

    Returns a status only when the transaction is an expense in a budgeted
    category and that budget is now at or over its threshold - so the warning
    lands at the moment of spending rather than at month end. The whole month
    is considered, not just this one entry.
    """
    from .dates import month_of, parse_date

    if transaction.kind != EXPENSE or transaction.category_id is None:
        return None
    budget = find_budget(budgets, transaction.category_id)
    if budget is None:
        return None
    parsed = parse_date(transaction.occurred_on)
    if parsed is None:
        return None
    year, month = month_of(parsed)
    status = status_for(budget, category_names.get(budget.category_id), transactions, year, month)
    return status if status.state in (NEAR, OVER) else None
