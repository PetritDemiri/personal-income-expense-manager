"""Tests for totals, filtering, sorting and reports.

The balance tests are deliberately blunt: this project shipped twice with
income silently counted as zero because a comparison did not match, and once
counting transfers as spending.
"""

import datetime
from decimal import Decimal

import pytest

from personal_finance.reports import (
    OTHER,
    calculate_totals,
    filter_by_dates,
    filter_by_month,
    has_accounts_used,
    has_subcategories,
    month_report,
    ordered_options,
    percent_change,
    search,
    sort_by_date,
    totals_by_category,
    totals_by_subcategory,
)
from personal_finance.schema import EXPENSE, INCOME, TRANSFER

from .conftest import make_view


@pytest.fixture
def sample():
    return [
        make_view(INCOME, "Paga", "1000.00", "01-06-2026", "Paga"),
        make_view(EXPENSE, "Qera", "300.00", "02-06-2026", "Qera"),
        make_view(EXPENSE, "Ushqime", "150.50", "15-06-2026", "Ushqim", "Dyqan"),
        make_view(INCOME, "Bonus", "200.00", "05-07-2026", "Bonus"),
        make_view(EXPENSE, "Benzine", "60.00", "10-07-2026", "Transport"),
    ]


class TestCalculateTotals:
    def test_income_is_actually_counted(self, sample):
        """The regression test for the bug that hit this project twice."""
        totals = calculate_totals(sample)
        assert totals.income == Decimal("1200.00")
        assert totals.income != Decimal("0.00")

    def test_expenses_are_counted(self, sample):
        assert calculate_totals(sample).expenses == Decimal("510.50")

    def test_balance_is_income_minus_expenses(self, sample):
        assert calculate_totals(sample).balance == Decimal("689.50")

    def test_count(self, sample):
        assert calculate_totals(sample).count == 5

    def test_empty(self):
        totals = calculate_totals([])
        assert totals.income == Decimal("0.00")
        assert totals.balance == Decimal("0.00")
        assert totals.count == 0

    def test_negative_balance_when_overspending(self):
        totals = calculate_totals([make_view(INCOME, amount="50"), make_view(EXPENSE, amount="80")])
        assert totals.balance == Decimal("-30")

    def test_transfers_count_as_neither(self):
        """An else branch here would file every transfer as spending."""
        totals = calculate_totals(
            [
                make_view(INCOME, amount="1000"),
                make_view(EXPENSE, amount="300"),
                make_view(TRANSFER, amount="200", category=None),
            ]
        )
        assert totals.income == Decimal("1000")
        assert totals.expenses == Decimal("300")

    def test_a_transfer_alone_leaves_the_balance_at_zero(self):
        totals = calculate_totals([make_view(TRANSFER, amount="500", category=None)])
        assert totals.balance == Decimal("0.00")

    def test_no_floating_point_drift(self):
        totals = calculate_totals(
            [make_view(EXPENSE, amount="0.10"), make_view(EXPENSE, amount="0.20")]
        )
        assert totals.expenses == Decimal("0.30")

    def test_many_small_amounts_stay_exact(self):
        totals = calculate_totals([make_view(EXPENSE, amount="0.01") for _ in range(100)])
        assert totals.expenses == Decimal("1.00")


class TestSortByDate:
    def test_sorts_chronologically(self):
        items = [
            make_view(occurred_on="15-07-2026"),
            make_view(occurred_on="01-06-2026"),
            make_view(occurred_on="30-06-2026"),
        ]
        assert [x.occurred_on for x in sort_by_date(items)] == [
            "01-06-2026",
            "30-06-2026",
            "15-07-2026",
        ]

    def test_sorts_across_years(self):
        items = [make_view(occurred_on="01-01-2027"), make_view(occurred_on="31-12-2026")]
        assert sort_by_date(items)[0].occurred_on == "31-12-2026"

    def test_does_not_mutate_the_input(self):
        items = [make_view(occurred_on="15-07-2026"), make_view(occurred_on="01-06-2026")]
        original = list(items)
        sort_by_date(items)
        assert items == original


