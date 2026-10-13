"""Tests for importing transactions from a file.

The errors this guards against are the silent ones. A decimal separator read
the wrong way round turns 1.234,56 into 1.23; a day and month swapped moves a
transaction three months; an overlapping range imported twice doubles the
spending. None of them raises anything, so each is tested directly.
"""

from decimal import Decimal

import pytest

from personal_finance.importing import (
    Candidate,
    ImportError_,
    build_candidates,
    commit,
    decode,
    detect_date_format,
    detect_decimal_separator,
    guess_columns,
    has_usable_amount,
    is_deposit,
    mark_duplicates,
    normalise,
    parse_kind,
    parse_number,
    read_rows,
    sniff_delimiter,
)
from personal_finance.schema import EXPENSE, INCOME, TRANSFER


class TestDecoding:
    def test_plain_utf8(self):
        text, encoding = decode(b"Data,Shuma\n01-08-2026,10")
        assert "Data" in text

    def test_utf8_with_a_byte_order_mark(self):
        """Left in place it becomes part of the first header name."""
        text, _ = decode("Data,Shuma\n".encode("utf-8-sig"))
        assert text.startswith("Data")

    def test_utf16(self):
        """A bank file arriving as UTF-16 and read as UTF-8 yields no rows."""
        text, encoding = decode("Data,Shuma\n01-08-2026,10".encode("utf-16"))
        assert "Data" in text
        assert "\x00" not in text

    def test_accented_text_survives(self):
        text, _ = decode("Përshkrimi,Shuma\nËmbëlsira,10".encode())
        assert "Ëmbëlsira" in text


class TestDelimiters:
    @pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
    def test_each_is_found(self, delimiter):
        text = delimiter.join(["Data", "Shuma"]) + "\n" + delimiter.join(["01-08-2026", "10"])
        assert sniff_delimiter(text) == delimiter

    def test_an_empty_file_is_rejected(self):
        with pytest.raises(ImportError_):
            sniff_delimiter("   \n\n")

    def test_semicolons_win_over_commas_in_decimals(self):
        """A European file uses commas inside numbers, not between fields."""
        text = "Data;Shuma\n01-08-2026;1.234,56\n02-08-2026;9,99"
        assert sniff_delimiter(text) == ";"


class TestDecimalSeparator:
    def test_european_format(self):
        assert detect_decimal_separator(["1.234,56", "12,50"]) == ","

    def test_anglo_format(self):
        assert detect_decimal_separator(["1,234.56", "12.50"]) == "."

    def test_decided_from_the_whole_column(self):
        """One value cannot say; a column can."""
        assert detect_decimal_separator(["1.234", "12.50"]) == "."

    def test_plain_numbers_default_to_a_point(self):
        assert detect_decimal_separator(["1234.56", "12.50"]) == "."

    def test_no_separators_at_all(self):
        assert detect_decimal_separator(["100", "250"]) == "."


class TestParseNumber:
    @pytest.mark.parametrize(
        "text,separator,expected",
        [
            ("1.234,56", ",", "1234.56"),
            ("1,234.56", ".", "1234.56"),
            ("12,50", ",", "12.50"),
            ("-2.99", ".", "-2.99"),
            ("(50.00)", ".", "-50.00"),
            ("50.00-", ".", "-50.00"),
            ("€ 12.50", ".", "12.50"),
            ("1 234,56", ",", "1234.56"),
            ("0.00", ".", "0.00"),
        ],
    )
    def test_valid(self, text, separator, expected):
        assert parse_number(text, separator) == Decimal(expected)

    @pytest.mark.parametrize("bad", ["", "   ", None, "abc", "-", "..."])
    def test_invalid(self, bad):
        assert parse_number(bad) is None

    def test_a_misread_separator_produces_a_visibly_wrong_number(self):
        """It does not fail - it quietly returns the wrong amount.

        1.234,56 read with the wrong separator becomes about 1.23 instead of
        1234.56. Nothing raises, which is exactly why the preview shows the
        parsed amount rather than the file's text.
        """
        wrong = parse_number("1.234,56", ".")
        right = parse_number("1.234,56", ",")
        assert wrong is not None
        assert wrong != right
        assert wrong < 2 and right > 1000


