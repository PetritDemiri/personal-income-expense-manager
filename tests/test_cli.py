"""End-to-end tests for the command-line interface.

Each test drives main() against a temporary database, so these exercise the
whole stack: parser, service layer, database, display.
"""

import datetime
import os
from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.cli import ACTION_FLAGS, action_flag_dests, build_parser, main
from personal_finance.schema import EXPENSE


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield tmp_path
    i18n.set_language("sq")


def add_income(description="Paga", amount="1000", date="01-06-2026", category="Paga", *extra):
    main(
        [
            "--shto-te-ardhura",
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
            *extra,
        ]
    )


def add_expense(description="Qera", amount="300", date="02-06-2026", category="Qera", *extra):
    main(
        [
            "--shto-shpenzime",
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
            *extra,
        ]
    )


class TestParser:
    def test_albanian_flags(self):
        args = build_parser().parse_args(["--lista", "--gjendja"])
        assert args.lista and args.gjendja

    def test_english_aliases(self):
        args = build_parser().parse_args(["--list", "--balance"])
        assert args.lista and args.gjendja

    def test_language_defaults_to_albanian(self):
        assert build_parser().parse_args([]).gjuha == "sq"

    def test_invalid_language_is_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--gjuha", "de"])

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as info:
            build_parser().parse_args(["--ndihma"])
        assert info.value.code == 0

    def test_action_flags_matches_the_parser(self):
        """A hand-written list drifted twice; this is the guard."""
        dests = set(action_flag_dests(build_parser()))
        assert dests
        assert dests == set(ACTION_FLAGS)

    def test_no_startup_notice_in_flag_mode(self, capsys):
        main(["--gjendja"])
        assert "Jane lexuar" not in capsys.readouterr().out


class TestAddingAndListing:
    def test_add_then_list(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--lista"])
        output = capsys.readouterr().out
        assert "Qera" in output
        assert "300.00" in output

    def test_income_appears_in_the_balance(self, capsys):
        """Guards the bug where income silently totalled zero."""
        add_income()
        capsys.readouterr()
        main(["--gjendja"])
        assert "Te Ardhurat Totale: €1000.00" in capsys.readouterr().out

    def test_balance_arithmetic(self, capsys):
        add_income()
        add_expense()
        capsys.readouterr()
        main(["--gjendja"])
        assert "Gjendja Aktuale: €700.00" in capsys.readouterr().out

    def test_listing_is_chronological(self, capsys):
        add_expense("Vone", "10", "20-06-2026")
        add_expense("Heret", "10", "01-06-2026")
        capsys.readouterr()
        main(["--lista"])
        output = capsys.readouterr().out
        assert output.index("Heret") < output.index("Vone")

    def test_invalid_amount_is_rejected(self, isolated, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "x",
                "--shuma",
                "abc",
                "--data",
                "01-06-2026",
                "--kategoria",
                "y",
                "--nenkategoria",
                "",
            ]
        )
        assert "pavlefshme" in capsys.readouterr().out
        main(["--gjendja"])
        assert "Numri i Transaksioneve: 0" in capsys.readouterr().out

    def test_invalid_date_is_rejected(self, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "x",
                "--shuma",
                "10",
                "--data",
                "99-99-9999",
                "--kategoria",
                "y",
                "--nenkategoria",
                "",
            ]
        )
        assert "pavlefshem" in capsys.readouterr().out.lower()

    def test_a_new_category_is_created_on_first_use(self, capsys):
        add_expense(category="Kafene")
        capsys.readouterr()
        main(["--lista"])
        assert "Kafene" in capsys.readouterr().out


