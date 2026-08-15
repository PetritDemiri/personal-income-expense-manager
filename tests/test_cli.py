"""End-to-end tests for the app service layer and the command-line interface."""

import datetime
from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.cli import build_parser, main
from personal_finance.config import EXPENSE, INCOME

from .conftest import make_rule


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Point the app at a temp directory and reset global display state."""
    monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield tmp_path


class TestAppLayer:
    def test_add_persists_across_reloads(self, app, storage):
        app.add_transaction(INCOME, "Paga", Decimal("1000"), "01-06-2026", "Paga")

        from personal_finance.app import FinanceApp

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert len(reloaded.transactions) == 1
        assert reloaded.transactions[0].shuma == Decimal("1000")

    def test_delete_persists(self, app, storage):
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        app.delete_transaction(0)

        from personal_finance.app import FinanceApp

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert reloaded.transactions == []

    def test_update_persists(self, app, storage):
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        app.update_transaction(0, shuma=Decimal("350"))

        from personal_finance.app import FinanceApp

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert reloaded.transactions[0].shuma == Decimal("350")

    def test_process_recurring_persists_and_is_idempotent(self, app, storage):
        app.recurring_rules.append(make_rule(start="01-06-2026"))
        app.save_recurring()

        first = app.process_recurring(as_of=datetime.date(2026, 8, 7))
        assert len(first) == 3

        from personal_finance.app import FinanceApp

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert len(reloaded.transactions) == 3
        assert reloaded.process_recurring(as_of=datetime.date(2026, 8, 7)) == []

    def test_categories_include_ones_already_used(self, app):
        app.add_transaction(EXPENSE, "Kafe", Decimal("2"), "01-06-2026", "Kafene")
        assert "Kafene" in app.categories_for(EXPENSE)

    def test_set_budget_persists(self, app, storage):
        app.set_budget("Ushqim", Decimal("200"))

        from personal_finance.app import FinanceApp

        reloaded = FinanceApp(storage=storage, quiet=True)
        reloaded.load()
        assert reloaded.budgets[0].kategoria == "Ushqim"


class TestParser:
    def test_albanian_flags(self):
        args = build_parser().parse_args(["--lista", "--gjendja"])
        assert args.lista and args.gjendja

    def test_english_aliases(self):
        args = build_parser().parse_args(["--list", "--balance"])
        assert args.lista and args.gjendja

    def test_add_flags_with_fields(self):
        args = build_parser().parse_args(
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
        assert args.shto_shpenzime
        assert args.pershkrimi == "Qera"
        assert args.shuma == "300"

    def test_language_flag(self):
        assert build_parser().parse_args(["--gjuha", "en"]).gjuha == "en"
        assert build_parser().parse_args(["--language", "en"]).gjuha == "en"

    def test_language_defaults_to_albanian(self):
        assert build_parser().parse_args([]).gjuha == "sq"

    def test_invalid_language_is_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--gjuha", "de"])

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as excinfo:
            build_parser().parse_args(["--ndihma"])
        assert excinfo.value.code == 0


class TestCliEndToEnd:
    def test_add_then_list(self, capsys):
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
        output = capsys.readouterr().out
        assert "Qera" in output
        assert "300.00" in output

    def test_income_appears_in_the_balance(self, capsys):
        """Guards the bug where income silently totalled zero."""
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
        assert "1000.00" in output
        assert "Te Ardhurat Totale: €1000.00" in output

    def test_balance_arithmetic(self, capsys):
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
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Qera",
                "--shuma",
                "300",
                "--data",
                "02-06-2026",
                "--kategoria",
                "Qera",
            ]
        )
        capsys.readouterr()

        main(["--gjendja"])
        assert "Gjendja Aktuale: €700.00" in capsys.readouterr().out

    def test_invalid_amount_is_rejected(self, capsys, tmp_path):
        main(
            [
                "--csv",
                "--shto-shpenzime",
                "--pershkrimi",
                "x",
                "--shuma",
                "abc",
                "--data",
                "01-06-2026",
                "--kategoria",
                "y",
            ]
        )
        assert "pavlefshme" in capsys.readouterr().out
        assert not (tmp_path / "transactions.csv").exists()

    def test_invalid_date_is_rejected(self, capsys, tmp_path):
        main(
            [
                "--csv",
                "--shto-shpenzime",
                "--pershkrimi",
                "x",
                "--shuma",
                "10",
                "--data",
                "99-99-9999",
                "--kategoria",
                "y",
            ]
        )
        assert "pavlefshem" in capsys.readouterr().out
        assert not (tmp_path / "transactions.csv").exists()

    def test_single_date_filter(self, capsys):
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
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Ushqime",
                "--shuma",
                "50",
                "--data",
                "15-06-2026",
                "--kategoria",
                "Ushqim",
            ]
        )
        capsys.readouterr()

        main(["--lista", "--data", "01-06-2026"])
        output = capsys.readouterr().out
        assert "Qera" in output
        assert "Ushqime" not in output

    def test_date_range_filter_is_inclusive(self, capsys):
        for day in ("01", "15", "28"):
            main(
                [
                    "--shto-shpenzime",
                    "--pershkrimi",
                    f"Dita{day}",
                    "--shuma",
                    "10",
                    "--data",
                    f"{day}-06-2026",
                    "--kategoria",
                    "Ushqim",
                ]
            )
        capsys.readouterr()

        main(["--lista", "--nga", "01-06-2026", "--deri", "15-06-2026"])
        output = capsys.readouterr().out
        assert "Dita01" in output and "Dita15" in output
        assert "Dita28" not in output

    def test_reversed_range_is_rejected(self, capsys):
        main(["--lista", "--nga", "15-06-2026", "--deri", "01-06-2026"])
        assert "nuk mund te jete para" in capsys.readouterr().out

    def test_search(self, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Ushqime nga dyqani",
                "--shuma",
                "50",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Ushqim",
            ]
        )
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Benzine",
                "--shuma",
                "60",
                "--data",
                "02-06-2026",
                "--kategoria",
                "Transport",
            ]
        )
        capsys.readouterr()

        main(["--kerko", "dyqani"])
        output = capsys.readouterr().out
        assert "Ushqime nga dyqani" in output
        assert "Benzine" not in output

    def test_budget_set_and_view(self, capsys):
        main(["--cakto-buxhet", "Ushqim", "200"])
        capsys.readouterr()

        main(["--buxhetet"])
        output = capsys.readouterr().out
        assert "Ushqim" in output
        assert "200.00" in output

    def test_budget_warning_when_exceeded(self, capsys):
        main(["--cakto-buxhet", "Ushqim", "100"])
        capsys.readouterr()

        today = datetime.date.today().strftime("%d-%m-%Y")
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Shume ushqim",
                "--shuma",
                "150",
                "--data",
                today,
                "--kategoria",
                "Ushqim",
            ]
        )
        assert "KUJDES" in capsys.readouterr().out

    def test_monthly_report(self, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Qera",
                "--shuma",
                "300",
                "--data",
                "15-06-2026",
                "--kategoria",
                "Qera",
            ]
        )
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

    def test_language_does_not_change_stored_data(self, capsys, tmp_path):
        main(
            [
                "--csv",
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
            ]
        )
        capsys.readouterr()

        stored = (tmp_path / "transactions.csv").read_text(encoding="utf-8")
        # Stored type stays Albanian regardless of the display language.
        assert "Shpenzime" in stored
        assert "Expenses" not in stored

    def test_recurring_generates_and_lists(self, capsys, tmp_path):
        (tmp_path / "recurring.csv").write_text(
            "lloji,pershkrimi,shuma,kategoria,frekuenca,data_fillimit,data_e_fundit\n"
            f"{EXPENSE},Qera,300.00,Qera,mujore,01-01-2026,\n",
            encoding="utf-8",
        )

        main(["--csv", "--perserit"])
        assert "gjeneruan" in capsys.readouterr().out

        main(["--csv", "--perseritjet"])
        assert "Qera" in capsys.readouterr().out

    def test_recurring_does_not_duplicate_across_runs(self, capsys, tmp_path):
        (tmp_path / "recurring.csv").write_text(
            "lloji,pershkrimi,shuma,kategoria,frekuenca,data_fillimit,data_e_fundit\n"
            f"{EXPENSE},Qera,300.00,Qera,mujore,01-01-2026,\n",
            encoding="utf-8",
        )

        main(["--csv", "--perserit"])
        capsys.readouterr()
        first = (tmp_path / "transactions.csv").read_text(encoding="utf-8")

        main(["--csv", "--perserit"])
        capsys.readouterr()
        assert (tmp_path / "transactions.csv").read_text(encoding="utf-8") == first

    def test_listing_is_chronological(self, capsys):
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Vone",
                "--shuma",
                "10",
                "--data",
                "20-06-2026",
                "--kategoria",
                "Ushqim",
            ]
        )
        main(
            [
                "--shto-shpenzime",
                "--pershkrimi",
                "Heret",
                "--shuma",
                "10",
                "--data",
                "01-06-2026",
                "--kategoria",
                "Ushqim",
            ]
        )
        capsys.readouterr()

        main(["--lista"])
        output = capsys.readouterr().out
        assert output.index("Heret") < output.index("Vone")

    def test_no_color_output_has_no_escape_codes(self, capsys):
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

        main(["--lista", "--pa-ngjyra"])
        assert "\033[" not in capsys.readouterr().out

    def test_exit_code_is_zero_on_success(self):
        assert main(["--gjendja"]) == 0
