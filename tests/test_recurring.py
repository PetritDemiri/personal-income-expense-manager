"""Tests for recurring transactions.

The month-end cases are the interesting ones: computing each occurrence from
the previous one (rather than from the start date) makes a rule anchored on
the 31st drift permanently to the 28th after one February.
"""

import datetime
from decimal import Decimal

import pytest

from personal_finance.config import EXPENSE, INCOME
from personal_finance.dates import add_months, format_date
from personal_finance.recurring import (
    FREQUENCIES,
    due_occurrences,
    generate_due,
    next_occurrence,
)

from .conftest import make_rule


class TestAddMonths:
    def test_simple_advance(self):
        assert add_months(datetime.date(2026, 1, 15), 1) == datetime.date(2026, 2, 15)

    def test_year_rollover(self):
        assert add_months(datetime.date(2026, 12, 10), 1) == datetime.date(2027, 1, 10)

    def test_multiple_years(self):
        assert add_months(datetime.date(2026, 3, 5), 24) == datetime.date(2028, 3, 5)

    def test_clamps_to_short_month(self):
        assert add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)

    def test_clamps_to_leap_february(self):
        assert add_months(datetime.date(2024, 1, 31), 1) == datetime.date(2024, 2, 29)

    def test_thirty_day_month(self):
        assert add_months(datetime.date(2026, 1, 31), 3) == datetime.date(2026, 4, 30)

    def test_no_permanent_drift_from_the_anchor(self):
        """The critical property: February must not shorten every later month."""
        start = datetime.date(2026, 1, 31)
        days = [add_months(start, k).day for k in range(6)]
        assert days == [31, 28, 31, 30, 31, 30]


class TestDueOccurrences:
    def test_generates_everything_up_to_today(self):
        rule = make_rule(start="15-05-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 8, 7))
        assert [format_date(d) for d in occurrences] == [
            "15-05-2026",
            "15-06-2026",
            "15-07-2026",
        ]

    def test_excludes_future_occurrences(self):
        rule = make_rule(start="15-05-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 8, 7))
        assert datetime.date(2026, 8, 15) not in occurrences

    def test_nothing_due_when_already_generated(self):
        rule = make_rule(start="15-05-2026", last="15-07-2026")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == []

    def test_resumes_from_last_generated(self):
        rule = make_rule(start="15-01-2026", last="15-03-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 6, 1))
        assert [format_date(d) for d in occurrences] == [
            "15-04-2026",
            "15-05-2026",
        ]

    def test_start_date_in_the_future_yields_nothing(self):
        rule = make_rule(start="01-12-2026")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == []

    def test_start_date_exactly_today_is_due(self):
        rule = make_rule(start="07-08-2026")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == [datetime.date(2026, 8, 7)]

    def test_unknown_frequency_yields_nothing(self):
        rule = make_rule(frequency="cdo-hene")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == []

    def test_invalid_start_date_yields_nothing(self):
        rule = make_rule(start="garbage")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == []

    @pytest.mark.parametrize(
        "frequency,expected_count",
        [
            ("javore", 6),  # 01-07, 08-07, 15-07, 22-07, 29-07, 05-08
            ("mujore", 2),  # 01-07, 01-08
            ("vjetore", 1),  # 01-07-2026 only
        ],
    )
    def test_each_frequency(self, frequency, expected_count):
        rule = make_rule(frequency=frequency, start="01-07-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 8, 7))
        assert len(occurrences) == expected_count

    def test_month_end_rule_over_several_months(self):
        rule = make_rule(start="31-01-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 5, 15))
        assert [format_date(d) for d in occurrences] == [
            "31-01-2026",
            "28-02-2026",
            "31-03-2026",
            "30-04-2026",
        ]


class TestNextOccurrence:
    def test_first_when_nothing_generated(self):
        rule = make_rule(start="15-05-2026")
        assert next_occurrence(rule) == datetime.date(2026, 5, 15)

    def test_after_last_generated(self):
        rule = make_rule(start="15-05-2026", last="15-07-2026")
        assert next_occurrence(rule) == datetime.date(2026, 8, 15)

    def test_none_for_broken_rule(self):
        assert next_occurrence(make_rule(frequency="nonsense")) is None


class TestGenerateDue:
    def test_appends_transactions_and_updates_the_rule(self):
        rules = [make_rule(start="01-06-2026", amount="300.00")]
        transactions = []
        generated = generate_due(rules, transactions, datetime.date(2026, 8, 7))

        assert len(generated) == 3
        assert len(transactions) == 3
        assert rules[0].data_e_fundit == "01-08-2026"

    def test_is_idempotent(self):
        """Running twice must not duplicate anything."""
        rules = [make_rule(start="01-06-2026")]
        transactions = []
        as_of = datetime.date(2026, 8, 7)

        generate_due(rules, transactions, as_of)
        first_count = len(transactions)
        generate_due(rules, transactions, as_of)

        assert len(transactions) == first_count

    def test_generated_transactions_carry_rule_details(self):
        rules = [make_rule(INCOME, "Paga", "1200.00", "Paga", start="01-07-2026")]
        transactions = []
        generate_due(rules, transactions, datetime.date(2026, 7, 15))

        created = transactions[0]
        assert created.lloji == INCOME
        assert created.pershkrimi == "Paga"
        assert created.shuma == Decimal("1200.00")
        assert created.kategoria == "Paga"
        assert created.data == "01-07-2026"

    def test_multiple_rules_all_run(self):
        rules = [
            make_rule(EXPENSE, "Qera", start="01-07-2026"),
            make_rule(INCOME, "Paga", start="05-07-2026"),
        ]
        transactions = []
        generate_due(rules, transactions, datetime.date(2026, 7, 31))
        assert len(transactions) == 2

    def test_broken_rule_does_not_stop_the_others(self):
        rules = [
            make_rule(frequency="nonsense", start="01-07-2026"),
            make_rule(EXPENSE, "Qera", start="01-07-2026"),
        ]
        transactions = []
        generate_due(rules, transactions, datetime.date(2026, 7, 31))
        assert len(transactions) == 1


def test_all_frequencies_are_callable():
    """Guards against a typo in the FREQUENCIES table."""
    start = datetime.date(2026, 1, 1)
    for name, advance in FREQUENCIES.items():
        assert isinstance(advance(start, 1), datetime.date), name
