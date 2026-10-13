"""Tests for the database layer.

This is the module the whole of version 3 rests on, so the tests cover the
things a text file could never do and that the CSV backend therefore never had
to get right: real NULLs instead of sentinel strings, filtering in SQL,
constraints the database enforces, and delete rules that keep the data behind a
deleted label.
"""

import datetime
import os
import sqlite3
from decimal import Decimal

import pytest

from personal_finance.database import Database, from_cents, from_iso, to_cents, to_iso
from personal_finance.models import (
    BANK,
    CASH,
    Account,
    Category,
    RecurringRule,
    Transaction,
    name_key,
    parse_amount,
    parse_signed_amount,
)
from personal_finance.schema import EXPENSE, INCOME, SCHEMA_VERSION, TRANSFER


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "finance.db"))
    yield database
    database.close()


@pytest.fixture
def seeded(db):
    """A small realistic set: two accounts, two categories, four transactions."""
    bank = db.add_account(Account(name="Banka", kind=BANK, opening=Decimal("500.00")))
    cash = db.add_account(Account(name="Kesh", kind=CASH, opening=Decimal("40.00")))
    food = db.ensure_category("Ushqim", EXPENSE)
    pay = db.ensure_category("Paga", INCOME)
    shop = db.ensure_subcategory("Dyqan", food)

    db.add_transaction(
        Transaction(
            INCOME, "Paga", Decimal("1200.00"), "01-08-2026", category_id=pay, account_id=bank
        )
    )
    db.add_transaction(
        Transaction(
            EXPENSE,
            "Ushqime",
            Decimal("45.50"),
            "03-08-2026",
            category_id=food,
            subcategory_id=shop,
            account_id=cash,
        )
    )
    db.add_transaction(
        Transaction(
            TRANSFER,
            "Terheqje",
            Decimal("200.00"),
            "04-08-2026",
            account_id=bank,
            to_account_id=cash,
        )
    )
    db.add_transaction(Transaction(EXPENSE, "Pa asgje", Decimal("5.00"), "05-08-2026"))
    return db, {"bank": bank, "cash": cash, "food": food, "pay": pay, "shop": shop}


class TestSchema:
    def test_new_database_is_at_the_current_version(self, db):
        assert db.schema_version == SCHEMA_VERSION

    def test_is_empty_until_something_is_stored(self, db):
        assert db.is_empty()
        db.add_account(Account(name="Kesh"))
        assert not db.is_empty()

    def test_reopening_keeps_the_data(self, tmp_path):
        path = str(tmp_path / "finance.db")
        first = Database(path)
        first.add_account(Account(name="Kesh"))
        first.close()

        second = Database(path)
        assert len(second.accounts()) == 1
        assert second.schema_version == SCHEMA_VERSION
        second.close()

    def test_foreign_keys_are_enforced(self, db):
        """Off by default in SQLite, so this has to be switched on per connection."""
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection as conn:
                conn.execute(
                    "INSERT INTO subcategories (name, name_key, category_id) VALUES ('x', 'x', 999)"
                )

    def test_money_column_is_an_integer(self, db):
        columns = {
            row[1]: row[2] for row in db.connection.execute("PRAGMA table_info(transactions)")
        }
        assert columns["amount_cents"] == "INTEGER"


