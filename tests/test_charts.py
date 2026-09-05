"""Tests for the charts.

Bars are scaled against the largest value in their own chart, so the biggest
always fills the width. That makes bars comparable within a chart and never
between two - which is the right trade, but only if the scaling is right, so
it is what most of these check.
"""

import datetime
from decimal import Decimal

import pytest

from personal_finance.charts import (
    DEFAULT_SPAN,
    SPANS,
    Bar,
    account_bars,
    category_bars,
    has_data,
    month_span,
    monthly_bars,
    percent,
)
from personal_finance.display import BAR_FULL, BAR_WIDTH, bar_of
from personal_finance.schema import EXPENSE, INCOME

from .conftest import make_view


@pytest.fixture
def sample():
    return [
        make_view(EXPENSE, "Qera", "300.00", "02-08-2026", category="Qera"),
        make_view(EXPENSE, "Ushqime", "150.00", "10-08-2026", category="Ushqim"),
        make_view(EXPENSE, "Benzine", "50.00", "12-08-2026", category="Transport"),
        make_view(INCOME, "Paga", "1000.00", "01-08-2026", category="Paga"),
        make_view(EXPENSE, "Qera korrik", "200.00", "02-07-2026", category="Qera"),
        make_view(INCOME, "Paga korrik", "800.00", "01-07-2026", category="Paga"),
    ]


class TestCategoryBars:
    def test_largest_first(self, sample):
        bars = category_bars(sample, EXPENSE, 2026, 8)
        assert [b.label for b in bars] == ["Qera", "Ushqim", "Transport"]

    def test_the_largest_bar_is_full(self, sample):
        assert category_bars(sample, EXPENSE, 2026, 8)[0].fraction == 1

    def test_bars_scale_against_the_largest(self, sample):
        """150 against 300 is half the width."""
        bars = category_bars(sample, EXPENSE, 2026, 8)
        assert bars[1].fraction == Decimal("0.5")

    def test_share_is_of_the_total_not_the_largest(self, sample):
        """A different question from bar length, and worth showing beside it."""
        bars = category_bars(sample, EXPENSE, 2026, 8)
        assert percent(bars[0].share) == 60  # 300 of 500

    def test_only_the_requested_month(self, sample):
        bars = category_bars(sample, EXPENSE, 2026, 7)
        assert [b.label for b in bars] == ["Qera"]
        assert bars[0].amount == Decimal("200.00")

    def test_only_the_requested_kind(self, sample):
        assert [b.label for b in category_bars(sample, INCOME, 2026, 8)] == ["Paga"]

    def test_every_month_when_none_is_given(self, sample):
        bars = category_bars(sample, EXPENSE)
        assert {b.label: b.amount for b in bars}["Qera"] == Decimal("500.00")

    def test_a_limit_keeps_the_largest(self, sample):
        bars = category_bars(sample, EXPENSE, 2026, 8, limit=2)
        assert [b.label for b in bars] == ["Qera", "Ushqim"]

    def test_an_empty_month(self, sample):
        assert not has_data(category_bars(sample, EXPENSE, 2030, 1))

    def test_no_transactions_at_all(self):
        assert category_bars([], EXPENSE, 2026, 8) == []


class TestMonthSpan:
    def test_it_ends_with_the_current_month(self):
        months = month_span(datetime.date(2026, 8, 15), 3)
        assert months[-1] == (2026, 8)

    def test_oldest_first(self):
        assert month_span(datetime.date(2026, 8, 15), 3) == [(2026, 6), (2026, 7), (2026, 8)]

    def test_it_crosses_a_year(self):
        assert month_span(datetime.date(2026, 2, 15), 4)[0] == (2025, 11)

    @pytest.mark.parametrize("span", SPANS)
    def test_each_offered_span(self, span):
        assert len(month_span(datetime.date(2026, 8, 15), span)) == span

    def test_the_default_span_is_offered(self):
        assert DEFAULT_SPAN in SPANS