class TestDateFormat:
    def test_day_first_with_slashes(self):
        found = detect_date_format(["06/06/2025", "30/06/2025", "24/07/2025"])
        assert found[0] == "%d/%m/%Y"

    def test_iso(self):
        assert detect_date_format(["2025-06-06", "2025-07-24"])[0] == "%Y-%m-%d"

    def test_day_first_with_dashes(self):
        assert detect_date_format(["06-06-2025", "24-07-2025"])[0] == "%d-%m-%Y"

    def test_dots(self):
        assert detect_date_format(["06.06.2025", "24.07.2025"])[0] == "%d.%m.%Y"

    def test_a_day_over_twelve_settles_the_order(self):
        assert detect_date_format(["24/07/2025", "01/02/2025"])[0] == "%d/%m/%Y"

    def test_unreadable_dates(self):
        assert detect_date_format(["hello", "world"]) is None

    def test_an_empty_column(self):
        assert detect_date_format(["", "  "]) is None


class TestColumnGuessing:
    def test_albanian_headers(self):
        mapping = guess_columns(["Data", "Pershkrimi", "Shuma", "Kategoria"])
        assert mapping["date"] == 0
        assert mapping["description"] == 1
        assert mapping["amount"] == 2

    def test_english_headers(self):
        mapping = guess_columns(["Date", "Description", "Amount"])
        assert mapping["date"] == 0
        assert mapping["amount"] == 2

    def test_a_bank_statement_with_two_amount_columns(self):
        mapping = guess_columns(["Data", "Shpjegimi", "Val.", "Debi", "Kredi", "Bilanci", "Nr.Trx"])
        assert mapping["debit"] == 3
        assert mapping["credit"] == 4
        assert "amount" not in mapping
        assert has_usable_amount(mapping)

    def test_unrecognised_headers_are_left_out(self):
        """Asking is better than guessing wrongly."""
        assert guess_columns(["Foo", "Bar"]) == {}

    def test_has_usable_amount(self):
        assert not has_usable_amount({"date": 0})
        assert has_usable_amount({"amount": 1})
        assert has_usable_amount({"debit": 1})