class TestFilters:
    def test_single_date(self, capsys):
        add_expense("Qera", "300", "01-06-2026")
        add_expense("Ushqime", "50", "15-06-2026")
        capsys.readouterr()
        main(["--lista", "--data", "01-06-2026"])
        output = capsys.readouterr().out
        assert "Qera" in output
        assert "Ushqime" not in output

    def test_date_range_is_inclusive(self, capsys):
        for day in ("01", "15", "28"):
            add_expense(f"Dita{day}", "10", f"{day}-06-2026")
        capsys.readouterr()
        main(["--lista", "--nga", "01-06-2026", "--deri", "15-06-2026"])
        output = capsys.readouterr().out
        assert "Dita01" in output and "Dita15" in output
        assert "Dita28" not in output

    def test_reversed_range_is_rejected(self, capsys):
        main(["--lista", "--nga", "15-06-2026", "--deri", "01-06-2026"])
        assert "nuk mund te jete para" in capsys.readouterr().out

    def test_search_by_description(self, capsys):
        add_expense("Ushqime nga dyqani", "50", "01-06-2026", "Ushqim")
        add_expense("Benzine", "60", "02-06-2026", "Transport")
        capsys.readouterr()
        main(["--kerko", "dyqani"])
        output = capsys.readouterr().out
        assert "Ushqime nga dyqani" in output
        assert "Benzine" not in output

    def test_search_matches_a_category_name(self, capsys):
        """Approved behaviour: search reaches the joined names."""
        add_expense("Asgje e vecante", "50", "01-06-2026", "Transport")
        capsys.readouterr()
        main(["--kerko", "Transport"])
        assert "Asgje e vecante" in capsys.readouterr().out


