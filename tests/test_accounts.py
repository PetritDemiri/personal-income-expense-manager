"""Tests for accounts and transfers.

The transfer tests carry most of the weight. A transfer is neither income nor
an expense, so any code path that reaches for an `else` branch when checking
the transaction type will quietly file every transfer as spending - which is
the bug class that has hit this project more than once.
"""

import datetime
from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.accounts import (
    UNASSIGNED,
    balances_for,
    filter_by_account,
    find_account,
    rename_account,
    total_balance,
    unassign_account,
)
from personal_finance.app import FinanceApp
from personal_finance.cli import main
from personal_finance.config import BANK, CARD, CASH, EXPENSE, INCOME, TRANSFER
from personal_finance.models import Account, Transaction
from personal_finance.reports import calculate_totals

from .conftest import make_rule, make_transaction


def account(name="Kesh", account_type=CASH, opening="0.00"):
    return Account(emri=name, lloji=account_type, gjendja_fillestare=Decimal(opening))


def entry(trans_type, amount, acct="", dest="", date="15-06-2026"):
    return Transaction(
        lloji=trans_type,
        pershkrimi="Test",
        shuma=Decimal(amount),
        data=date,
        kategoria="Ushqim",
        llogaria=acct,
        llogaria_dest=dest,
    )


class TestAccountModel:
    def test_round_trip_through_row(self):
        original = account("Banka", BANK, "500.00")
        assert Account.from_row(original.to_row()) == original

    def test_opening_balance_may_be_negative(self):
        """A credit card usually starts out owing money."""
        card = Account.from_row({"emri": "Karta", "lloji": CARD, "gjendja_fillestare": "-250.00"})
        assert card.gjendja_fillestare == Decimal("-250.00")

    def test_missing_opening_balance_defaults_to_zero(self):
        assert Account.from_row({"emri": "Kesh"}).gjendja_fillestare == Decimal("0.00")

    def test_missing_type_defaults_to_cash(self):
        assert Account.from_row({"emri": "Kesh"}).lloji == CASH

    @pytest.mark.parametrize(
        "row",
        [
            {"emri": "", "gjendja_fillestare": "0"},
            {"emri": "Kesh", "gjendja_fillestare": "abc"},
        ],
    )
    def test_invalid_rows_raise(self, row):
        with pytest.raises(ValueError):
            Account.from_row(row)


class TestTransfersAreNeitherIncomeNorExpense:
    """The property everything else depends on."""

    def test_transfer_is_excluded_from_totals(self):
        transactions = [
            entry(INCOME, "1000"),
            entry(EXPENSE, "300"),
            entry(TRANSFER, "200", "Banka", "Kesh"),
        ]
        totals = calculate_totals(transactions)
        assert totals.income == Decimal("1000")
        assert totals.expenses == Decimal("300")
        assert totals.balance == Decimal("700")

    def test_a_transfer_alone_leaves_the_balance_at_zero(self):
        totals = calculate_totals([entry(TRANSFER, "500", "Banka", "Kesh")])
        assert totals.income == Decimal("0.00")
        assert totals.expenses == Decimal("0.00")
        assert totals.balance == Decimal("0.00")

    def test_transfers_do_not_reach_the_category_breakdown(self):
        from personal_finance.reports import totals_by_category

        transactions = [
            entry(EXPENSE, "100"),
            entry(TRANSFER, "500", "Banka", "Kesh"),
        ]
        rows = totals_by_category(transactions, EXPENSE)
        assert sum(amount for _, amount in rows) == Decimal("100")

    def test_transfers_do_not_count_against_a_budget(self):
        from personal_finance.budgets import spent_in_month

        transactions = [
            entry(EXPENSE, "50", date="05-06-2026"),
            entry(TRANSFER, "900", "Banka", "Kesh", date="05-06-2026"),
        ]
        assert spent_in_month(transactions, "Ushqim", 2026, 6) == Decimal("50")