class TestConstraints:
    """Rules the database enforces, rather than rules the code remembers."""

    def test_an_unknown_kind_is_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection as conn:
                conn.execute(
                    "INSERT INTO transactions (kind, description, amount_cents, occurred_on) "
                    "VALUES ('Nonsense', 'x', 1, '2026-01-01')"
                )

    def test_a_blank_description_is_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection as conn:
                conn.execute(
                    "INSERT INTO transactions (kind, description, amount_cents, occurred_on) "
                    "VALUES (?, '   ', 1, '2026-01-01')",
                    (EXPENSE,),
                )

    def test_a_negative_amount_is_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection as conn:
                conn.execute(
                    "INSERT INTO transactions (kind, description, amount_cents, occurred_on) "
                    "VALUES (?, 'x', -5, '2026-01-01')",
                    (EXPENSE,),
                )

    def test_duplicate_category_in_the_same_kind_is_rejected(self, db):
        db.add_category(Category(name="Ushqim", kind=EXPENSE))
        with pytest.raises(sqlite3.IntegrityError):
            db.add_category(Category(name="Ushqim", kind=EXPENSE))

    def test_the_same_name_may_exist_in_each_kind(self, db):
        """Rimbursim is legitimately both an income and an expense category."""
        db.add_category(Category(name="Rimbursim", kind=INCOME))
        db.add_category(Category(name="Rimbursim", kind=EXPENSE))
        assert len(db.categories()) == 2

    def test_case_differing_names_are_the_same_category(self, db):
        db.add_category(Category(name="Ushqim", kind=EXPENSE))
        with pytest.raises(sqlite3.IntegrityError):
            db.add_category(Category(name="ushqim", kind=EXPENSE))

    def test_albanian_case_folding_is_handled(self, db):
        """COLLATE NOCASE folds only A-Z, which is why name_key exists."""
        db.add_category(Category(name="Ëmbëlsira", kind=EXPENSE))
        with pytest.raises(sqlite3.IntegrityError):
            db.add_category(Category(name="ëmbëlsira", kind=EXPENSE))

    def test_duplicate_account_name_is_rejected(self, db):
        db.add_account(Account(name="Banka"))
        with pytest.raises(sqlite3.IntegrityError):
            db.add_account(Account(name="banka"))

    def test_a_budget_limit_must_be_positive(self, db):
        category = db.ensure_category("Ushqim", EXPENSE)
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection as conn:
                conn.execute(
                    "INSERT INTO budgets (category_id, limit_cents) VALUES (?, 0)",
                    (category,),
                )


class TestNullsNotSentinels:
    def test_a_transaction_may_have_no_category(self, db):
        db.add_transaction(Transaction(EXPENSE, "x", Decimal("5"), "01-08-2026"))
        stored = db.transactions()[0]
        assert stored.category_id is None
        assert stored.account_id is None

    def test_clearing_a_field_sets_null(self, seeded):
        db, ids = seeded
        first = db.transactions()[0]
        db.update_transaction(first.id, category_id=None)
        assert db.transaction(first.id).category_id is None

    def test_no_placeholder_text_is_stored(self, db):
        db.add_transaction(Transaction(EXPENSE, "x", Decimal("5"), "01-08-2026"))
        row = db.connection.execute("SELECT * FROM transactions").fetchone()
        assert row["category_id"] is None


class TestFilteringInSql:
    def test_date_range_is_inclusive(self, seeded):
        db, _ = seeded
        rows = db.transactions(start=datetime.date(2026, 8, 3), end=datetime.date(2026, 8, 4))
        assert len(rows) == 2

    def test_open_ended_start(self, seeded):
        db, _ = seeded
        assert len(db.transactions(start=datetime.date(2026, 8, 4))) == 2

    def test_by_kind(self, seeded):
        db, _ = seeded
        assert len(db.transactions(kind=EXPENSE)) == 2
        assert len(db.transactions(kind=TRANSFER)) == 1

    def test_by_account_includes_transfers_in_both_directions(self, seeded):
        db, ids = seeded
        assert len(db.transactions(account_id=ids["cash"])) == 2
        assert len(db.transactions(account_id=ids["bank"])) == 2

    def test_by_category(self, seeded):
        db, ids = seeded
        assert len(db.transactions(category_id=ids["food"])) == 1

    def test_search_matches_the_description(self, seeded):
        db, _ = seeded
        assert len(db.transactions(search="Ushqime")) == 1

    def test_search_matches_a_joined_category_name(self, seeded):
        """Searching for a category finds its transactions without resolving it."""
        db, _ = seeded
        assert len(db.transactions(search="Paga")) == 1

    def test_search_matches_a_joined_subcategory_name(self, seeded):
        db, _ = seeded
        assert len(db.transactions(search="Dyqan")) == 1

    def test_results_are_chronological(self, seeded):
        db, _ = seeded
        dates = [t.occurred_on for t in db.transactions()]
        assert dates == sorted(dates, key=lambda d: to_iso(d))

    def test_filters_combine(self, seeded):
        db, ids = seeded
        rows = db.transactions(kind=EXPENSE, account_id=ids["cash"])
        assert len(rows) == 1

    def test_limit(self, seeded):
        db, _ = seeded
        assert len(db.transactions(limit=2)) == 2


