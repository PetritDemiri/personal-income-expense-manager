"""Tests for recurring transactions.

The month-end cases matter most: computing each occurrence from the previous
one, rather than from the start date, makes a rule anchored on the 31st drift
permanently to the 28th after one February.

The atomicity test is the reason version 3 exists. With two CSV files a crash
between writing the transactions and advancing the rules regenerated every
occurrence on the next run.
"""

import datetime
from decimal import Decimal

import pytest

from personal_finance.dates import add_months, format_date
from personal_finance.recurring import (
    FREQUENCIES,
    due_occurrences,
    generate_due,
    next_occurrence,
)
from personal_finance.schema import EXPENSE, INCOME

from .conftest import make_rule


class TestAddMonths:
    def test_simple_advance(self):
        assert add_months(datetime.date(2026, 1, 15), 1) == datetime.date(2026, 2, 15)

    def test_year_rollover(self):
        assert add_months(datetime.date(2026, 12, 10), 1) == datetime.date(2027, 1, 10)

    def test_clamps_to_short_month(self):
        assert add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)

    def test_clamps_to_leap_february(self):
        assert add_months(datetime.date(2024, 1, 31), 1) == datetime.date(2024, 2, 29)

    def test_no_permanent_drift_from_the_anchor(self):
        """February must not shorten every later month."""
        start = datetime.date(2026, 1, 31)
        assert [add_months(start, k).day for k in range(6)] == [31, 28, 31, 30, 31, 30]