class TestPerAccountBalances:
    def test_opening_balance_is_the_starting_point(self):
        balances = balances_for([account("Banka", BANK, "500.00")], [])
        assert balances[0].balance == Decimal("500.00")

    def test_income_raises_the_account_balance(self):
        balances = balances_for([account("Banka", BANK, "500.00")], [entry(INCOME, "200", "Banka")])
        assert balances[0].balance == Decimal("700.00")

    def test_expense_lowers_the_account_balance(self):
        balances = balances_for(
            [account("Banka", BANK, "500.00")], [entry(EXPENSE, "200", "Banka")]
        )
        assert balances[0].balance == Decimal("300.00")

    def test_transfer_moves_money_between_two_accounts(self):
        """The ATM withdrawal case: bank down 100, cash up 100."""
        accounts = [account("Banka", BANK, "500.00"), account("Kesh", CASH, "20.00")]
        balances = balances_for(accounts, [entry(TRANSFER, "100", "Banka", "Kesh")])
        by_name = {b.name: b.balance for b in balances}
        assert by_name["Banka"] == Decimal("400.00")
        assert by_name["Kesh"] == Decimal("120.00")

    def test_transfer_leaves_the_combined_total_unchanged(self):
        accounts = [account("Banka", BANK, "500.00"), account("Kesh", CASH, "20.00")]
        before = total_balance(accounts, [])
        after = total_balance(accounts, [entry(TRANSFER, "100", "Banka", "Kesh")])
        assert before == after == Decimal("520.00")

    def test_negative_opening_balance_works(self):
        balances = balances_for(
            [account("Karta", CARD, "-250.00")], [entry(EXPENSE, "50", "Karta")]
        )
        assert balances[0].balance == Decimal("-300.00")

    def test_transactions_for_other_accounts_are_ignored(self):
        accounts = [account("Banka", BANK, "100.00"), account("Kesh", CASH, "0.00")]
        balances = balances_for(accounts, [entry(EXPENSE, "50", "Kesh")])
        by_name = {b.name: b.balance for b in balances}
        assert by_name["Banka"] == Decimal("100.00")
        assert by_name["Kesh"] == Decimal("-50.00")

    def test_combined_total_sums_every_account(self):
        accounts = [account("Banka", BANK, "500.00"), account("Kesh", CASH, "100.00")]
        transactions = [entry(INCOME, "50", "Banka"), entry(EXPENSE, "20", "Kesh")]
        assert total_balance(accounts, transactions) == Decimal("630.00")


class TestUnassignedTransactions:
    def test_unassigned_row_appears_only_when_needed(self):
        accounts = [account("Kesh")]
        assert len(balances_for(accounts, [entry(INCOME, "10", "Kesh")])) == 1
        assert len(balances_for(accounts, [entry(INCOME, "10", "")])) == 2

    def test_unassigned_money_still_counts_in_the_total(self):
        """Transactions from before accounts existed must not vanish."""
        accounts = [account("Kesh", CASH, "0.00")]
        transactions = [entry(INCOME, "100", ""), entry(INCOME, "50", "Kesh")]
        assert total_balance(accounts, transactions) == Decimal("150.00")

    def test_unassigned_entry_is_marked_as_such(self):
        balances = balances_for([], [entry(INCOME, "100", "")])
        assert balances[0].is_unassigned
        assert balances[0].display_name == "-"

    def test_no_accounts_at_all_still_totals_correctly(self):
        transactions = [entry(INCOME, "100", ""), entry(EXPENSE, "40", "")]
        assert total_balance([], transactions) == Decimal("60.00")


class TestFilterByAccount:
    def test_matches_the_source_account(self):
        transactions = [entry(EXPENSE, "10", "Kesh"), entry(EXPENSE, "10", "Banka")]
        assert len(filter_by_account(transactions, "Kesh")) == 1

    def test_a_transfer_shows_under_both_accounts(self):
        transactions = [entry(TRANSFER, "100", "Banka", "Kesh")]
        assert len(filter_by_account(transactions, "Banka")) == 1
        assert len(filter_by_account(transactions, "Kesh")) == 1

    def test_unrelated_accounts_do_not_match(self):
        transactions = [entry(TRANSFER, "100", "Banka", "Kesh")]
        assert filter_by_account(transactions, "Karta") == []