class TestRowLevelOperations:
    def test_add_returns_an_id(self, db):
        new_id = db.add_transaction(Transaction(EXPENSE, "x", Decimal("5"), "01-08-2026"))
        assert isinstance(new_id, int)
        assert db.transaction(new_id) is not None

    def test_update_changes_only_what_is_passed(self, seeded):
        db, ids = seeded
        first = db.transactions()[0]
        db.update_transaction(first.id, amount=Decimal("99.99"))
        after = db.transaction(first.id)
        assert after.amount == Decimal("99.99")
        assert after.description == first.description
        assert after.category_id == first.category_id

    def test_update_rejects_an_unknown_field(self, seeded):
        db, _ = seeded
        first = db.transactions()[0]
        with pytest.raises(ValueError):
            db.update_transaction(first.id, nonsense="x")

    def test_delete_removes_one_row_only(self, seeded):
        db, _ = seeded
        before = db.count_transactions()
        db.delete_transaction(db.transactions()[0].id)
        assert db.count_transactions() == before - 1

    def test_adding_does_not_rewrite_the_table(self, seeded):
        """Row-level writes: existing ids must survive an insert."""
        db, _ = seeded
        ids_before = [t.id for t in db.transactions()]
        db.add_transaction(Transaction(EXPENSE, "new", Decimal("1"), "06-08-2026"))
        ids_after = [t.id for t in db.transactions()]
        assert ids_before == ids_after[: len(ids_before)]


class TestDeleteRules:
    def test_deleting_an_account_keeps_its_transactions(self, seeded):
        """The spending still happened; only the label is gone."""
        db, ids = seeded
        before = db.count_transactions()
        db.delete_account(ids["cash"])
        assert db.count_transactions() == before
        assert all(t.account_id != ids["cash"] for t in db.transactions())

    def test_deleting_an_account_clears_both_sides_of_a_transfer(self, seeded):
        db, ids = seeded
        db.delete_account(ids["cash"])
        transfer = db.transactions(kind=TRANSFER)[0]
        assert transfer.to_account_id is None

    def test_deleting_a_category_keeps_its_transactions(self, seeded):
        db, ids = seeded
        before = db.count_transactions()
        db.delete_category(ids["food"])
        assert db.count_transactions() == before

    def test_deleting_a_category_removes_its_subcategories(self, seeded):
        """A subcategory has no meaning without its parent."""
        db, ids = seeded
        db.delete_category(ids["food"])
        assert db.subcategory(ids["shop"]) is None

    def test_deleting_a_category_removes_its_budget(self, seeded):
        db, ids = seeded
        db.set_budget(ids["food"], Decimal("200"))
        db.delete_category(ids["food"])
        assert db.budgets() == []


class TestEnsureHelpers:
    def test_ensure_category_creates_once(self, db):
        first = db.ensure_category("Ushqim", EXPENSE)
        second = db.ensure_category("Ushqim", EXPENSE)
        assert first == second
        assert len(db.categories()) == 1

    def test_ensure_category_matches_regardless_of_case(self, db):
        first = db.ensure_category("Ushqim", EXPENSE)
        assert db.ensure_category("USHQIM", EXPENSE) == first

    def test_ensure_category_separates_the_two_kinds(self, db):
        income = db.ensure_category("Rimbursim", INCOME)
        expense = db.ensure_category("Rimbursim", EXPENSE)
        assert income != expense

    def test_ensure_category_ignores_a_blank_name(self, db):
        assert db.ensure_category("   ", EXPENSE) is None

    def test_ensure_subcategory_is_scoped_to_its_category(self, db):
        food = db.ensure_category("Ushqim", EXPENSE)
        travel = db.ensure_category("Transport", EXPENSE)
        one = db.ensure_subcategory("Te tjera", food)
        two = db.ensure_subcategory("Te tjera", travel)
        assert one != two

    def test_ensure_subcategory_needs_a_category(self, db):
        assert db.ensure_subcategory("Dyqan", None) is None


