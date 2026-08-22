"""Tests for budgets.

Budgets key on a category id now, so a rename no longer needs the budget
rewritten - and a deleted category takes its budget with it.
"""

from decimal import Decimal

import pytest

from personal_finance.budgets import (
    NEAR,
    OK,
    OVER,
    BudgetStatus,
    all_statuses,
    check_after_adding,
    find_budget,
    spent_in_month,
    status_for,
)
from personal_finance.models import Budget
from personal_finance.schema import EXPENSE, INCOME

from .conftest import make_view

FOOD = 1
RENT = 2
NAMES = {FOOD: "Ushqim", RENT: "Qera"}


def budget(category_id=FOOD, limit="200.00"):
    return Budget(category_id=category_id, limit=Decimal(limit))


def spend(amount, category_id=FOOD, date="05-06-2026"):
    return make_view(EXPENSE, "x", amount, date, category="Ushqim", category_id=category_id)


class TestSpentInMonth:
    def test_sums_one_category_in_one_month(self):
        items = [
            spend("30"),
            spend("20"),
            spend("99", category_id=RENT),
            spend("99", date="05-07-2026"),
        ]
        assert spent_in_month(items, FOOD, 2026, 6) == Decimal("50")

    def test_income_never_counts_against_a_budget(self):
        items = [make_view(INCOME, "x", "500", "05-06-2026", category_id=FOOD)]
        assert spent_in_month(items, FOOD, 2026, 6) == Decimal("0.00")

    def test_no_matching_transactions(self):
        assert spent_in_month([], FOOD, 2026, 6) == Decimal("0.00")


class TestBudgetStatus:
    def test_remaining(self):
        status = status_for(budget(), "Ushqim", [spend("50")], 2026, 6)
        assert status.remaining == Decimal("150")

    def test_remaining_goes_negative_when_over(self):
        status = status_for(budget(limit="100"), "Ushqim", [spend("150")], 2026, 6)
        assert status.remaining == Decimal("-50")
        assert status.overspent == Decimal("50")

    def test_overspent_is_zero_within_budget(self):
        status = status_for(budget(limit="100"), "Ushqim", [spend("40")], 2026, 6)
        assert status.overspent == Decimal("0.00")

    @pytest.mark.parametrize(
        "amount,expected",
        [("10", OK), ("79", OK), ("80", NEAR), ("95", NEAR), ("100", NEAR), ("101", OVER)],
    )
    def test_states(self, amount, expected):
        status = status_for(budget(limit="100"), "Ushqim", [spend(amount)], 2026, 6)
        assert status.state == expected

    def test_percent_used(self):
        status = status_for(budget(), "Ushqim", [spend("50")], 2026, 6)
        assert status.percent_used == Decimal("25")

    def test_a_zero_limit_does_not_divide_by_zero(self):
        status = BudgetStatus(FOOD, "Ushqim", Decimal("0.00"), Decimal("10"))
        assert status.fraction_used == Decimal("0.00")


class TestAllStatuses:
    def test_worst_first(self):
        budgets = [budget(FOOD, "100"), budget(RENT, "100")]
        items = [spend("10"), spend("90", category_id=RENT)]
        statuses = all_statuses(budgets, NAMES, items, 2026, 6)
        assert statuses[0].category == "Qera"

    def test_empty(self):
        assert all_statuses([], NAMES, [], 2026, 6) == []

    def test_a_deleted_category_leaves_the_name_missing(self):
        """The budget goes with the category, but a stale map must not crash."""
        statuses = all_statuses([budget(99)], NAMES, [], 2026, 6)
        assert statuses[0].category is None


class TestCheckAfterAdding:
    def test_warns_when_over(self):
        item = spend("150")
        status = check_after_adding([budget(limit="100")], NAMES, [item], item)
        assert status is not None and status.state == OVER

    def test_warns_when_near(self):
        item = spend("85")
        assert check_after_adding([budget(limit="100")], NAMES, [item], item).state == NEAR

    def test_silent_when_well_within_budget(self):
        item = spend("10")
        assert check_after_adding([budget(limit="100")], NAMES, [item], item) is None

    def test_silent_for_income(self):
        item = make_view(INCOME, "x", "5000", "05-06-2026", category_id=FOOD)
        assert check_after_adding([budget(limit="100")], NAMES, [item], item) is None

    def test_silent_for_an_unbudgeted_category(self):
        item = spend("9999", category_id=RENT)
        assert check_after_adding([budget(FOOD, "100")], NAMES, [item], item) is None

    def test_silent_when_the_transaction_has_no_category(self):
        item = make_view(EXPENSE, "x", "9999", "05-06-2026", category=None, category_id=None)
        assert check_after_adding([budget(limit="100")], NAMES, [item], item) is None

    def test_counts_earlier_spending_in_the_same_month(self):
        """The warning considers the whole month, not just this one entry."""
        earlier = spend("80", date="01-06-2026")
        latest = spend("30", date="15-06-2026")
        status = check_after_adding([budget(limit="100")], NAMES, [earlier, latest], latest)
        assert status.state == OVER
        assert status.overspent == Decimal("10")


class TestFindBudget:
    def test_found_and_not_found(self):
        budgets = [budget(FOOD)]
        assert find_budget(budgets, FOOD) is not None
        assert find_budget(budgets, RENT) is None
