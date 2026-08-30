"""Tests for reading a bank statement as the bank sends it.

The fixture is a TEB statement with invented data: real structure, real
formats, nothing real in it. UTF-16 little-endian, six tables of which two are
legal boilerplate, a header row, an opening-balance row carrying no movement,
and a totals row one cell wider than the header.

The reconciliation tests carry the weight. A statement gives its running
balance on every row, so a misread column or a misplaced decimal separator can
be caught by arithmetic instead of by noticing months later that the money is
wrong.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from personal_finance.importing import ImportError_
from personal_finance.schema import EXPENSE, INCOME, TRANSFER
from personal_finance.statements import (
    clean_description,
    find_statement_table,
    looks_like_teb,
    parse_statement,
    read_tables,
    reconcile,
    to_candidates,
)

FIXTURE = Path(__file__).parent / "fixtures" / "teb_statement.htm"


@pytest.fixture
def raw():
    return FIXTURE.read_bytes()


class TestReadingTheFile:
    def test_the_fixture_is_utf16(self, raw):
        """Read as UTF-8 it yields no tables at all, rather than an error."""
        assert b"\x00" in raw[:200]

    def test_tables_are_found_despite_the_encoding(self, raw):
        assert len(read_tables(raw)) >= 4

    def test_the_boilerplate_tables_are_not_mistaken_for_data(self, raw):
        """Three pages of deposit-insurance text are laid out as tables too."""
        table = find_statement_table(read_tables(raw))
        assert table is not None
        assert table[0][0].strip().casefold() == "data"

    def test_the_table_is_found_by_header_not_position(self, raw):
        tables = read_tables(raw)
        found = find_statement_table(tables)
        assert tables.index(found) != 0

    def test_recognised_as_a_statement(self, raw):
        assert looks_like_teb(raw)

    def test_a_plain_csv_is_not_recognised(self):
        assert not looks_like_teb(b"Data,Shuma\n01-08-2026,10\n")

    def test_nonsense_is_not_recognised(self):
        assert not looks_like_teb(b"\x01\x02\x03")


class TestParsing:
    def test_the_opening_balance_is_read(self, raw):
        assert parse_statement(raw).opening == Decimal("10.00")

    def test_the_opening_row_is_not_a_transaction(self, raw):
        """Its debit and credit cells are empty rather than zero."""
        statement = parse_statement(raw)
        assert len(statement.rows) == 8
        assert all("bilancit" not in r["description"].casefold() for r in statement.rows)

    def test_the_totals_row_is_not_a_transaction(self, raw):
        statement = parse_statement(raw)
        assert all("totali" not in r["description"].casefold() for r in statement.rows)

    def test_the_stated_totals_are_read(self, raw):
        statement = parse_statement(raw)
        assert statement.stated_debit == Decimal("-27.00")
        assert statement.stated_credit == Decimal("50.00")

    def test_the_stated_count_is_read_from_the_wider_row(self, raw):
        """The totals row has one more cell than the header."""
        assert parse_statement(raw).stated_count == 8

    def test_debits_and_credits_become_one_signed_amount(self, raw):
        statement = parse_statement(raw)
        assert any(r["signed"] < 0 for r in statement.rows)
        assert any(r["signed"] > 0 for r in statement.rows)

    def test_the_reference_is_kept(self, raw):
        assert parse_statement(raw).rows[0]["reference"] == "101"

    def test_the_closing_balance_is_computed(self, raw):
        assert parse_statement(raw).closing == Decimal("33.00")

    def test_a_file_with_no_statement_table_is_rejected(self):
        with pytest.raises(ImportError_):
            parse_statement(b"<html><table><tr><td>hello</td></tr></table></html>")


class TestReconciliation:
    def test_a_good_statement_reconciles(self, raw):
        result = reconcile(parse_statement(raw))
        assert result.ok
        assert result.balances_ok
        assert result.checked == 8

    def test_every_stated_total_agrees(self, raw):
        result = reconcile(parse_statement(raw))
        assert result.debit_ok
        assert result.credit_ok
        assert result.count_ok

    def test_an_altered_amount_is_caught(self, raw):
        """The check that makes a misread column impossible to miss."""
        broken = raw.decode("utf-16-le").replace("<TD>-7.25</TD>", "<TD>-9.25</TD>", 1)
        result = reconcile(parse_statement(broken.encode("utf-16-le")))
        assert not result.ok
        assert result.mismatches

    def test_the_failing_rows_are_named(self, raw):
        broken = raw.decode("utf-16-le").replace("<TD>-7.25</TD>", "<TD>-9.25</TD>", 1)
        result = reconcile(parse_statement(broken.encode("utf-16-le")))
        dates = [date for date, _, _ in result.mismatches]
        assert "11/07/2025" in dates

    def test_an_altered_amount_also_breaks_the_stated_total(self, raw):
        broken = raw.decode("utf-16-le").replace("<TD>-7.25</TD>", "<TD>-9.25</TD>", 1)
        result = reconcile(parse_statement(broken.encode("utf-16-le")))
        assert result.debit_ok is False

    def test_a_missing_row_is_caught(self, raw):
        """A row lost to a layout change would otherwise pass unnoticed."""
        text = raw.decode("utf-16-le")
        start = text.index("<TR><TD>24/07/2025")
        end = text.index("</TR>", start) + len("</TR>")
        result = reconcile(parse_statement((text[:start] + text[end:]).encode("utf-16-le")))
        assert not result.ok
        assert result.count_ok is False


class TestCandidates:
    def test_one_candidate_per_row(self, raw):
        assert len(to_candidates(parse_statement(raw))) == 8

    def test_dates_are_converted_to_the_programs_format(self, raw):
        assert to_candidates(parse_statement(raw))[0].occurred_on == "30-06-2025"

    def test_a_debit_becomes_an_expense(self, raw):
        candidate = to_candidates(parse_statement(raw))[0]
        assert candidate.kind == EXPENSE
        assert candidate.amount == Decimal("4.50")

    def test_amounts_are_stored_positive(self, raw):
        assert all(c.amount > 0 for c in to_candidates(parse_statement(raw)))

    def test_a_cash_deposit_becomes_a_transfer(self, raw):
        """Money moved from a pocket into a bank is not money earned."""
        deposits = [c for c in to_candidates(parse_statement(raw)) if "Deponimi" in c.description]
        assert deposits
        assert all(c.kind == TRANSFER for c in deposits)

    def test_deposits_can_be_left_as_income(self, raw):
        candidates = to_candidates(parse_statement(raw), deposit_is_transfer=False)
        deposits = [c for c in candidates if "Deponimi" in c.description]
        assert all(c.kind == INCOME for c in deposits)

    def test_the_account_is_applied_to_every_row(self, raw):
        """On whichever side the money moved: out for spending, in for a deposit."""
        for candidate in to_candidates(parse_statement(raw), account_id=7):
            if candidate.kind == TRANSFER:
                assert candidate.to_account_id == 7
            else:
                assert candidate.account_id == 7

    def test_the_transaction_number_is_kept_as_a_reference(self, raw):
        assert to_candidates(parse_statement(raw))[0].reference == "101"


class TestDescriptionCleaning:
    def test_account_numbers_are_removed(self):
        """They identify nothing about a purchase and would be stored forever."""
        cleaned = clean_description("Mirëmbajtje për llog. rrjedhëse 9999000011112222 - 06/2025")
        assert "9999000011112222" not in cleaned
        assert "Mirëmbajtje" in cleaned

    def test_masking_asterisks_are_removed(self):
        assert "*" not in clean_description("ATM T001 **************** Deponimi")

    def test_times_are_removed(self):
        assert "11:30:29" not in clean_description("ATM T001 11:30:29 Deponimi")

    def test_a_trailing_date_stamp_is_removed(self):
        assert clean_description("E-commerce 0SHOP 20250629") == "E-commerce 0SHOP"

    def test_the_merchant_survives(self):
        cleaned = clean_description("E-commerce 0SHOP.EXAMPLE 05:45:07 **************** 20250629")
        assert cleaned == "E-commerce 0SHOP.EXAMPLE"

    def test_albanian_characters_survive(self):
        assert "ë" in clean_description("Mirëmbajtje për llog. rrjedhëse - 06/2025")

    def test_an_empty_description_gets_a_placeholder(self):
        assert clean_description("****************") == "-"
        assert clean_description("") == "-"

    def test_short_numbers_are_kept(self):
        """A four-digit terminal or reference is part of what identifies a row."""
        assert "111111" in clean_description("AFT 111111 20250715 01:08:18")


class TestEndToEnd:
    def test_a_statement_imports_and_balances(self, app, raw):
        from personal_finance.importing import commit

        statement = parse_statement(raw)
        assert reconcile(statement).ok

        account_id = app.add_account("TEB", "Banke", statement.opening)
        candidates = to_candidates(statement, account_id=account_id)
        assert commit(app, candidates) == 8
        assert app.count() == 8

    def test_the_imported_balance_matches_the_statement(self, app, raw):
        """The strongest check there is: the account ends where the bank says.

        Opening balance plus every imported movement must equal the closing
        balance printed on the statement. This caught a real bug - deposits
        were put on the account_id side, which takes money out of the account
        the statement says it went into, and the balance came back 100 short.
        """
        from personal_finance.accounts import balances_for
        from personal_finance.importing import commit

        statement = parse_statement(raw)
        account_id = app.add_account("TEB", "Banke", statement.opening)
        commit(app, to_candidates(statement, account_id=account_id))

        balances = {
            b.account_id: b.balance for b in balances_for(app.accounts(), app.transactions())
        }
        assert balances[account_id] == statement.closing == Decimal("33.00")

    def test_a_deposit_arrives_in_the_account_rather_than_leaving_it(self, app, raw):
        statement = parse_statement(raw)
        account_id = app.add_account("TEB", "Banke", statement.opening)
        candidates = to_candidates(statement, account_id=account_id)

        deposits = [c for c in candidates if c.kind == TRANSFER]
        assert deposits
        for deposit in deposits:
            assert deposit.to_account_id == account_id
            assert deposit.account_id is None

    def test_the_other_side_of_a_deposit_is_left_unassigned(self, app, raw):
        """The cash came from somewhere the program does not track yet.

        Showing it as unassigned is honest: it says money entered the account
        from a source that has not been recorded, rather than inventing one.
        """
        from personal_finance.accounts import balances_for
        from personal_finance.importing import commit

        statement = parse_statement(raw)
        account_id = app.add_account("TEB", "Banke", statement.opening)
        commit(app, to_candidates(statement, account_id=account_id))

        unassigned = [
            b for b in balances_for(app.accounts(), app.transactions()) if b.is_unassigned
        ]
        assert unassigned
        assert unassigned[0].balance == Decimal("-50.00")

    def test_reimporting_flags_every_row(self, app, raw):
        from personal_finance.importing import commit, mark_duplicates

        statement = parse_statement(raw)
        account_id = app.add_account("TEB", "Banke", statement.opening)
        commit(app, to_candidates(statement, account_id=account_id))

        again = to_candidates(statement, account_id=account_id)
        mark_duplicates(again, app.transactions())
        assert all(c.duplicate_of is not None for c in again)
        assert not any(c.will_import for c in again)

    def test_no_account_number_reaches_the_database(self, app, raw):
        from personal_finance.importing import commit

        statement = parse_statement(raw)
        commit(app, to_candidates(statement))
        for transaction in app.transactions():
            assert "9999000011112222" not in transaction.description