class TestAccounts:
    def test_add_and_view(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "850"])
        capsys.readouterr()
        main(["--llogarite"])
        output = capsys.readouterr().out
        assert "Banka" in output
        assert "850.00" in output

    def test_account_kind_matching_ignores_case(self, capsys):
        main(["--shto-llogari", "Banka", "banke", "0"])
        capsys.readouterr()
        main(["--llogarite"])
        assert "Banke" in capsys.readouterr().out

    def test_negative_opening_is_allowed(self, capsys):
        main(["--shto-llogari", "Karta", "Karte", "-250"])
        capsys.readouterr()
        main(["--llogarite"])
        assert "-250.00" in capsys.readouterr().out

    def test_unknown_kind_is_rejected_by_name(self, capsys):
        main(["--shto-llogari", "X", "Kripto", "100"])
        output = capsys.readouterr().out
        assert "Lloj i pavlefshem" in output
        assert "Kesh" in output

    def test_duplicate_name_is_rejected(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "0"])
        capsys.readouterr()
        main(["--shto-llogari", "banka", "Banke", "0"])
        assert "ekziston" in capsys.readouterr().out

    def test_unknown_account_on_add_is_rejected(self, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "x",
                "--shuma",
                "10",
                "--data",
                "01-06-2026",
                "--kategoria",
                "y",
                "--nenkategoria",
                "",
                "--llogaria",
                "NukEkziston",
            ]
        )
        output = capsys.readouterr().out
        assert "NukEkziston" in output
        assert "nuk ekziston" in output

    def test_account_filter(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "0"])
        main(["--shto-llogari", "Kesh", "Kesh", "0"])
        add_expense("Qera", "300", "01-06-2026", "Qera", "--llogaria", "Banka")
        add_expense("Kafe", "3", "02-06-2026", "Ushqim", "--llogaria", "Kesh")
        capsys.readouterr()
        main(["--lista", "--llogaria", "Kesh"])
        output = capsys.readouterr().out
        assert "Kafe" in output
        assert "Qera" not in output

    def test_no_account_column_when_none_are_used(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--lista"])
        assert "Llogaria" not in capsys.readouterr().out


class TestTransfers:
    @pytest.fixture(autouse=True)
    def two_accounts(self, capsys):
        main(["--shto-llogari", "Banka", "Banke", "850"])
        main(["--shto-llogari", "Kesh", "Kesh", "40"])
        capsys.readouterr()

    def test_moves_money_between_accounts(self, capsys):
        main(["--transfero", "Banka", "Kesh", "--shuma", "200"])
        assert "regjistrua" in capsys.readouterr().out
        main(["--llogarite"])
        output = capsys.readouterr().out
        assert "650.00" in output
        assert "240.00" in output

    def test_is_not_counted_as_spending(self, capsys):
        main(["--transfero", "Banka", "Kesh", "--shuma", "200"])
        capsys.readouterr()
        main(["--gjendja"])
        output = capsys.readouterr().out
        assert "Shpenzimet Totale: €0.00" in output
        assert "Te Ardhurat Totale: €0.00" in output

    def test_same_account_is_rejected(self, capsys):
        main(["--transfero", "Banka", "Banka", "--shuma", "50"])
        assert "njejta" in capsys.readouterr().out

    def test_unknown_account_is_named(self, capsys):
        main(["--transfero", "Nope", "Kesh", "--shuma", "50"])
        assert "Nope" in capsys.readouterr().out

    def test_missing_amount_is_rejected(self, capsys):
        main(["--transfero", "Banka", "Kesh"])
        assert "pavlefshme" in capsys.readouterr().out.lower()


class TestBudgets:
    def test_set_and_view(self, capsys):
        main(["--cakto-buxhet", "Ushqim", "200"])
        capsys.readouterr()
        main(["--buxhetet"])
        output = capsys.readouterr().out
        assert "Ushqim" in output
        assert "200.00" in output

    def test_warning_when_exceeded(self, capsys):
        main(["--cakto-buxhet", "Ushqim", "100"])
        capsys.readouterr()
        today = datetime.date.today().strftime("%d-%m-%Y")
        add_expense("Shume ushqim", "150", today, "Ushqim")
        assert "KUJDES" in capsys.readouterr().out

    def test_zero_limit_is_rejected(self, capsys):
        main(["--cakto-buxhet", "Ushqim", "0"])
        assert "pavlefshme" in capsys.readouterr().out


class TestRecurring:
    def test_generates_and_lists(self, capsys):
        # Rules are created through the menu, so this drives the app directly.
        from personal_finance.app import FinanceApp
        from personal_finance.config import DATABASE_FILE, data_path

        app = FinanceApp(path=data_path(DATABASE_FILE), quiet=True)
        app.add_recurring_rule(EXPENSE, "Qera", Decimal("300"), "mujore", "01-01-2026")
        app.close()

        main(["--perserit"])
        assert "gjeneruan" in capsys.readouterr().out
        main(["--perseritjet"])
        assert "Qera" in capsys.readouterr().out

    def test_does_not_duplicate_across_runs(self, capsys):
        from personal_finance.app import FinanceApp
        from personal_finance.config import DATABASE_FILE, data_path

        app = FinanceApp(path=data_path(DATABASE_FILE), quiet=True)
        app.add_recurring_rule(EXPENSE, "Qera", Decimal("300"), "mujore", "01-01-2026")
        app.close()

        main(["--perserit"])
        capsys.readouterr()
        main(["--gjendja"])
        first = capsys.readouterr().out
        main(["--perserit"])
        capsys.readouterr()
        main(["--gjendja"])
        assert capsys.readouterr().out == first


class TestReportsAndLanguage:
    def test_monthly_report(self, capsys):
        add_expense("Qera", "300", "15-06-2026", "Qera")
        capsys.readouterr()
        main(["--raporti", "--muaji", "06-2026"])
        output = capsys.readouterr().out
        assert "06-2026" in output
        assert "300.00" in output

    def test_invalid_month_is_rejected(self, capsys):
        main(["--raporti", "--muaji", "nonsense"])
        assert "pavlefshem" in capsys.readouterr().out.lower()

    def test_english_interface(self, capsys):
        main(["--gjuha", "en", "--gjendja"])
        output = capsys.readouterr().out
        assert "Financial Summary" in output
        assert "Total Income" in output

    def test_language_does_not_change_stored_data(self, capsys):
        main(
            [
                "--gjuha",
                "en",
                "--add-expense",
                "--description",
                "Rent",
                "--amount",
                "300",
                "--date",
                "01-06-2026",
                "--category",
                "Qera",
                "--subcategory",
                "",
            ]
        )
        capsys.readouterr()
        main(["--lista"])
        output = capsys.readouterr().out
        assert "Shpenzime" in output
        assert "Qera" in output

    def test_no_color_output_has_no_escape_codes(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--lista", "--pa-ngjyra"])
        assert "\033[" not in capsys.readouterr().out

    def test_exit_code_is_zero_on_success(self):
        assert main(["--gjendja"]) == 0


class TestExport:
    def test_exports_and_reports_the_path(self, isolated, capsys):
        add_expense()
        capsys.readouterr()
        target = str(isolated / "out.csv")
        main(["--eksporto", target])
        assert "U eksportuan 1" in capsys.readouterr().out
        assert os.path.exists(target)

    def test_filters_apply_to_export(self, isolated, capsys):
        add_expense("Qera", "300", "01-06-2026")
        add_expense("Ushqime", "50", "15-06-2026", "Ushqim")
        capsys.readouterr()
        target = str(isolated / "out.csv")
        main(["--eksporto", target, "--data", "01-06-2026"])
        capsys.readouterr()
        with open(target, encoding="utf-8-sig") as handle:
            assert len(handle.readlines()) == 2

    def test_export_does_not_print_the_table(self, isolated, capsys):
        add_expense()
        capsys.readouterr()
        main(["--eksporto", str(isolated / "out.csv"), "--kerko", "Qera"])
        output = capsys.readouterr().out
        assert "Te gjitha transaksionet" not in output
        assert "U eksportuan" in output


class TestDatabaseFlag:
    def test_custom_database_path(self, isolated, capsys):
        target = isolated / "custom" / "mydata.db"
        main(["--baza", str(target), "--gjendja"])
        capsys.readouterr()
        assert target.exists()


class TestDetailsFlag:
    def test_timestamps_are_hidden_by_default(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--lista"])
        output = capsys.readouterr().out
        assert "Regjistruar" not in output
        assert "Ndryshuar" not in output

    def test_the_flag_shows_them(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--lista", "--detaje"])
        output = capsys.readouterr().out
        assert "Regjistruar" in output
        assert "Ndryshuar" in output

    def test_english_alias_and_headers(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--gjuha", "en", "--list", "--details"])
        output = capsys.readouterr().out
        assert "Recorded" in output
        assert "Changed" in output


class TestHistoryFlag:
    def test_shows_recent_changes(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--historia"])
        output = capsys.readouterr().out
        assert "Historiku i ndryshimeve" in output
        assert "Shtuar" in output

    def test_an_empty_log_says_so(self, capsys):
        main(["--historia"])
        assert "asnje ndryshim" in capsys.readouterr().out

    def test_money_is_shown_in_euros_not_cents(self, capsys):
        add_expense("Qera", "300", "01-06-2026")
        capsys.readouterr()
        main(["--historia"])
        output = capsys.readouterr().out
        assert "€300.00" in output
        assert "30000" not in output

    def test_filtering_to_one_transaction(self, capsys):
        add_expense("Qera", "300", "01-06-2026")
        add_expense("Ushqime", "50", "02-06-2026", "Ushqim")
        capsys.readouterr()
        main(["--historia", "1"])
        output = capsys.readouterr().out
        assert "Qera" in output
        assert "Ushqime" not in output

    def test_an_out_of_range_number_is_rejected(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--historia", "99"])
        assert "pavlefshem" in capsys.readouterr().out.lower()

    def test_english_alias_and_labels(self, capsys):
        add_expense()
        capsys.readouterr()
        main(["--gjuha", "en", "--history"])
        output = capsys.readouterr().out
        assert "Change history" in output
        assert "Added" in output

    def test_editing_shows_only_what_changed(self, capsys):
        """One entry per edit, listing one field."""
        from personal_finance.app import FinanceApp
        from personal_finance.config import DATABASE_FILE, data_path

        add_expense("Qera", "300", "01-06-2026")
        app = FinanceApp(path=data_path(DATABASE_FILE), quiet=True)
        app.update_transaction(app.transactions()[0].id, amount=Decimal("350"))
        app.close()
        capsys.readouterr()

        main(["--historia"])
        output = capsys.readouterr().out
        assert output.count("Ndryshuar transaksion") == 1
        assert "€300.00  ->  €350.00" in output
