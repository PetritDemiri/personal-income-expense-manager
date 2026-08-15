"""Tests for totals, filtering, sorting, and reports.

The balance tests are deliberately blunt: this project shipped twice with
income silently counted as zero because a comparison string did not match.
"""

import datetime
from decimal import Decimal

import pytest

from personal_finance.config import EXPENSE, INCOME
from personal_finance.reports import (
    calculate_totals,
    filter_by_dates,
    filter_by_month,
    month_report,
    percent_change,
    search,
    sort_by_date,
    totals_by_category,
)

from .conftest import make_transaction


class TestCalculateTotals:
    def test_income_is_actually_counted(self, sample_transactions):
        """The regression test for the bug that hit this project twice."""
        totals = calculate_totals(sample_transactions)
        assert totals.income == Decimal("1200.00")
        assert totals.income != Decimal("0.00")

    def test_expenses_are_counted(self, sample_transactions):
        assert calculate_totals(sample_transactions).expenses == Decimal("510.50")

    def test_balance_is_income_minus_expenses(self, sample_transactions):
        totals = calculate_totals(sample_transactions)
        assert totals.balance == Decimal("689.50")

    def test_count(self, sample_transactions):
        assert calculate_totals(sample_transactions).count == 5

    def test_empty_list(self):
        totals = calculate_totals([])
        assert totals.income == Decimal("0.00")
        assert totals.expenses == Decimal("0.00")
        assert totals.balance == Decimal("0.00")
        assert totals.count == 0

    def test_income_only(self):
        totals = calculate_totals([make_transaction(INCOME, amount="100")])
        assert totals.balance == Decimal("100")

    def test_negative_balance_when_overspending(self):
        totals = calculate_totals(
            [
                make_transaction(INCOME, amount="50"),
                make_transaction(EXPENSE, amount="80"),
            ]
        )
        assert totals.balance == Decimal("-30")

    def test_no_floating_point_drift(self):
        """0.1 + 0.2 must be exactly 0.3, which floats cannot promise."""
        totals = calculate_totals(
            [
                make_transaction(EXPENSE, amount="0.10"),
                make_transaction(EXPENSE, amount="0.20"),
            ]
        )
        assert totals.expenses == Decimal("0.30")

    def test_many_small_amounts_stay_exact(self):
        totals = calculate_totals([make_transaction(EXPENSE, amount="0.01") for _ in range(100)])
        assert totals.expenses == Decimal("1.00")


class TestSortByDate:
    def test_sorts_chronologically(self):
        items = [
            make_transaction(date="15-07-2026"),
            make_transaction(date="01-06-2026"),
            make_transaction(date="30-06-2026"),
        ]
        assert [x.data for x in sort_by_date(items)] == [
            "01-06-2026",
            "30-06-2026",
            "15-07-2026",
        ]

    def test_sorts_across_years(self):
        items = [
            make_transaction(date="01-01-2027"),
            make_transaction(date="31-12-2026"),
        ]
        assert sort_by_date(items)[0].data == "31-12-2026"

    def test_does_not_mutate_the_input(self):
        items = [make_transaction(date="15-07-2026"), make_transaction(date="01-06-2026")]
        original = list(items)
        sort_by_date(items)
        assert items == original