class TestMonthlyBars:
    def test_one_row_per_month(self, sample):
        months, income, expenses = monthly_bars(sample, datetime.date(2026, 8, 15), 3)
        assert len(months) == len(income) == len(expenses) == 3

    def test_the_labels_read_as_months(self, sample):
        _months, income, _ = monthly_bars(sample, datetime.date(2026, 8, 15), 3)
        assert income[-1].label == "08-2026"

    def test_income_and_expenses_are_separated(self, sample):
        _months, income, expenses = monthly_bars(sample, datetime.date(2026, 8, 15), 2)
        assert income[-1].amount == Decimal("1000.00")
        assert expenses[-1].amount == Decimal("500.00")

    def test_both_series_share_one_scale(self, sample):
        """Otherwise a month's spending would look equal to its income."""
        _months, income, expenses = monthly_bars(sample, datetime.date(2026, 8, 15), 2)
        assert income[-1].fraction == 1
        assert expenses[-1].fraction == Decimal("0.5")

    def test_a_month_with_nothing_is_still_shown(self, sample):
        """A gap in the data is itself worth seeing."""
        _months, income, _ = monthly_bars(sample, datetime.date(2026, 8, 15), 6)
        assert len(income) == 6
        assert income[0].amount == Decimal("0.00")

    def test_an_empty_history(self):
        _months, income, expenses = monthly_bars([], datetime.date(2026, 8, 15), 3)
        assert not has_data(income)
        assert not has_data(expenses)


class TestAccountBars:
    def make(self, name, balance):
        class FakeBalance:
            def __init__(self, name, balance):
                self.name = name
                self.balance = balance

        return FakeBalance(name, Decimal(balance))

    def test_one_bar_per_account(self):
        bars = account_bars([self.make("Banka", "500"), self.make("Kesh", "100")])
        assert [b.label for b in bars] == ["Banka", "Kesh"]

    def test_a_negative_balance_keeps_its_sign(self):
        """A card in debt is a real state; hiding the sign would misreport it."""
        bars = account_bars([self.make("Karta", "-250")])
        assert bars[0].amount == Decimal("-250")

    def test_bars_scale_on_magnitude(self):
        bars = account_bars([self.make("Banka", "500"), self.make("Karta", "-250")])
        assert bars[0].fraction == 1
        assert bars[1].fraction == Decimal("0.5")

    def test_no_accounts(self):
        assert account_bars([]) == []


class TestBarRendering:
    def test_a_full_bar(self):
        assert bar_of(Decimal("1")) == BAR_FULL * BAR_WIDTH

    def test_an_empty_bar(self):
        assert bar_of(Decimal("0")).strip() == ""

    def test_a_half_bar(self):
        assert bar_of(Decimal("0.5")).count(BAR_FULL) == BAR_WIDTH // 2

    def test_every_bar_is_the_same_width(self):
        for fraction in ("0", "0.01", "0.5", "1"):
            assert len(bar_of(Decimal(fraction))) == BAR_WIDTH

    def test_a_tiny_amount_still_shows(self):
        """Rounded down it would draw nothing and look like no data at all."""
        assert bar_of(Decimal("0.001")).count(BAR_FULL) == 1

    def test_a_custom_width(self):
        assert len(bar_of(Decimal("1"), 10)) == 10


class TestPercent:
    def test_it_rounds_to_a_whole_number(self):
        assert percent(Decimal("0.555")) == 56
        assert percent(Decimal("1")) == 100
        assert percent(Decimal("0")) == 0


class TestPrinting:
    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_a_category_chart_prints(self, sample, capsys):
        from personal_finance.display import print_category_chart

        print_category_chart(category_bars(sample, EXPENSE, 2026, 8), "Titulli")
        output = capsys.readouterr().out
        assert "Titulli" in output
        assert BAR_FULL in output
        assert "€300.00" in output

    def test_an_empty_chart_says_so(self, capsys):
        from personal_finance.display import print_category_chart

        print_category_chart([], "Titulli")
        assert "Nuk ka te dhena" in capsys.readouterr().out

    def test_a_monthly_chart_prints_both_series(self, sample, capsys):
        from personal_finance.display import print_monthly_chart

        _months, income, expenses = monthly_bars(sample, datetime.date(2026, 8, 15), 3)
        print_monthly_chart(income, expenses, "Titulli")
        output = capsys.readouterr().out
        assert "Te ardhura" in output
        assert "Shpenzime" in output
        assert "08-2026" in output

    def test_an_account_chart_prints(self, capsys):
        from personal_finance.display import print_account_chart

        bars = TestAccountBars().make("Banka", "500")
        print_account_chart(account_bars([bars]), "Titulli")
        assert "Banka" in capsys.readouterr().out


def test_bar_equality_compares_label_and_amount():
    assert Bar("A", Decimal("1")) == Bar("A", Decimal("1"))
    assert Bar("A", Decimal("1")) != Bar("B", Decimal("1"))