class TestBuildingCandidates:
    def rows(self):
        return [
            ["01-08-2026", "Paga", "1200.00", "Paga"],
            ["03-08-2026", "Ushqime", "-45.50", "Ushqim"],
        ]

    def mapping(self):
        return {"date": 0, "description": 1, "amount": 2, "category": 3}

    def test_a_positive_amount_is_income(self):
        candidates, _, _ = build_candidates(None, self.rows(), self.mapping())
        assert candidates[0].kind == INCOME
        assert candidates[0].amount == Decimal("1200.00")

    def test_a_negative_amount_is_an_expense(self):
        candidates, _, _ = build_candidates(None, self.rows(), self.mapping())
        assert candidates[1].kind == EXPENSE
        assert candidates[1].amount == Decimal("45.50")

    def test_the_amount_is_stored_positive(self):
        """The program keeps the sign in the type, not in the number."""
        candidates, _, _ = build_candidates(None, self.rows(), self.mapping())
        assert all(c.amount > 0 for c in candidates)

    def test_the_category_is_carried_through(self):
        candidates, _, _ = build_candidates(None, self.rows(), self.mapping())
        assert candidates[0].category == "Paga"

    def test_the_account_is_applied_to_every_row(self):
        candidates, _, _ = build_candidates(None, self.rows(), self.mapping(), account_id=7)
        assert all(c.account_id == 7 for c in candidates)

    def test_separate_debit_and_credit_columns(self):
        rows = [
            ["01-08-2026", "Deponim", "0.00", "15.00"],
            ["02-08-2026", "Blerje", "-5.00", "0.00"],
        ]
        mapping = {"date": 0, "description": 1, "debit": 2, "credit": 3}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert candidates[0].kind == INCOME
        assert candidates[0].amount == Decimal("15.00")
        assert candidates[1].kind == EXPENSE
        assert candidates[1].amount == Decimal("5.00")

    def test_a_debit_without_its_own_minus_sign(self):
        rows = [["01-08-2026", "Blerje", "5.00", "0.00"]]
        mapping = {"date": 0, "description": 1, "debit": 2, "credit": 3}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert candidates[0].kind == EXPENSE

    def test_an_unreadable_date_is_flagged_not_dropped(self):
        rows = [["01-08-2026", "Ok", "10"], ["garbage", "Bad", "10"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert len(candidates) == 2
        assert candidates[1].problem == "date"
        assert not candidates[1].selected

    def test_an_unreadable_amount_is_flagged(self):
        rows = [["01-08-2026", "Bad", "abc"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert candidates[0].problem == "amount"

    def test_a_zero_amount_is_flagged(self):
        rows = [["01-08-2026", "Nothing", "0.00"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert candidates[0].problem == "amount"

    def test_a_missing_description_gets_a_placeholder(self):
        rows = [["01-08-2026", "", "10"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert candidates[0].description == "-"

    def test_european_amounts_are_read_correctly(self):
        rows = [["01-08-2026", "Paga", "1.234,56"], ["02-08-2026", "Kafe", "12,50"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, separator, _ = build_candidates(None, rows, mapping)
        assert separator == ","
        assert candidates[0].amount == Decimal("1234.56")

    def test_the_row_number_is_kept_for_reporting(self):
        candidates, _, _ = build_candidates(None, self.rows(), self.mapping())
        assert [c.row_number for c in candidates] == [2, 3]


class TestDeposits:
    @pytest.mark.parametrize(
        "description",
        ["ATM T003 Deponimi ne llogari", "CASH IN branch", "Deposit at ATM"],
    )
    def test_recognised(self, description):
        assert is_deposit(description)

    def test_ordinary_descriptions_are_not(self):
        assert not is_deposit("E-commerce Steam Purchase")

    def test_treated_as_a_transfer_when_asked(self):
        """Cash into a bank is moved money, not earned money."""
        rows = [["01-08-2026", "ATM Deponimi ne llogari", "15.00"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _, _ = build_candidates(None, rows, mapping, deposit_is_transfer=True)
        assert candidates[0].kind == TRANSFER

    def test_left_as_income_by_default(self):
        rows = [["01-08-2026", "ATM Deponimi ne llogari", "15.00"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _, _ = build_candidates(None, rows, mapping)
        assert candidates[0].kind == INCOME


class TestDuplicates:
    def make(self, description="Qera", amount="300.00", date="01-08-2026"):
        return Candidate(
            row_number=2,
            kind=EXPENSE,
            description=description,
            amount=Decimal(amount),
            occurred_on=date,
        )

    def test_an_identical_row_is_flagged(self, app):
        app.add_transaction(EXPENSE, "Qera", Decimal("300.00"), "01-08-2026", "Qera")
        candidates = mark_duplicates([self.make()], app.transactions())
        assert candidates[0].duplicate_of is not None

    def test_a_flagged_row_is_deselected(self, app):
        app.add_transaction(EXPENSE, "Qera", Decimal("300.00"), "01-08-2026", "Qera")
        candidates = mark_duplicates([self.make()], app.transactions())
        assert not candidates[0].selected

    def test_flagged_rather_than_dropped(self, app):
        """Seeing them is the point; silently skipping hides a real mistake."""
        app.add_transaction(EXPENSE, "Qera", Decimal("300.00"), "01-08-2026", "Qera")
        candidates = mark_duplicates([self.make()], app.transactions())
        assert len(candidates) == 1

    def test_a_different_amount_is_not_a_duplicate(self, app):
        app.add_transaction(EXPENSE, "Qera", Decimal("300.00"), "01-08-2026", "Qera")
        candidates = mark_duplicates([self.make(amount="350.00")], app.transactions())
        assert candidates[0].duplicate_of is None

    def test_a_different_date_is_not_a_duplicate(self, app):
        app.add_transaction(EXPENSE, "Qera", Decimal("300.00"), "01-08-2026", "Qera")
        candidates = mark_duplicates([self.make(date="02-08-2026")], app.transactions())
        assert candidates[0].duplicate_of is None

    def test_matching_ignores_case_and_punctuation(self, app):
        app.add_transaction(EXPENSE, "Qera e Gushtit", Decimal("300.00"), "01-08-2026")
        candidates = mark_duplicates([self.make(description="QERA E GUSHTIT!")], app.transactions())
        assert candidates[0].duplicate_of is not None

    def test_an_unimportable_row_is_left_alone(self, app):
        candidate = self.make()
        candidate.problem = "date"
        mark_duplicates([candidate], app.transactions())
        assert candidate.duplicate_of is None

    def test_normalise(self):
        assert normalise("  Qera,  e Gushtit! ") == "qera e gushtit"
        assert normalise(None) == ""


class TestCommit:
    def make(self, description="Qera", amount="300.00", kind=EXPENSE, category=None):
        return Candidate(
            row_number=2,
            kind=kind,
            description=description,
            amount=Decimal(amount),
            occurred_on="01-08-2026",
            category=category,
        )

    def test_writes_the_selected_rows(self, app):
        assert commit(app, [self.make(), self.make("Ushqime", "45.50")]) == 2
        assert app.count() == 2

    def test_skips_the_deselected(self, app):
        deselected = self.make("Skipped")
        deselected.selected = False
        assert commit(app, [self.make(), deselected]) == 1
        assert [t.description for t in app.transactions()] == ["Qera"]

    def test_skips_the_unimportable(self, app):
        broken = self.make("Broken")
        broken.problem = "date"
        assert commit(app, [broken]) == 0
        assert app.count() == 0

    def test_creates_categories_as_needed(self, app):
        commit(app, [self.make(category="Qera")])
        assert app.transactions()[0].category == "Qera"

    def test_nothing_selected_writes_nothing(self, app):
        assert commit(app, []) == 0
        assert app.count() == 0

    def test_a_failure_writes_nothing_at_all(self, app, monkeypatch):
        """All or nothing: a partial import cannot be told apart from a full one."""
        real = type(app.db).add_transaction
        calls = {"n": 0}

        def flaky(self, transaction, connection=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return real(self, transaction, connection=connection)

        monkeypatch.setattr(type(app.db), "add_transaction", flaky)
        with pytest.raises(RuntimeError):
            commit(app, [self.make("A"), self.make("B"), self.make("C")])
        monkeypatch.undo()

        assert app.count() == 0

    def test_a_failure_after_a_new_category_writes_nothing_either(self, app, monkeypatch):
        """Creating a category used to commit everything written before it, so
        a failure later on kept the first rows - and the category."""
        real = type(app.db).add_transaction
        calls = {"n": 0}

        def flaky(self, transaction, connection=None):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk full")
            return real(self, transaction, connection=connection)

        monkeypatch.setattr(type(app.db), "add_transaction", flaky)
        with pytest.raises(RuntimeError):
            commit(
                app,
                [self.make("A"), self.make("B", category="Krejt e re"), self.make("C")],
            )
        monkeypatch.undo()

        assert app.count() == 0
        assert app.categories(EXPENSE) == []

    def test_an_imported_transfer_keeps_its_type(self, app):
        commit(app, [self.make("Deponim", "15.00", kind=TRANSFER)])
        assert app.transactions()[0].kind == TRANSFER


class TestReadRows:
    def test_header_and_rows_are_separated(self):
        raw = b"Data,Shuma\n01-08-2026,10\n02-08-2026,20\n"
        header, rows, _ = read_rows(raw)
        assert header == ["Data", "Shuma"]
        assert len(rows) == 2

    def test_blank_lines_are_skipped(self):
        raw = b"Data,Shuma\n\n01-08-2026,10\n\n\n"
        _, rows, _ = read_rows(raw)
        assert len(rows) == 1

    def test_a_file_with_only_a_header(self):
        _, rows, _ = read_rows(b"Data,Shuma\n")
        assert rows == []

    def test_an_empty_file_is_rejected(self):
        with pytest.raises(ImportError_):
            read_rows(b"")


class TestTheTypeColumn:
    """A file may say what each row is, and that beats reading the sign.

    The program's own export writes every amount positive with the type in a
    column beside it. Reading only the sign made every exported row come back
    as income - so exporting and importing, which ought to be a round trip,
    quietly turned every expense into earnings.
    """

    def rows(self):
        return [
            ["01-09-2026", "Te Ardhura", "Paga", "1200.00"],
            ["02-09-2026", "Shpenzime", "Qera", "300.00"],
        ]

    def mapping(self):
        return {"date": 0, "kind": 1, "description": 2, "amount": 3}

    def test_the_column_is_recognised(self):
        found = guess_columns(["Data", "Lloji", "Pershkrimi", "Shuma"])
        assert found["kind"] == 1

    def test_the_english_heading_is_recognised(self):
        assert guess_columns(["Date", "Type", "Description", "Amount"])["kind"] == 1

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Te Ardhura", INCOME),
            ("të ardhura", INCOME),
            ("Income", INCOME),
            ("Shpenzime", EXPENSE),
            ("Expense", EXPENSE),
            ("Transferim", TRANSFER),
        ],
    )
    def test_the_words_it_understands(self, text, expected):
        assert parse_kind(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", None, "xyz"])
    def test_anything_else_names_no_type(self, text):
        assert parse_kind(text) is None

    def test_a_positive_amount_can_still_be_an_expense(
        self,
    ):
        """Which is the whole point: the export writes them all positive."""
        candidates, _sep, _fmt = build_candidates(None, self.rows(), self.mapping())
        assert candidates[0].kind == INCOME
        assert candidates[1].kind == EXPENSE

    def test_the_sign_is_used_when_there_is_no_column(self):
        rows = [["01-09-2026", "Paga", "1200.00"], ["02-09-2026", "Qera", "-300.00"]]
        mapping = {"date": 0, "description": 1, "amount": 2}
        candidates, _sep, _fmt = build_candidates(None, rows, mapping)
        assert candidates[0].kind == INCOME
        assert candidates[1].kind == EXPENSE

    def test_an_unreadable_type_falls_back_to_the_sign(self):
        rows = [["01-09-2026", "xyz", "Qera", "-300.00"]]
        candidates, _sep, _fmt = build_candidates(None, rows, self.mapping())
        assert candidates[0].kind == EXPENSE

    def test_a_stated_type_beats_a_deposit_looking_description(self):
        rows = [["01-09-2026", "Te Ardhura", "ATM Deponimi ne llogari", "50.00"]]
        candidates, _sep, _fmt = build_candidates(
            None, rows, self.mapping(), deposit_is_transfer=True
        )
        assert candidates[0].kind == INCOME

    def test_exporting_and_importing_is_a_round_trip(self, app, tmp_path, monkeypatch):
        """The case that was broken: every expense came back as income."""
        from decimal import Decimal

        from personal_finance.export import export_transactions

        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        app.add_transaction(INCOME, "Paga", Decimal("1200"), "01-09-2026", "Paga")
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "02-09-2026", "Qera")

        _count, written = export_transactions("dalje", app.transactions())
        with open(written, "rb") as handle:
            header, rows, _encoding = read_rows(handle.read())

        mapping = guess_columns(header)
        candidates, _sep, _fmt = build_candidates(header, rows, mapping)
        assert [c.kind for c in candidates] == [INCOME, EXPENSE]
        assert [c.amount for c in candidates] == [Decimal("1200.00"), Decimal("300.00")]
