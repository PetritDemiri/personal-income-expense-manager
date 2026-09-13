"""Shared pytest fixtures."""

from decimal import Decimal

import pytest

from personal_finance.app import FinanceApp
from personal_finance.database import Database
from personal_finance.models import BANK, CASH, Account, Transaction
from personal_finance.schema import EXPENSE, INCOME


@pytest.fixture
def db(tmp_path):
    """An empty database in a temporary directory, never the real one."""
    database = Database(str(tmp_path / "finance.db"))
    yield database
    database.close()


@pytest.fixture
def app(db):
    """A FinanceApp over an empty database."""
    instance = FinanceApp(database=db, quiet=True)
    yield instance


@pytest.fixture
def stocked(app):
    """Two accounts, two categories and four transactions.

    Returns (app, ids) so a test can refer to things by id without querying
    for them first.
    """
    bank = app.add_account("Banka", BANK, Decimal("500.00"))
    cash = app.add_account("Kesh", CASH, Decimal("40.00"))

    app.add_transaction(INCOME, "Paga", Decimal("1000.00"), "01-06-2026", "Paga", None, bank)
    app.add_transaction(
        EXPENSE, "Ushqime", Decimal("150.50"), "15-06-2026", "Ushqim", "Dyqan", cash
    )
    app.add_transaction(INCOME, "Bonus", Decimal("200.00"), "05-07-2026", "Bonus", None, bank)
    app.add_transaction(EXPENSE, "Benzine", Decimal("60.00"), "10-07-2026", "Transport", None, bank)

    ids = {
        "bank": bank,
        "cash": cash,
        "food": app.db.category_by_name("Ushqim", EXPENSE).id,
        "pay": app.db.category_by_name("Paga", INCOME).id,
        "transport": app.db.category_by_name("Transport", EXPENSE).id,
    }
    return app, ids


def schema_before_users():
    """SCHEMA as it stood before version 7, for testing older migrations.

    Built by removing what version 7 added rather than by keeping a copy of
    the old text, so it cannot drift out of step with the real schema.
    """
    from personal_finance.schema import SCHEMA

    text = SCHEMA
    for fragment in (
        "    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n",
        "    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n",
        "    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n",
        "    user_id     INTEGER,\n",
    ):
        text = text.replace(fragment, "")

    start = text.index("CREATE TABLE users (")
    end = text.index("CREATE TABLE accounts (")
    text = text[:start] + text[end:]

    text = text.replace("    UNIQUE (user_id, name_key)\n);", "    dummy TEXT\n);")
    text = text.replace("UNIQUE (user_id, name_key, kind)", "UNIQUE (name_key, kind)")
    text = text.replace("UNIQUE (user_id, pattern_key)", "UNIQUE (pattern_key)")
    return "\n".join(line for line in text.split("\n") if "_user " not in line)


def audit_triggers_before_users():
    """The audit triggers as they stood before they recorded a user.

    The users table is skipped: it did not exist before version 7, so a
    trigger on it cannot be part of an older schema.
    """
    from personal_finance.schema import AUDITED_TABLES, audit_triggers

    script = "".join(
        audit_triggers(table, columns)
        for table, columns in AUDITED_TABLES.items()
        if table != "users"
    )
    return (
        script.replace(
            "INSERT INTO audit_log (user_id, entity, entity_id, action, before_json, after_json)",
            "INSERT INTO audit_log (entity, entity_id, action, before_json, after_json)",
        )
        .replace("VALUES (NEW.user_id, ", "VALUES (")
        .replace("VALUES (OLD.user_id, ", "VALUES (")
    )


def make_view(
    kind=EXPENSE,
    description="Test",
    amount="10.00",
    occurred_on="15-06-2026",
    category="Ushqim",
    subcategory=None,
    account=None,
    to_account=None,
    category_id=1,
    account_id=None,
    to_account_id=None,
    view_id=1,
):
    """A TransactionView built by hand, for testing pure functions.

    The domain modules work on views, so tests for them do not need a
    database - only something shaped like a row that came out of one.
    """
    from personal_finance.models import TransactionView

    return TransactionView(
        id=view_id,
        kind=kind,
        description=description,
        amount=Decimal(amount),
        occurred_on=occurred_on,
        category_id=category_id if category else None,
        subcategory_id=2 if subcategory else None,
        account_id=account_id,
        to_account_id=to_account_id,
        category=category,
        subcategory=subcategory,
        account=account,
        to_account=to_account,
    )


def make_transaction(
    kind=EXPENSE, description="Test", amount="10.00", occurred_on="15-06-2026", **kwargs
):
    """A Transaction model, for storage-level tests."""
    return Transaction(
        kind=kind,
        description=description,
        amount=Decimal(amount),
        occurred_on=occurred_on,
        **kwargs,
    )


def make_account(name="Kesh", kind=CASH, opening="0.00"):
    return Account(name=name, kind=kind, opening=Decimal(opening))


def make_rule(
    kind=EXPENSE,
    description="Qera",
    amount="300.00",
    frequency="mujore",
    starts_on="01-01-2026",
    generated_upto=None,
    **kwargs,
):
    from personal_finance.models import RecurringRule

    return RecurringRule(
        kind=kind,
        description=description,
        amount=Decimal(amount),
        frequency=frequency,
        starts_on=starts_on,
        generated_upto=generated_upto,
        **kwargs,
    )
