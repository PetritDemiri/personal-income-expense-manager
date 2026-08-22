"""Tests for accounts and transfers.

The transfer tests carry most of the weight: a transfer is neither income nor
an expense, so any code path reaching for an `else` when checking the kind
quietly files every one of them as spending.
"""

from decimal import Decimal

from personal_finance.accounts import (
    UNASSIGNED,
    AccountBalance,
    balances_for,
    count_unassigned,
    filter_by_account,
    find_account,
    total_balance,
)
from personal_finance.models import BANK, CARD, CASH, Account
from personal_finance.reports import calculate_totals
from personal_finance.schema import EXPENSE, INCOME, TRANSFER

from .conftest import make_rule, make_view

BANK_ID = 1
CASH_ID = 2


def account(name="Kesh", kind=CASH, opening="0.00", account_id=None):
    return Account(id=account_id, name=name, kind=kind, opening=Decimal(opening))


def entry(
    kind=EXPENSE, amount="10.00", account_id=None, to_account_id=None, occurred_on="15-06-2026"
):
    return make_view(
        kind,
        "Test",
        amount,
        occurred_on,
        category="Ushqim",
        account_id=account_id,
        to_account_id=to_account_id,
    )


class TestTransfersAreNeitherIncomeNorExpense:
    def test_excluded_from_totals(self):
        items = [
            entry(INCOME, "1000"),
            entry(EXPENSE, "300"),
            entry(TRANSFER, "200", BANK_ID, CASH_ID),
        ]
        totals = calculate_totals(items)
        assert totals.income == Decimal("1000")
        assert totals.expenses == Decimal("300")
        assert totals.balance == Decimal("700")

    def test_a_transfer_alone_leaves_the_balance_at_zero(self):
        totals = calculate_totals([entry(TRANSFER, "500", BANK_ID, CASH_ID)])
        assert totals.balance == Decimal("0.00")


class TestPerAccountBalances:
    def test_opening_balance_is_the_starting_point(self):
        balances = balances_for([account("Banka", BANK, "500.00", BANK_ID)], [])
        assert balances[0].balance == Decimal("500.00")

    def test_income_raises_the_balance(self):
        balances = balances_for(
            [account("Banka", BANK, "500.00", BANK_ID)], [entry(INCOME, "200", BANK_ID)]
        )
        assert balances[0].balance == Decimal("700.00")

    def test_expense_lowers_the_balance(self):
        balances = balances_for(
            [account("Banka", BANK, "500.00", BANK_ID)], [entry(EXPENSE, "200", BANK_ID)]
        )
        assert balances[0].balance == Decimal("300.00")

    def test_transfer_moves_money_between_two_accounts(self):
        """The ATM withdrawal case: bank down 100, cash up 100."""
        accounts = [
            account("Banka", BANK, "500.00", BANK_ID),
            account("Kesh", CASH, "20.00", CASH_ID),
        ]
        balances = balances_for(accounts, [entry(TRANSFER, "100", BANK_ID, CASH_ID)])
        by_name = {b.name: b.balance for b in balances}
        assert by_name["Banka"] == Decimal("400.00")
        assert by_name["Kesh"] == Decimal("120.00")

    def test_transfer_leaves_the_combined_total_unchanged(self):
        accounts = [
            account("Banka", BANK, "500.00", BANK_ID),
            account("Kesh", CASH, "20.00", CASH_ID),
        ]
        before = total_balance(accounts, [])
        after = total_balance(accounts, [entry(TRANSFER, "100", BANK_ID, CASH_ID)])
        assert before == after == Decimal("520.00")

    def test_negative_opening_balance_works(self):
        balances = balances_for(
            [account("Karta", CARD, "-250.00", BANK_ID)], [entry(EXPENSE, "50", BANK_ID)]
        )
        assert balances[0].balance == Decimal("-300.00")

    def test_other_accounts_are_ignored(self):
        accounts = [
            account("Banka", BANK, "100.00", BANK_ID),
            account("Kesh", CASH, "0.00", CASH_ID),
        ]
        balances = balances_for(accounts, [entry(EXPENSE, "50", CASH_ID)])
        by_name = {b.name: b.balance for b in balances}
        assert by_name["Banka"] == Decimal("100.00")
        assert by_name["Kesh"] == Decimal("-50.00")

    def test_combined_total_sums_every_account(self):
        accounts = [
            account("Banka", BANK, "500.00", BANK_ID),
            account("Kesh", CASH, "100.00", CASH_ID),
        ]
        items = [entry(INCOME, "50", BANK_ID), entry(EXPENSE, "20", CASH_ID)]
        assert total_balance(accounts, items) == Decimal("630.00")