class TestRenameAndDelete:
    def test_rename_repoints_transactions(self):
        accounts = [account("Banka")]
        transactions = [entry(EXPENSE, "10", "Banka")]
        rename_account(accounts, transactions, [], "Banka", "BKT")
        assert accounts[0].emri == "BKT"
        assert transactions[0].llogaria == "BKT"

    def test_rename_repoints_transfer_destinations(self):
        accounts = [account("Kesh")]
        transactions = [entry(TRANSFER, "10", "Banka", "Kesh")]
        rename_account(accounts, transactions, [], "Kesh", "Portofoli")
        assert transactions[0].llogaria_dest == "Portofoli"

    def test_rename_repoints_recurring_rules(self):
        accounts = [account("Banka")]
        rule = make_rule()
        rule.llogaria = "Banka"
        rename_account(accounts, [], [rule], "Banka", "BKT")
        assert rule.llogaria == "BKT"

    def test_delete_leaves_transactions_behind_as_unassigned(self):
        """The spending still happened; only the account is gone."""
        transactions = [entry(EXPENSE, "10", "Banka")]
        touched = unassign_account(transactions, [], "Banka")
        assert touched == 1
        assert transactions[0].llogaria == ""
        assert transactions[0].shuma == Decimal("10")

    def test_delete_clears_both_sides_of_a_transfer(self):
        transactions = [entry(TRANSFER, "10", "Banka", "Kesh")]
        unassign_account(transactions, [], "Banka")
        assert transactions[0].llogaria == ""
        assert transactions[0].llogaria_dest == "Kesh"

    def test_find_account_ignores_case(self):
        accounts = [account("Banka")]
        assert find_account(accounts, "banka") is not None
        assert find_account(accounts, "BANKA") is not None
        assert find_account(accounts, "Karta") is None

    def test_find_account_handles_empty_input(self):
        assert find_account([account("Banka")], "") is None


class TestAppLayer:
    def test_has_accounts_is_false_by_default(self, app):
        assert not app.has_accounts()

    def test_adding_an_account_persists(self, app, storage):
        app.add_account("Banka", BANK, Decimal("500"))

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert len(reloaded.accounts) == 1
        assert reloaded.accounts[0].gjendja_fillestare == Decimal("500.00")

    def test_renaming_persists_across_transactions_and_rules(self, app, storage):
        app.add_account("Banka", BANK, Decimal("0"))
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera", "", "Banka")
        app.update_account(0, name="BKT")

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert reloaded.accounts[0].emri == "BKT"
        assert reloaded.transactions[0].llogaria == "BKT"

    def test_deleting_persists_and_unassigns(self, app, storage):
        app.add_account("Banka", BANK, Decimal("0"))
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera", "", "Banka")
        removed, touched = app.delete_account(0)
        assert removed.emri == "Banka"
        assert touched == 1

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert reloaded.accounts == []
        assert len(reloaded.transactions) == 1
        assert reloaded.transactions[0].llogaria == ""

    def test_transfer_persists_with_both_accounts(self, app, storage):
        app.add_account("Banka", BANK, Decimal("500"))
        app.add_account("Kesh", CASH, Decimal("0"))
        app.add_transaction(
            TRANSFER,
            "Terheqje",
            Decimal("100"),
            "01-06-2026",
            account="Banka",
            destination="Kesh",
        )

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        transaction = reloaded.transactions[0]
        assert transaction.lloji == TRANSFER
        assert transaction.llogaria == "Banka"
        assert transaction.llogaria_dest == "Kesh"

        by_name = {
            b.name: b.balance for b in balances_for(reloaded.accounts, reloaded.transactions)
        }
        assert by_name["Banka"] == Decimal("400.00")
        assert by_name["Kesh"] == Decimal("100.00")

    def test_recurring_rules_carry_their_account(self, app, storage):
        rule = make_rule(start="01-06-2026")
        rule.llogaria = "Banka"
        app.recurring_rules.append(rule)
        app.save_recurring()
        app.process_recurring(as_of=datetime.date(2026, 8, 7))

        assert all(t.llogaria == "Banka" for t in app.transactions)


