"""Tests for budgets."""

from decimal import Decimal

import pytest

from personal_finance.budgets import (
    NEAR,
    OK,
    OVER,
    all_statuses,
    check_after_adding,
    find_budget,
    set_budget,
    spent_in_month,
    status_for,
)
from personal_finance.config import EXPENSE, INCOME

from .conftest import make_budget, make_transaction


class TestSpentInMonth:
    def test_sums_one_category_in_one_month(self):
        items = [
            make_transaction(EXPENSE, amount="30", date="05-06-2026", category="Ushqim"),
            make_transaction(EXPENSE, amount="20", date="20-06-2026", category="Ushqim"),
            make_transaction(EXPENSE, amount="99", date="05-06-2026", category="Qera"),
            make_transaction(EXPENSE, amount="99", date="05-07-2026", category="Ushqim"),
        ]
        assert spent_in_month(items, "Ushqim", 2026, 6) == Decimal("50")

    def test_income_never_counts_against_a_budget(self):
        items = [make_transaction(INCOME, amount="500", date="05-06-2026", category="Ushqim")]
        assert spent_in_month(items, "Ushqim", 2026, 6) == Decimal("0.00")

    def test_no_matching_transactions(self):
        assert spent_in_month([], "Ushqim", 2026, 6) == Decimal("0.00")


class TestBudgetStatus:
    def test_remaining(self):
        status = status_for(
            make_budget("Ushqim", "200"),
            [make_transaction(EXPENSE, amount="50", date="05-06-2026", category="Ushqim")],
            2026,
            6,
        )
        assert status.remaining == Decimal("150")

    def test_remaining_goes_negative_when_over(self):
        status = status_for(
            make_budget("Ushqim", "100"),
            [make_transaction(EXPENSE, amount="150", date="05-06-2026", category="Ushqim")],
            2026,
            6,
        )
        assert status.remaining == Decimal("-50")
        assert status.overspent == Decimal("50")

    def test_overspent_is_zero_when_within_budget(self):
        status = status_for(
            make_budget("Ushqim", "100"),
            [make_transaction(EXPENSE, amount="40", date="05-06-2026", category="Ushqim")],
            2026,
            6,
        )
        assert status.overspent == Decimal("0.00")

    @pytest.mark.parametrize(
        "spent,expected",
        [
            ("10", OK),  # 10%
            ("79", OK),  # just below the 80% threshold
            ("80", NEAR),  # exactly at it
            ("95", NEAR),
            ("100", NEAR),  # exactly on budget is not yet over
            ("101", OVER),
        ],
    )
    def test_states(self, spent, expected):
        status = status_for(
            make_budget("Ushqim", "100"),
            [make_transaction(EXPENSE, amount=spent, date="05-06-2026", category="Ushqim")],
            2026,
            6,
        )
        assert status.state == expected

    def test_percent_used(self):
        status = status_for(
            make_budget("Ushqim", "200"),
            [make_transaction(EXPENSE, amount="50", date="05-06-2026", category="Ushqim")],
            2026,
            6,
        )
        assert status.percent_used == Decimal("25")


class TestAllStatuses:
    def test_worst_first(self):
        budgets = [make_budget("Ushqim", "100"), make_budget("Qera", "100")]
        items = [
            make_transaction(EXPENSE, amount="10", date="05-06-2026", category="Ushqim"),
            make_transaction(EXPENSE, amount="90", date="05-06-2026", category="Qera"),
        ]
        statuses = all_statuses(budgets, items, 2026, 6)
        assert statuses[0].category == "Qera"

    def test_empty_budgets(self):
        assert all_statuses([], [], 2026, 6) == []


class TestCheckAfterAdding:
    def test_warns_when_over(self):
        budgets = [make_budget("Ushqim", "100")]
        transaction = make_transaction(EXPENSE, amount="150", date="05-06-2026", category="Ushqim")
        status = check_after_adding(budgets, [transaction], transaction)
        assert status is not None and status.state == OVER

    def test_warns_when_near(self):
        budgets = [make_budget("Ushqim", "100")]
        transaction = make_transaction(EXPENSE, amount="85", date="05-06-2026", category="Ushqim")
        assert check_after_adding(budgets, [transaction], transaction).state == NEAR

    def test_silent_when_well_within_budget(self):
        budgets = [make_budget("Ushqim", "100")]
        transaction = make_transaction(EXPENSE, amount="10", date="05-06-2026", category="Ushqim")
        assert check_after_adding(budgets, [transaction], transaction) is None

    def test_silent_for_income(self):
        budgets = [make_budget("Paga", "100")]
        transaction = make_transaction(INCOME, amount="5000", date="05-06-2026", category="Paga")
        assert check_after_adding(budgets, [transaction], transaction) is None

    def test_silent_for_unbudgeted_category(self):
        transaction = make_transaction(
            EXPENSE, amount="9999", date="05-06-2026", category="Argetim"
        )
        assert check_after_adding([], [transaction], transaction) is None

    def test_counts_earlier_spending_in_the_same_month(self):
        """The warning must consider the whole month, not just this one entry."""
        budgets = [make_budget("Ushqim", "100")]
        earlier = make_transaction(EXPENSE, amount="80", date="01-06-2026", category="Ushqim")
        latest = make_transaction(EXPENSE, amount="30", date="15-06-2026", category="Ushqim")
        status = check_after_adding(budgets, [earlier, latest], latest)
        assert status.state == OVER
        assert status.overspent == Decimal("10")


class TestSetBudget:
    def test_adds_a_new_budget(self):
        budgets = []
        set_budget(budgets, "Ushqim", Decimal("200"))
        assert len(budgets) == 1

    def test_updates_an_existing_budget_instead_of_duplicating(self):
        budgets = [make_budget("Ushqim", "100")]
        set_budget(budgets, "Ushqim", Decimal("250"))
        assert len(budgets) == 1
        assert budgets[0].shuma == Decimal("250")

    def test_find_budget(self):
        budgets = [make_budget("Ushqim", "100")]
        assert find_budget(budgets, "Ushqim") is not None
        assert find_budget(budgets, "Qera") is None