class TestBudgets:
    def test_set_and_read(self, db):
        food = db.ensure_category("Ushqim", EXPENSE)
        db.set_budget(food, Decimal("200"))
        assert db.budget_for(food).limit == Decimal("200.00")

    def test_setting_twice_replaces_rather_than_duplicates(self, db):
        food = db.ensure_category("Ushqim", EXPENSE)
        db.set_budget(food, Decimal("200"))
        db.set_budget(food, Decimal("250"))
        assert len(db.budgets()) == 1
        assert db.budget_for(food).limit == Decimal("250.00")

    def test_spent_in_month_sums_in_sql(self, seeded):
        db, ids = seeded
        assert db.spent_in_month(ids["food"], 2026, 8) == Decimal("45.50")

    def test_spent_in_month_ignores_other_months(self, seeded):
        db, ids = seeded
        assert db.spent_in_month(ids["food"], 2026, 7) == Decimal("0.00")

    def test_spent_in_month_ignores_income(self, db):
        category = db.ensure_category("Rimbursim", EXPENSE)
        income_category = db.ensure_category("Rimbursim", INCOME)
        db.add_transaction(
            Transaction(INCOME, "x", Decimal("500"), "01-08-2026", category_id=income_category)
        )
        assert db.spent_in_month(category, 2026, 8) == Decimal("0.00")


class TestRecurringRules:
    def test_round_trip(self, db):
        rule = RecurringRule(
            kind=EXPENSE,
            description="Qera",
            amount=Decimal("300.00"),
            frequency="mujore",
            starts_on="01-01-2026",
        )
        rule_id = db.add_recurring_rule(rule)
        stored = db.recurring_rules()[0]
        assert stored.id == rule_id
        assert stored.amount == Decimal("300.00")
        assert stored.starts_on == "01-01-2026"
        assert stored.generated_upto is None

    def test_generated_upto_is_recorded(self, db):
        rule_id = db.add_recurring_rule(
            RecurringRule(
                kind=EXPENSE, description="Qera", amount=Decimal("300"), starts_on="01-01-2026"
            )
        )
        db.set_rule_generated_upto(rule_id, "01-03-2026")
        assert db.recurring_rules()[0].generated_upto == "01-03-2026"


class TestAtomic:
    def test_a_failure_rolls_back_everything(self, db):
        """The recurring-run bug from 2.2.0, now handled by one context manager."""
        food = db.ensure_category("Ushqim", EXPENSE)
        rule_id = db.add_recurring_rule(
            RecurringRule(
                kind=EXPENSE,
                description="Qera",
                amount=Decimal("300"),
                starts_on="01-01-2026",
                category_id=food,
            )
        )
        before = db.count_transactions()

        with pytest.raises(RuntimeError):
            with db.atomic() as conn:
                db.add_transaction(
                    Transaction(EXPENSE, "generated", Decimal("300"), "01-01-2026"),
                    connection=conn,
                )
                db.set_rule_generated_upto(rule_id, "01-01-2026", connection=conn)
                raise RuntimeError("crash between the two writes")

        assert db.count_transactions() == before
        assert db.recurring_rules()[0].generated_upto is None

    def test_success_commits_both(self, db):
        rule_id = db.add_recurring_rule(
            RecurringRule(
                kind=EXPENSE, description="Qera", amount=Decimal("300"), starts_on="01-01-2026"
            )
        )
        with db.atomic() as conn:
            db.add_transaction(
                Transaction(EXPENSE, "generated", Decimal("300"), "01-01-2026"),
                connection=conn,
            )
            db.set_rule_generated_upto(rule_id, "01-01-2026", connection=conn)

        assert db.count_transactions() == 1
        assert db.recurring_rules()[0].generated_upto == "01-01-2026"

    def test_a_write_inside_it_waits_for_the_whole_of_it(self, db):
        """Every write used to commit itself, and with it everything the
        enclosing transaction had done so far."""
        with pytest.raises(RuntimeError):
            with db.atomic() as conn:
                db.add_transaction(
                    Transaction(EXPENSE, "first", Decimal("1"), "01-01-2026"), connection=conn
                )
                db.ensure_category("Krejt e re", EXPENSE)
                raise RuntimeError("fails after a category was created")

        assert db.count_transactions() == 0
        assert db.categories() == []

    def test_one_inside_another_is_part_of_it(self, db):
        with pytest.raises(RuntimeError):
            with db.atomic():
                with db.atomic() as conn:
                    db.add_transaction(
                        Transaction(EXPENSE, "inner", Decimal("1"), "01-01-2026"),
                        connection=conn,
                    )
                raise RuntimeError("the outer one fails after the inner one finished")

        assert db.count_transactions() == 0

    def test_a_write_outside_it_is_saved_at_once(self, db, tmp_path):
        db.ensure_category("Ushqim", EXPENSE)
        other = sqlite3.connect(db.path)
        try:
            assert other.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1
        finally:
            other.close()

    def test_it_is_usable_again_after_a_failure(self, db):
        with pytest.raises(RuntimeError):
            with db.atomic():
                raise RuntimeError("fails")
        db.ensure_category("Ushqim", EXPENSE)
        other = sqlite3.connect(db.path)
        try:
            assert other.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1
        finally:
            other.close()


