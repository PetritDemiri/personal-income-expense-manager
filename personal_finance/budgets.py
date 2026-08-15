"""Buxhetet / Budgets.

A budget is a monthly spending limit for one expense category. This module
answers "how am I doing against it" and never prints anything itself.
"""

from decimal import Decimal

from .config import BUDGET_WARNING_THRESHOLD, EXPENSE
from .dates import month_of
from .reports import ZERO, filter_by_month

OK = "ok"
NEAR = "near"
OVER = "over"


class BudgetStatus:
    """How much of one category's monthly budget has been used."""

    def __init__(self, category, limit, spent):
        self.category = category
        self.limit = limit
        self.spent = spent

    @property
    def remaining(self):
        """How much is left. Negative once the budget is exceeded."""
        return self.limit - self.spent

    @property
    def overspent(self):
        """How far past the limit, or zero if still within it."""
        return max(ZERO, self.spent - self.limit)

    @property
    def fraction_used(self):
        """Share of the budget used, as a Decimal. Zero limits report 0."""
        if self.limit == ZERO:
            return ZERO
        return self.spent / self.limit

    @property
    def percent_used(self):
        return self.fraction_used * Decimal("100")

    @property
    def state(self):
        """One of OK, NEAR, or OVER."""
        if self.spent > self.limit:
            return OVER
        if self.fraction_used >= Decimal(str(BUDGET_WARNING_THRESHOLD)):
            return NEAR
        return OK


def spent_in_month(transactions, category, year, month):
    """Total spent in one category during one month."""
    total = ZERO
    for t in filter_by_month(transactions, year, month):
        if t.lloji == EXPENSE and t.kategoria == category:
            total += t.shuma
    return total


def status_for(budget, transactions, year, month):
    """BudgetStatus for one budget in one month."""
    spent = spent_in_month(transactions, budget.kategoria, year, month)
    return BudgetStatus(budget.kategoria, budget.shuma, spent)


def all_statuses(budgets, transactions, year, month):
    """BudgetStatus for every budget, worst first."""
    statuses = [status_for(b, transactions, year, month) for b in budgets]
    return sorted(statuses, key=lambda s: (-s.fraction_used, s.category))


def find_budget(budgets, category):
    """The budget for a category, or None if there isn't one."""
    for budget in budgets:
        if budget.kategoria == category:
            return budget
    return None


def check_after_adding(budgets, transactions, transaction):
    """Status to warn about after adding a transaction, or None.

    Returns a BudgetStatus only when the transaction is an expense in a
    budgeted category and that budget is now at or over its threshold - so the
    caller can warn at the moment of spending rather than at month end.
    """
    if transaction.lloji != EXPENSE:
        return None
    budget = find_budget(budgets, transaction.kategoria)
    if budget is None:
        return None
    parsed = transaction.date
    if parsed is None:
        return None
    year, month = month_of(parsed)
    status = status_for(budget, transactions, year, month)
    return status if status.state in (NEAR, OVER) else None


def set_budget(budgets, category, amount):
    """Add or update a budget in place. Returns the Budget object."""
    from .models import Budget

    existing = find_budget(budgets, category)
    if existing is not None:
        existing.shuma = amount
        return existing
    budget = Budget(kategoria=category, shuma=amount)
    budgets.append(budget)
    return budget