class TestFilterByDates:
    def test_single_day(self, sample_transactions):
        target = datetime.date(2026, 6, 2)
        matches = filter_by_dates(sample_transactions, target, target)
        assert len(matches) == 1
        assert matches[0].pershkrimi == "Qera"

    def test_range_includes_both_bounds(self, sample_transactions):
        matches = filter_by_dates(
            sample_transactions, datetime.date(2026, 6, 2), datetime.date(2026, 7, 5)
        )
        descriptions = [x.pershkrimi for x in matches]
        assert "Qera" in descriptions  # exactly on the start bound
        assert "Bonus" in descriptions  # exactly on the end bound
        assert len(matches) == 3

    def test_open_ended_start(self, sample_transactions):
        matches = filter_by_dates(sample_transactions, start=datetime.date(2026, 7, 1))
        assert len(matches) == 2

    def test_open_ended_end(self, sample_transactions):
        matches = filter_by_dates(sample_transactions, end=datetime.date(2026, 6, 30))
        assert len(matches) == 3

    def test_no_bounds_returns_everything(self, sample_transactions):
        assert len(filter_by_dates(sample_transactions)) == 5

    def test_empty_range_returns_nothing(self, sample_transactions):
        matches = filter_by_dates(
            sample_transactions, datetime.date(2030, 1, 1), datetime.date(2030, 12, 31)
        )
        assert matches == []

    def test_unparseable_dates_are_skipped_not_fatal(self):
        items = [make_transaction(date="garbage"), make_transaction(date="01-06-2026")]
        matches = filter_by_dates(items, datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        assert len(matches) == 1


class TestFilterByMonth:
    def test_selects_one_month(self, sample_transactions):
        assert len(filter_by_month(sample_transactions, 2026, 6)) == 3

    def test_month_boundaries_are_inclusive(self):
        items = [
            make_transaction(date="01-06-2026"),
            make_transaction(date="30-06-2026"),
            make_transaction(date="01-07-2026"),
        ]
        assert len(filter_by_month(items, 2026, 6)) == 2

    def test_february_in_a_leap_year(self):
        items = [make_transaction(date="29-02-2024")]
        assert len(filter_by_month(items, 2024, 2)) == 1


class TestSearch:
    def test_matches_description(self, sample_transactions):
        assert len(search(sample_transactions, "Paga")) == 1

    def test_matches_category(self, sample_transactions):
        assert len(search(sample_transactions, "Transport")) == 1

    def test_is_case_insensitive(self, sample_transactions):
        assert len(search(sample_transactions, "QERA")) == 1

    def test_matches_partial_words(self, sample_transactions):
        assert len(search(sample_transactions, "Ushq")) == 1

    @pytest.mark.parametrize("term", ["", "   ", None])
    def test_empty_term_matches_nothing(self, sample_transactions, term):
        assert search(sample_transactions, term) == []


class TestTotalsByCategory:
    def test_groups_and_sums(self):
        items = [
            make_transaction(EXPENSE, amount="10", category="Ushqim"),
            make_transaction(EXPENSE, amount="15", category="Ushqim"),
            make_transaction(EXPENSE, amount="30", category="Qera"),
        ]
        assert totals_by_category(items, EXPENSE) == [
            ("Qera", Decimal("30")),
            ("Ushqim", Decimal("25")),
        ]

    def test_largest_first(self, sample_transactions):
        rows = totals_by_category(sample_transactions, EXPENSE)
        assert [amount for _, amount in rows] == sorted(
            [amount for _, amount in rows], reverse=True
        )

    def test_only_the_requested_type(self, sample_transactions):
        categories = [c for c, _ in totals_by_category(sample_transactions, INCOME)]
        assert set(categories) == {"Paga", "Bonus"}


class TestPercentChange:
    def test_increase(self):
        assert percent_change(Decimal("150"), Decimal("100")) == Decimal("50")

    def test_decrease(self):
        assert percent_change(Decimal("50"), Decimal("100")) == Decimal("-50")

    def test_zero_previous_is_undefined(self):
        assert percent_change(Decimal("100"), Decimal("0")) is None


class TestMonthlyReport:
    def test_totals_for_the_month_only(self, sample_transactions):
        report = month_report(sample_transactions, 2026, 6)
        assert report.totals.income == Decimal("1000.00")
        assert report.totals.expenses == Decimal("450.50")

    def test_compares_with_the_previous_month(self, sample_transactions):
        report = month_report(sample_transactions, 2026, 7)
        assert report.previous_totals.income == Decimal("1000.00")
        assert report.has_previous

    def test_expense_change_percentage(self, sample_transactions):
        report = month_report(sample_transactions, 2026, 7)
        # 60.00 this month against 450.50 last month.
        assert report.expense_change < 0

    def test_empty_month(self, sample_transactions):
        report = month_report(sample_transactions, 2030, 1)
        assert report.is_empty
        assert not report.has_previous

    def test_january_looks_back_to_december(self):
        items = [
            make_transaction(date="15-12-2025", amount="100"),
            make_transaction(date="15-01-2026", amount="50"),
        ]
        report = month_report(items, 2026, 1)
        assert report.previous_totals.expenses == Decimal("100")

    def test_category_breakdowns_are_present(self, sample_transactions):
        report = month_report(sample_transactions, 2026, 6)
        assert dict(report.expenses_by_category) == {
            "Qera": Decimal("300.00"),
            "Ushqim": Decimal("150.50"),
        }