class TestConversion:
    @pytest.mark.parametrize(
        "euros,cents",
        [
            ("0.00", 0),
            ("0.01", 1),
            ("1.00", 100),
            ("200.00", 20000),
            ("185.40", 18540),
            ("1234567.89", 123456789),
        ],
    )
    def test_to_cents(self, euros, cents):
        assert to_cents(Decimal(euros)) == cents

    def test_round_trip_is_exact(self):
        for value in ("0.01", "0.10", "0.20", "185.40", "999999.99"):
            assert from_cents(to_cents(Decimal(value))) == Decimal(value)

    def test_no_floating_point_drift(self):
        total = from_cents(to_cents(Decimal("0.10"))) + from_cents(to_cents(Decimal("0.20")))
        assert total == Decimal("0.30")

    def test_dates_are_stored_iso_so_they_sort(self):
        assert to_iso("05-08-2026") == "2026-08-05"
        assert sorted([to_iso("15-12-2026"), to_iso("05-08-2026")])[0] == "2026-08-05"

    def test_iso_round_trip(self):
        assert from_iso(to_iso("05-08-2026")) == "05-08-2026"

    def test_amount_survives_storage_exactly(self, db):
        db.add_transaction(Transaction(EXPENSE, "x", Decimal("185.40"), "01-08-2026"))
        assert db.transactions()[0].amount == Decimal("185.40")


class TestModelHelpers:
    def test_name_key_folds_case(self):
        assert name_key("Ushqim") == name_key("USHQIM")

    def test_name_key_folds_albanian_letters(self):
        assert name_key("Ëmbëlsira") == name_key("ëmbëlsira")

    def test_name_key_matches_composed_and_decomposed_accents(self):
        assert name_key("\u00eb") == name_key("e\u0308")

    def test_name_key_trims(self):
        assert name_key("  Ushqim  ") == name_key("Ushqim")

    @pytest.mark.parametrize("bad", ["abc", "", None, "-5", "NaN"])
    def test_parse_amount_rejects(self, bad):
        assert parse_amount(bad) is None

    def test_parse_signed_amount_allows_negative(self):
        """A card's opening balance is routinely negative."""
        assert parse_signed_amount("-250.00") == Decimal("-250.00")

    def test_parse_signed_amount_rejects_nonsense(self):
        assert parse_signed_amount("abc") is None


def test_database_survives_an_interrupted_process(tmp_path):
    path = str(tmp_path / "finance.db")
    db = Database(path)
    db.add_transaction(Transaction(EXPENSE, "x", Decimal("5"), "01-08-2026"))
    del db  # never closed, as if the process vanished

    check = sqlite3.connect(path)
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()

    reopened = Database(path)
    assert reopened.count_transactions() == 1
    reopened.close()


def test_creates_a_missing_directory(tmp_path):
    path = str(tmp_path / "nested" / "deeper" / "finance.db")
    db = Database(path)
    assert os.path.exists(path)
    db.close()