class TestUnassigned:
    def test_the_row_appears_only_when_needed(self):
        accounts = [account("Kesh", account_id=CASH_ID)]
        assert len(balances_for(accounts, [entry(INCOME, "10", CASH_ID)])) == 1
        assert len(balances_for(accounts, [entry(INCOME, "10", None)])) == 2

    def test_unassigned_money_still_counts_in_the_total(self):
        """Transactions from before accounts existed must not vanish."""
        accounts = [account("Kesh", CASH, "0.00", CASH_ID)]
        items = [entry(INCOME, "100", None), entry(INCOME, "50", CASH_ID)]
        assert total_balance(accounts, items) == Decimal("150.00")

    def test_the_entry_is_marked_as_such(self):
        balances = balances_for([], [entry(INCOME, "100", None)])
        assert balances[0].is_unassigned
        assert balances[0].name is None

    def test_no_accounts_at_all_still_totals(self):
        items = [entry(INCOME, "100", None), entry(EXPENSE, "40", None)]
        assert total_balance([], items) == Decimal("60.00")

    def test_unassigned_key_is_none(self):
        assert UNASSIGNED is None

    def test_count_unassigned(self):
        rule = make_rule()
        items = [entry(INCOME, "1", None), entry(INCOME, "1", CASH_ID)]
        assert count_unassigned(items, [rule]) == 2


class TestFilterByAccount:
    def test_matches_the_source(self):
        items = [entry(EXPENSE, "10", CASH_ID), entry(EXPENSE, "10", BANK_ID)]
        assert len(filter_by_account(items, CASH_ID)) == 1

    def test_a_transfer_shows_under_both(self):
        items = [entry(TRANSFER, "100", BANK_ID, CASH_ID)]
        assert len(filter_by_account(items, BANK_ID)) == 1
        assert len(filter_by_account(items, CASH_ID)) == 1

    def test_unrelated_accounts_do_not_match(self):
        items = [entry(TRANSFER, "100", BANK_ID, CASH_ID)]
        assert filter_by_account(items, 99) == []


class TestFindAccount:
    def test_ignores_case(self):
        accounts = [account("Banka", account_id=BANK_ID)]
        assert find_account(accounts, "banka") is not None
        assert find_account(accounts, "BANKA") is not None
        assert find_account(accounts, "Karta") is None

    def test_handles_albanian_case_folding(self):
        accounts = [account("Ëmbëlsira", account_id=BANK_ID)]
        assert find_account(accounts, "ëmbëlsira") is not None

    def test_handles_empty_input(self):
        assert find_account([account("Banka")], "") is None


class TestAppLayer:
    def test_has_accounts_is_false_by_default(self, app):
        assert not app.has_accounts()

    def test_adding_an_account_persists(self, app):
        app.add_account("Banka", BANK, Decimal("500"))
        assert len(app.accounts()) == 1
        assert app.accounts()[0].opening == Decimal("500.00")

    def test_renaming_touches_only_the_account_row(self, app):
        """Transactions reference an id, so a rename is one row."""
        account_id = app.add_account("Banka", BANK, Decimal("0"))
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera", None, account_id)
        app.update_account(account_id, name="BKT")

        assert app.accounts()[0].name == "BKT"
        assert app.transactions()[0].account == "BKT"
        assert app.transactions()[0].account_id == account_id

    def test_deleting_keeps_the_transactions(self, app):
        account_id = app.add_account("Banka", BANK, Decimal("0"))
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera", None, account_id)
        removed, affected = app.delete_account(account_id)
        assert removed.name == "Banka"
        assert affected == 1
        assert app.accounts() == []
        assert app.count() == 1
        assert app.transactions()[0].account_id is None

    def test_transfer_persists_with_both_accounts(self, app):
        bank = app.add_account("Banka", BANK, Decimal("500"))
        cash = app.add_account("Kesh", CASH, Decimal("0"))
        app.add_transaction(
            TRANSFER,
            "Terheqje",
            Decimal("100"),
            "01-06-2026",
            account_id=bank,
            to_account_id=cash,
        )
        stored = app.transactions()[0]
        assert stored.kind == TRANSFER
        assert stored.account == "Banka"
        assert stored.to_account == "Kesh"

        by_name = {b.name: b.balance for b in balances_for(app.accounts(), app.transactions())}
        assert by_name["Banka"] == Decimal("400.00")
        assert by_name["Kesh"] == Decimal("100.00")

    def test_assign_unassigned(self, app):
        account_id = app.add_account("Petrit", CASH, Decimal("0"))
        app.add_transaction(INCOME, "Paga", Decimal("150"), "01-08-2026", "Paga")
        assert app.assign_unassigned_to(account_id) == 1
        assert app.transactions()[0].account_id == account_id

    def test_assign_unassigned_does_not_change_the_balance(self, app):
        account_id = app.add_account("Petrit", CASH, Decimal("0"))
        app.add_transaction(INCOME, "Paga", Decimal("150"), "01-08-2026", "Paga")
        app.add_transaction(EXPENSE, "Qera", Decimal("120"), "02-08-2026", "Qera")
        before = total_balance(app.accounts(), app.transactions())
        app.assign_unassigned_to(account_id)
        assert total_balance(app.accounts(), app.transactions()) == before == Decimal("30.00")

    def test_assign_skips_a_transfer_that_would_point_at_itself(self, app):
        app.add_account("Banka", BANK, Decimal("0"))
        cash = app.add_account("Kesh", CASH, Decimal("0"))
        app.add_transaction(
            TRANSFER,
            "x",
            Decimal("50"),
            "01-08-2026",
            account_id=None,
            to_account_id=cash,
        )
        app.assign_unassigned_to(cash)
        assert app.transactions()[0].account_id is None


def test_account_balance_repr_handles_the_unassigned_row():
    assert "pa llogari" in repr(AccountBalance(None, None))
