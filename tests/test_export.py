"""Tests for CSV export.

Export exists to be opened by a person in a spreadsheet, so most of these are
about that file being readable rather than about the data being correct: the
byte order mark Excel needs, blank cells rather than placeholder words,
amounts as plain numbers, and a delimiter that suits the reader's locale.
"""

import csv
import os

import pytest

from personal_finance import colors, i18n
from personal_finance.cli import main
from personal_finance.export import (
    ALLOWED_DELIMITERS,
    column_titles,
    export_transactions,
    transaction_row,
)
from personal_finance.schema import EXPENSE, INCOME, TRANSFER

from .conftest import make_view


def entry(
    kind=EXPENSE,
    amount="10.00",
    category="Ushqim",
    subcategory=None,
    account=None,
    destination=None,
    date="15-06-2026",
    description="Test",
):
    return make_view(
        kind,
        description,
        amount,
        date,
        category=category,
        subcategory=subcategory,
        account=account,
        to_account=destination,
    )


def read_back(path, delimiter=","):
    """Read an exported file the way a spreadsheet would."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle, delimiter=delimiter))


@pytest.fixture(autouse=True)
def plain():
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield
    i18n.set_language("sq")


class TestFileIsSpreadsheetReadable:
    def test_writes_a_byte_order_mark(self, tmp_path):
        """Without it Excel assumes the system code page and mangles ë and ç."""
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry()])
        with open(path, "rb") as handle:
            assert handle.read(3) == b"\xef\xbb\xbf"

    def test_accented_text_survives(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(description="Ëmbëlsira dhe çaj")])
        assert read_back(path)[1][2] == "Ëmbëlsira dhe çaj"

    def test_header_row_comes_first(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry()])
        assert read_back(path)[0] == column_titles()

    def test_amounts_are_plain_numbers(self, tmp_path):
        """A currency symbol would make the column text, not numbers."""
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(amount="1200.00")])
        cell = read_back(path)[1][-1]
        assert cell == "1200.00"
        assert float(cell) == 1200.00

    def test_amounts_keep_two_decimals(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(amount="5")])
        assert read_back(path)[1][-1] == "5.00"

    def test_amounts_stay_positive_with_type_in_its_own_column(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(EXPENSE, amount="10.00")])
        row = read_back(path)[1]
        assert row[-1] == "10.00"
        assert row[1] == "Shpenzime"

    def test_a_comma_in_a_description_does_not_break_the_row(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(description="Buke, qumesht dhe vaj")])
        rows = read_back(path)
        assert len(rows) == 2
        assert rows[1][2] == "Buke, qumesht dhe vaj"


class TestEmptyFieldsAreBlank:
    def test_missing_subcategory_is_a_blank_cell(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(subcategory="")])
        assert read_back(path)[1][4] == ""

    def test_missing_account_is_a_blank_cell(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(account="")])
        assert read_back(path)[1][5] == ""

    def test_an_absent_category_is_a_blank_cell(self, tmp_path):
        """Absence is NULL now, so this is simply an empty string."""
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(category=None)])
        assert read_back(path)[1][3] == ""

    def test_screen_labels_do_not_leak_into_the_file(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(category=None, subcategory=None, account=None)])
        contents = open(path, encoding="utf-8-sig").read()
        assert "Pa nenkategori" not in contents
        assert "Pa llogari" not in contents

    def test_destination_is_blank_for_non_transfers(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(EXPENSE, account="Kesh", destination="Banka")])
        assert read_back(path)[1][6] == ""

    def test_transfer_writes_both_accounts(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(TRANSFER, account="Banka", destination="Kesh")])
        row = read_back(path)[1]
        assert row[5] == "Banka"
        assert row[6] == "Kesh"


class TestDelimiters:
    @pytest.mark.parametrize("delimiter", ALLOWED_DELIMITERS)
    def test_each_allowed_delimiter_round_trips(self, tmp_path, delimiter):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry()], delimiter=delimiter)
        assert len(read_back(path, delimiter)) == 2

    def test_semicolon_for_comma_decimal_locales(self, tmp_path):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry()], delimiter=";")
        assert ";" in open(path, encoding="utf-8-sig").readline()

    def test_an_unknown_delimiter_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            export_transactions(str(tmp_path / "out.csv"), [entry()], delimiter="~")

    def test_nothing_is_written_when_the_delimiter_is_rejected(self, tmp_path):
        path = str(tmp_path / "out.csv")
        with pytest.raises(ValueError):
            export_transactions(path, [entry()], delimiter="~")
        assert not os.path.exists(path)


class TestWriteSafety:
    def test_leaves_no_temporary_file_behind(self, tmp_path):
        export_transactions(str(tmp_path / "out.csv"), [entry()])
        assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")] == []

    def test_a_failed_write_leaves_the_previous_file_intact(self, tmp_path, monkeypatch):
        path = str(tmp_path / "out.csv")
        export_transactions(path, [entry(description="Origjinali")])

        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            export_transactions(path, [entry(description="I riu")])
        monkeypatch.undo()

        assert read_back(path)[1][2] == "Origjinali"

    def test_a_failed_write_cleans_up(self, tmp_path, monkeypatch):
        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            export_transactions(str(tmp_path / "out.csv"), [entry()])
        monkeypatch.undo()

        assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")] == []

    def test_creates_a_missing_directory(self, tmp_path):
        path = str(tmp_path / "nested" / "deeper" / "out.csv")
        export_transactions(path, [entry()])
        assert os.path.exists(path)

    def test_empty_list_writes_just_the_header(self, tmp_path):
        path = str(tmp_path / "out.csv")
        count, _written_to = export_transactions(path, [])
        assert count == 0
        assert len(read_back(path)) == 1

    def test_returns_the_row_count_and_where_it_wrote(self, tmp_path):
        path = str(tmp_path / "out.csv")
        count, written_to = export_transactions(path, [entry(), entry(), entry()])
        assert count == 3
        assert written_to == os.path.abspath(path)


class TestLanguage:
    def test_albanian_headers(self):
        assert column_titles()[0] == "Data"
        assert column_titles()[1] == "Lloji"

    def test_english_headers(self):
        i18n.set_language("en")
        titles = column_titles()
        assert titles[0] == "Date"
        assert titles[1] == "Type"

    def test_type_labels_follow_the_language(self):
        i18n.set_language("en")
        assert transaction_row(entry(INCOME))[1] == "Income"

    def test_stored_values_are_not_translated(self):
        """Only headers and type labels change; the data itself is untouched."""
        i18n.set_language("en")
        row = transaction_row(entry(category="Ushqim", account="Kesh"))
        assert row[3] == "Ushqim"
        assert row[5] == "Kesh"


class TestCliExport:
    @pytest.fixture(autouse=True)
    def seeded(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        main(["--shto-llogari", "Banka", "Banke", "500"])
        main(["--shto-llogari", "Kesh", "Kesh", "40"])
        for description, amount, date, category, account in [
            ("Paga", "1200", "01-08-2026", "Paga", "Banka"),
            ("Ushqime", "12.50", "03-08-2026", "Ushqim", "Kesh"),
            ("Benzine", "60", "10-08-2026", "Transport", "Banka"),
        ]:
            main(
                [
                    "--shto-shpenzime" if description != "Paga" else "--shto-te-ardhura",
                    "--pershkrimi",
                    description,
                    "--shuma",
                    amount,
                    "--data",
                    date,
                    "--kategoria",
                    category,
                    "--nenkategoria",
                    "",
                    "--llogaria",
                    account,
                ]
            )
        capsys.readouterr()
        return tmp_path

    def test_exports_everything(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target])
        assert "U eksportuan 3" in capsys.readouterr().out
        assert len(read_back(target)) == 4

    def test_rows_are_chronological(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target])
        capsys.readouterr()
        dates = [row[0] for row in read_back(target)[1:]]
        assert dates == ["01-08-2026", "03-08-2026", "10-08-2026"]

    def test_date_range_filter(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--nga", "01-08-2026", "--deri", "05-08-2026"])
        capsys.readouterr()
        assert len(read_back(target)) == 3

    def test_single_date_filter(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--data", "03-08-2026"])
        capsys.readouterr()
        assert len(read_back(target)) == 2

    def test_account_filter(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--llogaria", "Kesh"])
        capsys.readouterr()
        assert len(read_back(target)) == 2

    def test_search_filter(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--kerko", "Benzine"])
        capsys.readouterr()
        assert len(read_back(target)) == 2

    def test_unknown_account_is_rejected_and_writes_nothing(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--llogaria", "Nope"])
        assert "nuk ekziston" in capsys.readouterr().out
        assert not os.path.exists(target)

    def test_invalid_date_is_rejected_and_writes_nothing(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--data", "99-99-9999"])
        assert "pavlefshem" in capsys.readouterr().out.lower()
        assert not os.path.exists(target)

    def test_a_filter_matching_nothing_writes_nothing(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--data", "01-01-2020"])
        assert "asnje transaksion" in capsys.readouterr().out
        assert not os.path.exists(target)

    def test_delimiter_flag(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--ndares", ";"])
        capsys.readouterr()
        assert len(read_back(target, ";")) == 4

    def test_bad_delimiter_is_rejected(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--ndares", "~"])
        assert "pavlefshem" in capsys.readouterr().out.lower()
        assert not os.path.exists(target)

    def test_english_alias_and_headers(self, seeded, capsys):
        target = str(seeded / "out.csv")
        main(["--gjuha", "en", "--export", target])
        capsys.readouterr()
        assert read_back(target)[0][0] == "Date"

    def test_export_does_not_print_the_transaction_table(self, seeded, capsys):
        """--kerko with --eksporto should write the file, not list to screen."""
        target = str(seeded / "out.csv")
        main(["--eksporto", target, "--kerko", "Benzine"])
        output = capsys.readouterr().out
        assert "Te gjitha transaksionet" not in output
        assert "U eksportuan" in output

    def test_no_startup_notice_in_export_mode(self, seeded, capsys):
        main(["--eksporto", str(seeded / "out.csv")])
        assert "Jane lexuar" not in capsys.readouterr().out


def test_a_plain_view_exports_cleanly(tmp_path):
    path = str(tmp_path / "out.csv")
    export_transactions(path, [make_view()])
    assert len(read_back(path)) == 2