class TestCliAccounts:
    @pytest.fixture(autouse=True)
    def isolated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        i18n.set_language("sq")
        colors.configure(force_off=True)
        return tmp_path

    def test_accounts_view_is_empty_by_default(self, capsys):
        main(["--llogarite"])
        assert "Nuk ka asnje llogari" in capsys.readouterr().out

    def test_adding_with_an_unknown_account_is_rejected(self, capsys, isolated):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Qera",
                "--shuma",
                "300",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Qera",
                "--llogaria",
                "NukEkziston",
            ]
        )
        output = capsys.readouterr().out
        # Named, rather than reported as an invalid "number" when none was given.
        assert "NukEkziston" in output
        assert "nuk ekziston" in output

    def test_no_account_column_when_no_accounts_are_used(self, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Qera",
                "--shuma",
                "300",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Qera",
            ]
        )
        capsys.readouterr()
        main(["--lista"])
        assert "Llogaria" not in capsys.readouterr().out

    def test_balance_is_unchanged_for_a_user_without_accounts(self, capsys):
        main(
            [
                "--shto-te-ardhura",
                "--pershkrimi",
                "Paga",
                "--shuma",
                "1000",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Paga",
            ]
        )
        capsys.readouterr()
        main(["--gjendja"])
        output = capsys.readouterr().out
        assert "Gjendja Aktuale: €1000.00" in output
        assert "Llogarite:" not in output


def test_account_column_appears_once_an_account_is_used(app, capsys):
    from personal_finance.display import print_transactions
    from personal_finance.ui import numbered

    i18n.set_language("sq")
    colors.configure(force_off=True)

    app.add_account("Banka", BANK, Decimal("0"))
    app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera", "", "Banka")
    capsys.readouterr()

    print_transactions(numbered(app.transactions))
    assert "Llogaria" in capsys.readouterr().out


def test_transfer_shows_both_accounts_in_the_column():
    from personal_finance.display import account_cell

    assert account_cell(entry(TRANSFER, "10", "Banka", "Kesh")) == "Banka -> Kesh"
    assert account_cell(entry(EXPENSE, "10", "Kesh")) == "Kesh"
    assert account_cell(entry(EXPENSE, "10", "")) == "-"


def test_unassigned_constant_is_the_empty_string():
    assert UNASSIGNED == ""


def test_make_transaction_default_has_no_account():
    assert make_transaction().llogaria == ""


class TestActionFlagsStayInSync:
    """A hand-written list of action flags drifted twice; this is the guard.

    main() decides between flag mode and the interactive menu from
    ACTION_FLAGS. Adding a flag to the parser's action group without listing it
    there let start-up notices leak into scripted output.
    """

    def test_action_flags_matches_the_parser(self):
        from personal_finance.cli import ACTION_FLAGS, action_flag_dests, build_parser

        parser_dests = set(action_flag_dests(build_parser()))
        assert parser_dests, "the action group was not found"
        assert parser_dests == set(ACTION_FLAGS)

    def test_no_startup_notice_in_flag_mode(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        i18n.set_language("sq")
        colors.configure(force_off=True)

        main(["--llogarite"])
        assert "Jane lexuar" not in capsys.readouterr().out


class TestCliAccountCreation:
    @pytest.fixture(autouse=True)
    def isolated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        i18n.set_language("sq")
        colors.configure(force_off=True)
        return tmp_path

    def test_creates_an_account(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "850"])
        assert "u shtua" in capsys.readouterr().out

        main(["--llogarite"])
        output = capsys.readouterr().out
        assert "Banka" in output
        assert "850.00" in output

    def test_account_type_matching_ignores_case(self, capsys):
        main(["--shto-llogari", "Banka", "banke", "0"])
        capsys.readouterr()
        main(["--llogarite"])
        assert "Banke" in capsys.readouterr().out

    def test_negative_opening_balance_is_allowed(self, capsys):
        main(["--shto-llogari", "Karta", "Karte", "-250"])
        capsys.readouterr()
        main(["--llogarite"])
        assert "-250.00" in capsys.readouterr().out

    def test_unknown_account_type_is_rejected(self, capsys, isolated):
        main(["--shto-llogari", "X", "Kripto", "100"])
        output = capsys.readouterr().out
        assert "Lloj i pavlefshem" in output
        # And the type list is named, rather than telling the user to press 1 or 2.
        assert "Kesh" in output

    def test_duplicate_account_name_is_rejected(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "0"])
        capsys.readouterr()
        main(["--shto-llogari", "Banka", "Banke", "0"])
        assert "ekziston" in capsys.readouterr().out

    def test_invalid_opening_balance_is_rejected(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "abc"])
        assert "pavlefshme" in capsys.readouterr().out.lower()

    def test_english_alias(self, capsys):
        main(["--add-account", "Bank", "Banke", "100"])
        assert "u shtua" in capsys.readouterr().out