class TestDueOccurrences:
    def test_generates_everything_up_to_today(self):
        rule = make_rule(starts_on="15-05-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 8, 7))
        assert [format_date(d) for d in occurrences] == [
            "15-05-2026",
            "15-06-2026",
            "15-07-2026",
        ]

    def test_excludes_future_occurrences(self):
        rule = make_rule(starts_on="15-05-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 8, 7))
        assert datetime.date(2026, 8, 15) not in occurrences

    def test_nothing_due_when_already_generated(self):
        rule = make_rule(starts_on="15-05-2026", generated_upto="15-07-2026")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == []

    def test_resumes_from_the_last_generated(self):
        rule = make_rule(starts_on="15-01-2026", generated_upto="15-03-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 6, 1))
        assert [format_date(d) for d in occurrences] == ["15-04-2026", "15-05-2026"]

    def test_a_future_start_yields_nothing(self):
        rule = make_rule(starts_on="01-12-2026")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == []

    def test_a_start_exactly_today_is_due(self):
        rule = make_rule(starts_on="07-08-2026")
        assert due_occurrences(rule, datetime.date(2026, 8, 7)) == [datetime.date(2026, 8, 7)]

    def test_an_unknown_frequency_yields_nothing(self):
        assert due_occurrences(make_rule(frequency="cdo-hene"), datetime.date(2026, 8, 7)) == []

    def test_an_invalid_start_yields_nothing(self):
        assert due_occurrences(make_rule(starts_on="garbage"), datetime.date(2026, 8, 7)) == []

    @pytest.mark.parametrize("frequency,expected", [("javore", 6), ("mujore", 2), ("vjetore", 1)])
    def test_each_frequency(self, frequency, expected):
        rule = make_rule(frequency=frequency, starts_on="01-07-2026")
        assert len(due_occurrences(rule, datetime.date(2026, 8, 7))) == expected

    def test_a_month_end_rule_over_several_months(self):
        rule = make_rule(starts_on="31-01-2026")
        occurrences = due_occurrences(rule, datetime.date(2026, 5, 15))
        assert [format_date(d) for d in occurrences] == [
            "31-01-2026",
            "28-02-2026",
            "31-03-2026",
            "30-04-2026",
        ]


class TestNextOccurrence:
    def test_first_when_nothing_generated(self):
        assert next_occurrence(make_rule(starts_on="15-05-2026")) == datetime.date(2026, 5, 15)

    def test_after_the_last_generated(self):
        rule = make_rule(starts_on="15-05-2026", generated_upto="15-07-2026")
        assert next_occurrence(rule) == datetime.date(2026, 8, 15)

    def test_none_for_a_broken_rule(self):
        assert next_occurrence(make_rule(frequency="nonsense")) is None


class TestGenerateDue:
    def test_inserts_and_advances_the_rule(self, db):
        rule_id = db.add_recurring_rule(make_rule(starts_on="01-06-2026"))
        generated = generate_due(db, db.recurring_rules(), datetime.date(2026, 8, 7))

        assert len(generated) == 3
        assert db.count_transactions() == 3
        assert db.recurring_rules()[0].generated_upto == "01-08-2026"
        assert rule_id == db.recurring_rules()[0].id

    def test_is_idempotent(self, db):
        db.add_recurring_rule(make_rule(starts_on="01-06-2026"))
        as_of = datetime.date(2026, 8, 7)
        generate_due(db, db.recurring_rules(), as_of)
        generate_due(db, db.recurring_rules(), as_of)
        assert db.count_transactions() == 3

    def test_generated_transactions_carry_the_rule_details(self, db):
        category_id = db.ensure_category("Paga", INCOME)
        db.add_recurring_rule(
            make_rule(INCOME, "Paga", "1200.00", starts_on="01-07-2026", category_id=category_id)
        )
        generate_due(db, db.recurring_rules(), datetime.date(2026, 7, 15))

        created = db.transactions()[0]
        assert created.kind == INCOME
        assert created.description == "Paga"
        assert created.amount == Decimal("1200.00")
        assert created.category == "Paga"
        assert created.occurred_on == "01-07-2026"

    def test_the_account_is_carried_through(self, db):
        from personal_finance.models import Account

        account_id = db.add_account(Account(name="Banka"))
        db.add_recurring_rule(make_rule(starts_on="01-07-2026", account_id=account_id))
        generate_due(db, db.recurring_rules(), datetime.date(2026, 7, 15))
        assert db.transactions()[0].account == "Banka"

    def test_multiple_rules_all_run(self, db):
        db.add_recurring_rule(make_rule(EXPENSE, "Qera", starts_on="01-07-2026"))
        db.add_recurring_rule(make_rule(INCOME, "Paga", starts_on="05-07-2026"))
        generate_due(db, db.recurring_rules(), datetime.date(2026, 7, 31))
        assert db.count_transactions() == 2

    def test_a_broken_rule_does_not_stop_the_others(self, db):
        db.add_recurring_rule(make_rule(frequency="nonsense", starts_on="01-07-2026"))
        db.add_recurring_rule(make_rule(EXPENSE, "Qera", starts_on="01-07-2026"))
        generate_due(db, db.recurring_rules(), datetime.date(2026, 7, 31))
        assert db.count_transactions() == 1

    def test_nothing_due_writes_nothing(self, db):
        db.add_recurring_rule(make_rule(starts_on="01-12-2026"))
        assert generate_due(db, db.recurring_rules(), datetime.date(2026, 8, 7)) == []
        assert db.count_transactions() == 0


class TestGenerationIsAtomic:
    """The bug version 3 exists to make impossible."""

    def test_a_crash_part_way_rolls_the_whole_run_back(self, db, monkeypatch):
        db.add_recurring_rule(make_rule(starts_on="01-06-2026"))

        real = type(db).set_rule_generated_upto
        calls = {"n": 0}

        def flaky(self, rule_id, date_text, connection=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt("power loss mid-run")
            return real(self, rule_id, date_text, connection=connection)

        monkeypatch.setattr(type(db), "set_rule_generated_upto", flaky)
        with pytest.raises(KeyboardInterrupt):
            generate_due(db, db.recurring_rules(), datetime.date(2026, 8, 7))
        monkeypatch.undo()

        assert db.count_transactions() == 0
        assert db.recurring_rules()[0].generated_upto is None

    def test_no_duplicates_after_a_crashed_run(self, db, monkeypatch):
        db.add_recurring_rule(make_rule(starts_on="01-06-2026"))

        real = type(db).set_rule_generated_upto
        calls = {"n": 0}

        def flaky(self, rule_id, date_text, connection=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt()
            return real(self, rule_id, date_text, connection=connection)

        monkeypatch.setattr(type(db), "set_rule_generated_upto", flaky)
        with pytest.raises(KeyboardInterrupt):
            generate_due(db, db.recurring_rules(), datetime.date(2026, 8, 7))
        monkeypatch.undo()

        generate_due(db, db.recurring_rules(), datetime.date(2026, 8, 7))
        dates = [t.occurred_on for t in db.transactions()]
        assert len(dates) == len(set(dates)) == 3


def test_all_frequencies_are_callable():
    """Guards against a typo in the FREQUENCIES table."""
    start = datetime.date(2026, 1, 1)
    for name, advance in FREQUENCIES.items():
        assert isinstance(advance(start, 1), datetime.date), name
