"""Shared pytest fixtures."""

import datetime
from decimal import Decimal

import pytest

from personal_finance.app import FinanceApp
from personal_finance.config import EXPENSE, INCOME
from personal_finance.models import Budget, RecurringRule, Transaction
from personal_finance.sqlite_storage import SqliteStorage
from personal_finance.storage import CsvStorage


@pytest.fixture
def csv_storage(tmp_path):
    """CsvStorage pointed at a temporary directory, never at real data.

    For tests that are specifically about the CSV backend - file layout,
    corrupted rows, atomic renames.
    """
    return CsvStorage(
        transactions_file=str(tmp_path / "transactions.csv"),
        recurring_file=str(tmp_path / "recurring.csv"),
        budgets_file=str(tmp_path / "budgets.csv"),
        accounts_file=str(tmp_path / "accounts.csv"),
    )


@pytest.fixture
def sqlite_storage(tmp_path):
    """SqliteStorage pointed at a temporary database."""
    store = SqliteStorage(database_file=str(tmp_path / "finance.db"))
    yield store
    store.close()


@pytest.fixture(params=["csv", "sqlite"])
def storage(request, tmp_path):
    """Every backend, one after the other.

    Any test using this fixture runs once per backend, which is what proves
    the two behave identically rather than merely being expected to.
    """
    if request.param == "csv":
        yield CsvStorage(
            transactions_file=str(tmp_path / "transactions.csv"),
            recurring_file=str(tmp_path / "recurring.csv"),
            budgets_file=str(tmp_path / "budgets.csv"),
            accounts_file=str(tmp_path / "accounts.csv"),
        )
    else:
        store = SqliteStorage(database_file=str(tmp_path / "finance.db"))
        yield store
        store.close()


@pytest.fixture
def app(storage):
    """A loaded, empty FinanceApp backed by temporary files."""
    instance = FinanceApp(storage=storage, quiet=True)
    instance.load()
    return instance


def make_transaction(
    trans_type=EXPENSE, description="Test", amount="10.00", date="15-06-2026", category="Ushqim"
):
    """Build a Transaction without repeating defaults in every test."""
    return Transaction(
        lloji=trans_type,
        pershkrimi=description,
        shuma=Decimal(amount),
        data=date,
        kategoria=category,
    )


def make_rule(
    trans_type=EXPENSE,
    description="Qera",
    amount="300.00",
    category="Qera",
    frequency="mujore",
    start="01-01-2026",
    last="",
):
    return RecurringRule(
        lloji=trans_type,
        pershkrimi=description,
        shuma=Decimal(amount),
        kategoria=category,
        frekuenca=frequency,
        data_fillimit=start,
        data_e_fundit=last,
    )


def make_budget(category="Ushqim", amount="200.00"):
    return Budget(kategoria=category, shuma=Decimal(amount))


@pytest.fixture
def sample_transactions():
    """A small mixed set spanning two months."""
    return [
        make_transaction(INCOME, "Paga", "1000.00", "01-06-2026", "Paga"),
        make_transaction(EXPENSE, "Qera", "300.00", "02-06-2026", "Qera"),
        make_transaction(EXPENSE, "Ushqime", "150.50", "15-06-2026", "Ushqim"),
        make_transaction(INCOME, "Bonus", "200.00", "05-07-2026", "Bonus"),
        make_transaction(EXPENSE, "Benzine", "60.00", "10-07-2026", "Transport"),
    ]


@pytest.fixture
def june_2026():
    return datetime.date(2026, 6, 30)