class TestCliTransfer:
    @pytest.fixture(autouse=True)
    def two_accounts(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        i18n.set_language("sq")
        colors.configure(force_off=True)
        main(["--shto-llogari", "Banka", "Banke", "850"])
        main(["--shto-llogari", "Kesh", "Kesh", "40"])
        capsys.readouterr()
        return tmp_path

    def test_moves_money_between_accounts(self, capsys):
        main(["--transfero", "Banka", "Kesh", "--shuma", "200"])
        assert "regjistrua" in capsys.readouterr().out

        main(["--llogarite"])
        output = capsys.readouterr().out
        assert "650.00" in output  # 850 - 200
        assert "240.00" in output  # 40 + 200

    def test_combined_total_is_unchanged(self, capsys):
        main(["--llogarite"])
        before = capsys.readouterr().out
        main(["--transfero", "Banka", "Kesh", "--shuma", "200"])
        capsys.readouterr()
        main(["--llogarite"])
        after = capsys.readouterr().out

        total_line = "Totali i te gjitha llogarive"
        assert next(x for x in before.split("\n") if total_line in x) == next(
            x for x in after.split("\n") if total_line in x
        )

    def test_transfer_is_not_counted_as_spending(self, capsys):
        main(["--transfero", "Banka", "Kesh", "--shuma", "200"])
        capsys.readouterr()
        main(["--gjendja"])
        output = capsys.readouterr().out
        assert "Shpenzimet Totale: €0.00" in output
        assert "Te Ardhurat Totale: €0.00" in output

    def test_account_names_match_case_insensitively(self, capsys):
        main(["--transfero", "banka", "kesh", "--shuma", "50"])
        assert "regjistrua" in capsys.readouterr().out

    def test_unknown_source_is_rejected_by_name(self, capsys):
        main(["--transfero", "Nope", "Kesh", "--shuma", "50"])
        output = capsys.readouterr().out
        assert "Nope" in output
        assert "nuk ekziston" in output

    def test_unknown_destination_is_rejected_by_name(self, capsys):
        main(["--transfero", "Banka", "Nope", "--shuma", "50"])
        assert "Nope" in capsys.readouterr().out

    def test_same_account_is_rejected(self, capsys):
        main(["--transfero", "Banka", "Banka", "--shuma", "50"])
        assert "njejta" in capsys.readouterr().out

    def test_missing_amount_is_rejected(self, capsys):
        main(["--transfero", "Banka", "Kesh"])
        assert "pavlefshme" in capsys.readouterr().out.lower()

    def test_invalid_date_is_rejected(self, capsys):
        main(["--transfero", "Banka", "Kesh", "--shuma", "50", "--data", "99-99-9999"])
        assert "pavlefshem" in capsys.readouterr().out.lower()

    def test_description_defaults_to_the_type_label(self, capsys):
        main(["--transfero", "Banka", "Kesh", "--shuma", "50"])
        capsys.readouterr()
        main(["--lista"])
        assert "Transferim" in capsys.readouterr().out

    def test_custom_description_and_date(self, capsys):
        main(
            [
                "--transfero",
                "Banka",
                "Kesh",
                "--shuma",
                "50",
                "--pershkrimi",
                "Terheqje ne ATM",
                "--data",
                "03-08-2026",
            ]
        )
        capsys.readouterr()
        main(["--lista"])
        output = capsys.readouterr().out
        assert "Terheqje ne ATM" in output
        assert "03-08-2026" in output

    def test_english_alias(self, capsys):
        main(["--transfer", "Banka", "Kesh", "--amount", "50"])
        assert "regjistrua" in capsys.readouterr().out


class TestUnassignedRowIsNotAnAccount:
    """Reported from real use: the accounts menu looked broken.

    With transactions but no accounts, the list showed a row numbered 1 for the
    unassigned money, so it read as an editable account. Choosing "edit"
    returned in silence, because there was nothing in app.accounts to edit.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        i18n.set_language("sq")
        colors.configure(force_off=True)

    def test_unassigned_row_is_not_numbered(self, capsys):
        from personal_finance.display import print_accounts

        print_accounts(balances_for([], [entry(INCOME, "30", "")]))
        lines = [x for x in capsys.readouterr().out.split("\n") if "€" in x]
        row = next(x for x in lines if "-" in x and "Totali" not in x)
        assert not row.strip().startswith("1")

    def test_real_accounts_are_still_numbered_from_one(self, capsys):
        from personal_finance.display import print_accounts

        accounts = [account("Banka", BANK, "500"), account("Kesh", CASH, "20")]
        print_accounts(balances_for(accounts, [entry(INCOME, "30", "")]))
        output = capsys.readouterr().out
        assert "1   Banka" in output
        assert "2   Kesh" in output

    def test_a_legend_explains_the_dash_row(self, capsys):
        from personal_finance.display import print_accounts

        print_accounts(balances_for([], [entry(INCOME, "30", "")]))
        assert "nuk i perkasin" in capsys.readouterr().out

    def test_no_legend_when_everything_is_assigned(self, capsys):
        from personal_finance.display import print_accounts

        accounts = [account("Banka", BANK, "0")]
        print_accounts(balances_for(accounts, [entry(INCOME, "30", "Banka")]))
        assert "nuk i perkasin" not in capsys.readouterr().out

    def test_edit_says_why_nothing_happens(self, app, capsys, monkeypatch):
        from personal_finance.ui import edit_account

        app.add_transaction(INCOME, "Paga", Decimal("30"), "01-08-2026", "Paga")
        capsys.readouterr()

        # No input should be requested at all.
        monkeypatch.setattr(
            "builtins.input",
            lambda _="": pytest.fail("should not prompt when there is nothing to edit"),
        )
        edit_account(app)
        assert "per te ndryshuar" in capsys.readouterr().out

    def test_delete_says_why_nothing_happens(self, app, capsys, monkeypatch):
        from personal_finance.ui import delete_account

        app.add_transaction(INCOME, "Paga", Decimal("30"), "01-08-2026", "Paga")
        capsys.readouterr()

        monkeypatch.setattr(
            "builtins.input",
            lambda _="": pytest.fail("should not prompt when there is nothing to delete"),
        )
        delete_account(app)
        assert "per te fshire" in capsys.readouterr().out

    def test_displayed_number_maps_to_the_right_account(self, app, capsys):
        """The unassigned row must not shift the numbering of real accounts."""
        app.add_account("Banka", BANK, Decimal("500"))
        app.add_account("Kesh", CASH, Decimal("20"))
        app.add_transaction(INCOME, "Paga", Decimal("30"), "01-08-2026", "Paga")
        capsys.readouterr()

        balances = balances_for(app.accounts, app.transactions)
        numbered_rows = [b for b in balances if not b.is_unassigned]
        # Row 2 on screen is app.accounts[1], which is what prompt_index returns.
        assert numbered_rows[1].name == app.accounts[1].emri == "Kesh"


class TestAssignUnassigned:
    """Bulk-assigning transactions recorded before accounts existed."""

    @pytest.fixture(autouse=True)
    def plain(self):
        i18n.set_language("sq")
        colors.configure(force_off=True)

    def test_assigns_every_account_less_transaction(self):
        from personal_finance.accounts import assign_unassigned

        transactions = [entry(INCOME, "50", ""), entry(EXPENSE, "20", "")]
        assigned, skipped = assign_unassigned(transactions, [], "Petrit")
        assert assigned == 2
        assert skipped == 0
        assert all(t.llogaria == "Petrit" for t in transactions)

    def test_leaves_already_assigned_transactions_alone(self):
        from personal_finance.accounts import assign_unassigned

        transactions = [entry(INCOME, "50", "Banka"), entry(EXPENSE, "20", "")]
        assigned, _ = assign_unassigned(transactions, [], "Petrit")
        assert assigned == 1
        assert transactions[0].llogaria == "Banka"

    def test_assigns_recurring_rules_too(self):
        """A rule with no account would keep producing unassigned transactions."""
        from personal_finance.accounts import assign_unassigned

        rule = make_rule()
        rule.llogaria = ""
        assigned, _ = assign_unassigned([], [rule], "Petrit")
        assert assigned == 1
        assert rule.llogaria == "Petrit"

    def test_skips_a_transfer_that_would_point_at_itself(self):
        from personal_finance.accounts import assign_unassigned

        transactions = [entry(TRANSFER, "50", "", "Petrit")]
        assigned, skipped = assign_unassigned(transactions, [], "Petrit")
        assert assigned == 0
        assert skipped == 1
        assert transactions[0].llogaria == ""

    def test_count_unassigned(self):
        from personal_finance.accounts import count_unassigned

        rule = make_rule()
        rule.llogaria = ""
        assert count_unassigned([entry(INCOME, "1", ""), entry(INCOME, "1", "X")], [rule]) == 2

    def test_balance_is_unchanged_by_assigning(self):
        """Moving money onto an account must not create or destroy any."""
        accounts = [account("Petrit", CASH, "0.00")]
        transactions = [entry(INCOME, "150", ""), entry(EXPENSE, "120", "")]
        before = total_balance(accounts, transactions)

        from personal_finance.accounts import assign_unassigned

        assign_unassigned(transactions, [], "Petrit")
        assert total_balance(accounts, transactions) == before == Decimal("30.00")

    def test_unassigned_row_disappears_afterwards(self):
        from personal_finance.accounts import assign_unassigned

        accounts = [account("Petrit", CASH, "0.00")]
        transactions = [entry(INCOME, "30", "")]
        assert any(b.is_unassigned for b in balances_for(accounts, transactions))

        assign_unassigned(transactions, [], "Petrit")
        assert not any(b.is_unassigned for b in balances_for(accounts, transactions))

    def test_persists_through_the_app_layer(self, app, storage):
        app.add_account("Petrit", CASH, Decimal("0"))
        app.add_transaction(INCOME, "Paga", Decimal("50"), "01-08-2026", "Paga")
        assigned, _ = app.assign_unassigned_to("Petrit")
        assert assigned == 1

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert reloaded.transactions[0].llogaria == "Petrit"


class TestAssignUnassignedCli:
    @pytest.fixture(autouse=True)
    def isolated(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        i18n.set_language("sq")
        colors.configure(force_off=True)
        main(
            [
                "--shto-te-ardhura",
                "--pershkrimi",
                "Paga",
                "--shuma",
                "150",
                "--data",
                "01-08-2026",
                "--kategoria",
                "Paga",
            ]
        )
        main(["--shto-llogari", "Petrit", "Kesh", "0"])
        capsys.readouterr()
        return tmp_path

    def test_assigns_and_reports(self, capsys):
        main(["--cakto-pa-llogari", "Petrit"])
        output = capsys.readouterr().out
        assert "U caktuan 1" in output
        assert "Petrit" in output

    def test_unassigned_row_is_gone_afterwards(self, capsys):
        main(["--cakto-pa-llogari", "Petrit"])
        capsys.readouterr()
        main(["--llogarite"])
        output = capsys.readouterr().out
        assert "nuk i perkasin" not in output
        assert "Petrit" in output

    def test_balance_is_unchanged(self, capsys):
        main(["--gjendja"])
        before = capsys.readouterr().out
        main(["--cakto-pa-llogari", "Petrit"])
        capsys.readouterr()
        main(["--gjendja"])
        after = capsys.readouterr().out
        assert "Gjendja Aktuale: €150.00" in before
        assert "Gjendja Aktuale: €150.00" in after

    def test_running_twice_is_safe(self, capsys):
        main(["--cakto-pa-llogari", "Petrit"])
        capsys.readouterr()
        main(["--cakto-pa-llogari", "Petrit"])
        assert "kane nje llogari" in capsys.readouterr().out

    def test_unknown_account_is_rejected(self, capsys):
        main(["--cakto-pa-llogari", "Nope"])
        assert "nuk ekziston" in capsys.readouterr().out

    def test_english_alias(self, capsys):
        main(["--assign-unassigned", "Petrit"])
        assert "U caktuan" in capsys.readouterr().out


class TestInteractiveFlowsAskForAnAccount:
    """Shipped broken in 2.3.0: the menu never asked which account to use.

    The command-line paths were covered, the menu paths were not, so an edit
    that silently failed to apply went unnoticed until real use.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        i18n.set_language("sq")
        colors.configure(force_off=True)

    @pytest.fixture
    def answers(self, monkeypatch):
        def feed(*values):
            queue = list(values)

            def fake_input(_prompt=""):
                if not queue:
                    raise AssertionError("prompt asked for more input than expected")
                return queue.pop(0)

            monkeypatch.setattr("builtins.input", fake_input)

        return feed

    def test_add_asks_for_an_account_when_one_exists(self, app, answers, capsys):
        from personal_finance.ui import add_transaction

        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()

        # description, amount, today, category, no subcategory, account 1
        answers("Paga", "50", "po", "1", "", "1")
        add_transaction(app, INCOME)

        assert app.transactions[-1].llogaria == "Petrit"

    def test_add_does_not_ask_when_no_accounts_exist(self, app, answers, capsys):
        from personal_finance.ui import add_transaction

        # No account answer supplied: an extra prompt would raise.
        answers("Paga", "50", "po", "1", "")
        add_transaction(app, INCOME)

        assert app.transactions[-1].llogaria == ""

    def test_added_transaction_is_not_unassigned(self, app, answers, capsys):
        from personal_finance.accounts import count_unassigned
        from personal_finance.ui import add_transaction

        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()

        answers("Paga", "50", "po", "1", "", "1")
        add_transaction(app, INCOME)

        assert count_unassigned(app.transactions, app.recurring_rules) == 0

    def test_expense_flow_also_asks(self, app, answers, capsys):
        from personal_finance.ui import add_transaction

        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()

        answers("Qera", "300", "po", "1", "", "1")
        add_transaction(app, EXPENSE)

        assert app.transactions[-1].llogaria == "Petrit"

    def test_account_can_be_skipped_at_the_prompt(self, app, answers, capsys):
        from personal_finance.ui import add_transaction

        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()

        answers("Paga", "50", "po", "1", "", "")
        add_transaction(app, INCOME)

        assert app.transactions[-1].llogaria == ""

    def test_recurring_rule_asks_for_an_account(self, app, answers, capsys):
        """A rule with no account regenerates unassigned transactions monthly."""
        from personal_finance.ui import add_recurring

        app.add_account("Petrit", CASH, Decimal("0"))
        capsys.readouterr()

        # type, description, amount, category, no subcategory, account,
        # frequency, not today, start date
        answers("2", "Qera", "300", "1", "", "1", "2", "jo", "01-01-2027")
        add_recurring(app)

        assert app.recurring_rules[-1].llogaria == "Petrit"

    def test_recurring_rule_does_not_ask_without_accounts(self, app, answers, capsys):
        from personal_finance.ui import add_recurring

        answers("2", "Qera", "300", "1", "", "2", "jo", "01-01-2027")
        add_recurring(app)

        assert app.recurring_rules[-1].llogaria == ""