class TestFilterByDates:
    def test_single_day(self, sample):
        target = datetime.date(2026, 6, 2)
        matches = filter_by_dates(sample, target, target)
        assert len(matches) == 1
        assert matches[0].description == "Qera"

    def test_range_includes_both_bounds(self, sample):
        matches = filter_by_dates(sample, datetime.date(2026, 6, 2), datetime.date(2026, 7, 5))
        descriptions = [x.description for x in matches]
        assert "Qera" in descriptions
        assert "Bonus" in descriptions
        assert len(matches) == 3

    def test_open_ended_start(self, sample):
        assert len(filter_by_dates(sample, start=datetime.date(2026, 7, 1))) == 2

    def test_open_ended_end(self, sample):
        assert len(filter_by_dates(sample, end=datetime.date(2026, 6, 30))) == 3

    def test_no_bounds_returns_everything(self, sample):
        assert len(filter_by_dates(sample)) == 5

    def test_unparseable_dates_are_skipped(self):
        items = [make_view(occurred_on="garbage"), make_view(occurred_on="01-06-2026")]
        matches = filter_by_dates(items, datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        assert len(matches) == 1


class TestFilterByMonth:
    def test_selects_one_month(self, sample):
        assert len(filter_by_month(sample, 2026, 6)) == 3

    def test_boundaries_are_inclusive(self):
        items = [
            make_view(occurred_on="01-06-2026"),
            make_view(occurred_on="30-06-2026"),
            make_view(occurred_on="01-07-2026"),
        ]
        assert len(filter_by_month(items, 2026, 6)) == 2

    def test_february_in_a_leap_year(self):
        assert len(filter_by_month([make_view(occurred_on="29-02-2024")], 2024, 2)) == 1


class TestSearch:
    def test_matches_description(self, sample):
        assert len(search(sample, "Ushqime")) == 1

    def test_matches_category(self, sample):
        assert len(search(sample, "Transport")) == 1

    def test_matches_subcategory(self, sample):
        assert len(search(sample, "Dyqan")) == 1

    def test_is_case_insensitive(self, sample):
        assert len(search(sample, "QERA")) == 1

    def test_matches_partial_words(self, sample):
        # One row: "Ushqime" in the description and "Ushqim" as its category.
        assert len(search(sample, "Ushq")) == 1

    @pytest.mark.parametrize("term", ["", "   ", None])
    def test_empty_term_matches_nothing(self, sample, term):
        assert search(sample, term) == []

    def test_handles_a_missing_category(self):
        assert search([make_view(category=None)], "anything") == []


class TestTotalsByCategory:
    def test_groups_and_sums(self):
        items = [
            make_view(EXPENSE, amount="10", category="Ushqim"),
            make_view(EXPENSE, amount="15", category="Ushqim"),
            make_view(EXPENSE, amount="30", category="Qera"),
        ]
        assert totals_by_category(items, EXPENSE) == [
            ("Qera", Decimal("30")),
            ("Ushqim", Decimal("25")),
        ]

    def test_largest_first(self, sample):
        rows = totals_by_category(sample, EXPENSE)
        amounts = [amount for _, amount in rows]
        assert amounts == sorted(amounts, reverse=True)

    def test_only_the_requested_kind(self, sample):
        names = [name for name, _ in totals_by_category(sample, INCOME)]
        assert set(names) == {"Paga", "Bonus"}

    def test_uncategorised_groups_under_none_and_sorts_last(self):
        items = [
            make_view(EXPENSE, amount="1000", category=None),
            make_view(EXPENSE, amount="5", category="Ushqim"),
        ]
        rows = totals_by_category(items, EXPENSE)
        assert rows[-1][0] is None


class TestTotalsBySubcategory:
    def test_groups_and_sums(self):
        items = [
            make_view(EXPENSE, amount="30", category="Ushqim", subcategory="Dyqan"),
            make_view(EXPENSE, amount="20", category="Ushqim", subcategory="Dyqan"),
            make_view(EXPENSE, amount="40", category="Ushqim", subcategory="Restorant"),
        ]
        rows = totals_by_subcategory(items, EXPENSE, "Ushqim")
        assert rows[0] == ("Dyqan", Decimal("50"))

    def test_unsubcategorised_sorts_last(self):
        items = [
            make_view(EXPENSE, amount="1000", category="Ushqim", subcategory=None),
            make_view(EXPENSE, amount="5", category="Ushqim", subcategory="Dyqan"),
        ]
        assert totals_by_subcategory(items, EXPENSE, "Ushqim")[-1][0] is None

    def test_ignores_other_categories(self):
        items = [
            make_view(EXPENSE, amount="50", category="Ushqim", subcategory="Dyqan"),
            make_view(EXPENSE, amount="20", category="Transport", subcategory="Taksi"),
        ]
        assert len(totals_by_subcategory(items, EXPENSE, "Ushqim")) == 1


class TestPresenceHelpers:
    def test_has_subcategories(self):
        assert not has_subcategories([make_view(), make_view()])
        assert has_subcategories([make_view(), make_view(subcategory="Dyqan")])

    def test_has_accounts_used(self):
        assert not has_accounts_used([make_view()])
        assert has_accounts_used([make_view(account="Kesh")])
        assert has_accounts_used([make_view(to_account="Banka")])


class TestPercentChange:
    def test_increase(self):
        assert percent_change(Decimal("150"), Decimal("100")) == Decimal("50")

    def test_decrease(self):
        assert percent_change(Decimal("50"), Decimal("100")) == Decimal("-50")

    def test_zero_previous_is_undefined(self):
        assert percent_change(Decimal("100"), Decimal("0")) is None


class TestMonthlyReport:
    def test_totals_for_the_month_only(self, sample):
        report = month_report(sample, 2026, 6)
        assert report.totals.income == Decimal("1000.00")
        assert report.totals.expenses == Decimal("450.50")

    def test_compares_with_the_previous_month(self, sample):
        report = month_report(sample, 2026, 7)
        assert report.previous_totals.income == Decimal("1000.00")
        assert report.has_previous

    def test_expense_change_is_negative_when_spending_falls(self, sample):
        assert month_report(sample, 2026, 7).expense_change < 0

    def test_empty_month(self, sample):
        report = month_report(sample, 2030, 1)
        assert report.is_empty
        assert not report.has_previous

    def test_january_looks_back_to_december(self):
        items = [
            make_view(occurred_on="15-12-2025", amount="100"),
            make_view(occurred_on="15-01-2026", amount="50"),
        ]
        assert month_report(items, 2026, 1).previous_totals.expenses == Decimal("100")

    def test_category_breakdowns_are_present(self, sample):
        report = month_report(sample, 2026, 6)
        assert dict(report.expenses_by_category) == {
            "Qera": Decimal("300.00"),
            "Ushqim": Decimal("150.50"),
        }


class TestOrderedOptions:
    def test_catch_all_last(self):
        assert ordered_options(["A", OTHER, "B"]) == ["A", "B", OTHER]

    def test_sorts_alphabetically(self):
        assert ordered_options(["C", "A", "B"]) == ["A", "B", "C"]

    def test_albanian_letters_sort_in_alphabet_order(self):
        assert ordered_options(["Zarf", "Ëmbëlsira", "Çaji", "Abonim"]) == [
            "Abonim",
            "Çaji",
            "Ëmbëlsira",
            "Zarf",
        ]

    def test_digraphs_follow_their_base_letter(self):
        assert ordered_options(["Shendetesi", "Sende", "Sy"]) == [
            "Sende",
            "Sy",
            "Shendetesi",
        ]

    def test_duplicate_catch_all_appears_once(self):
        assert ordered_options(["A", OTHER, OTHER]) == ["A", OTHER]

    def test_empty(self):
        assert ordered_options([]) == []
