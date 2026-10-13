"""Tests for adding several income or expense entries at once.

Menu options 1 and 2 first ask how many. Each entry is then asked for exactly
as a single one always was; from the second on, the date, category,
subcategory and account of the one before are offered so Enter keeps them.
Several are shown as a list before anything is saved, where a row can be
changed or taken out, and then saved together - every one of them or none.
"""

from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.dates import current_date_str
from personal_finance.models import BANK, CASH
from personal_finance.schema import EXPENSE, INCOME
from personal_finance.ui import MENU_ITEMS, MOST_AT_ONCE, add_transactions


@pytest.fixture(autouse=True)
def plain():
    i18n.set_language("sq")
    colors.configure(force_off=True)
    yield
    i18n.set_language("sq")


class Screen:
    """Answers input() from a queue and records what was on screen when.

    `asked` holds every prompt in order. `lines` interleaves what was printed
    with the prompts and the answers typed, the way the window shows them.
    """

    def __init__(self, capsys, answers):
        self.capsys = capsys
        self.queue = list(answers)
        self.asked = []
        self.lines = []
        self.saved_before = []

    def __call__(self, prompt=""):
        self.lines.extend(self.capsys.readouterr().out.split("\n")[:-1])
        self.asked.append(prompt)
        if not self.queue:
            raise AssertionError(f"asked for more than expected: {prompt!r}")
        answer = self.queue.pop(0)
        self.lines.append(f"{prompt}{answer}")
        return answer

    def finish(self):
        self.lines.extend(self.capsys.readouterr().out.split("\n")[:-1])
        return self

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def run(app, capsys, monkeypatch):
    """Run the add flow for a kind with the given answers; returns the Screen."""

    def go(kind, *answers, on=None):
        target = on or app
        capsys.readouterr()
        screen = Screen(capsys, answers)
        monkeypatch.setattr("builtins.input", screen)
        add_transactions(target, kind)
        return screen.finish()

    return go


def saved(app):
    return [
        (v.description, v.amount, v.occurred_on, v.category, v.subcategory, v.account)
        for v in app.transactions()
    ]


TODAY = current_date_str()

# One entry answered in full, as the first of several: description, amount,
# today, category, no subcategory.
SALARY = ("Paga e tetorit", "650", "po", "Paga", "")
# The second, keeping the carried date and category.
BONUS = ("Bonus", "80", "", "", "")


class TestHowMany:
    def test_it_is_the_first_question(self, run):
        screen = run(INCOME, "anulo")
        assert screen.asked == ["Sa te ardhura doni te shtoni? "]

    def test_expenses_ask_in_their_own_words(self, run):
        screen = run(EXPENSE, "anulo")
        assert screen.asked == ["Sa shpenzime doni te shtoni? "]

    def test_it_says_enter_is_allowed(self, run):
        screen = run(INCOME, "anulo")
        assert "  (Shtypni Enter nese nuk e dini sa)" in screen.lines

    def test_cancelling_it_leaves_the_task(self, run, app):
        screen = run(INCOME, "anulo")
        assert "Anuluar." in screen.lines
        assert app.transactions() == []

    @pytest.mark.parametrize("bad", ["0", "abc", "-1", "2.5", " ", "²", "1 2", "ANULO"])
    def test_anything_but_a_number_is_refused(self, run, bad):
        screen = run(INCOME, bad, "anulo")
        assert "Shkruani nje numer nga 1 deri ne 100, ose shtypni Enter." in screen.lines

    def test_more_than_the_most_is_refused(self, run):
        screen = run(INCOME, str(MOST_AT_ONCE + 1), "anulo")
        assert "Shkruani nje numer nga 1 deri ne 100, ose shtypni Enter." in screen.lines

    def test_the_most_is_accepted(self, run):
        screen = run(INCOME, str(MOST_AT_ONCE), "anulo", "anulo")
        assert "Te Ardhura 1 nga 100" in screen.lines

    def test_spaces_around_the_number_do_not_matter(self, run):
        screen = run(INCOME, " 2 ", "anulo", "anulo")
        assert "Te Ardhura 1 nga 2" in screen.lines


class TestOne:
    """One is exactly what adding was before: no heading, no list."""

    def test_it_is_saved_at_once(self, run, app):
        screen = run(INCOME, "1", *SALARY)
        assert saved(app) == [("Paga e tetorit", Decimal("650"), TODAY, "Paga", None, None)]
        assert screen.lines[-1] == "Te Ardhura eshte shtuar me sukses!"

    def test_there_is_no_heading_and_no_list(self, run):
        text = run(INCOME, "1", *SALARY).text
        assert "nga 1" not in text
        assert "qe do te shtohen" not in text
        assert "Komandat:" not in text

    def test_the_questions_are_the_ones_asked_before(self, run):
        screen = run(INCOME, "1", *SALARY)
        assert screen.asked[1:] == [
            "Vendosni pershkrimin: ",
            "Vendosni shumen: ",
            "Te perdoret data e tanishme? (po/jo): ",
            "Zgjidhni ose shkruani kategorine: ",
            "Zgjidhni ose shkruani nenkategorine: ",
        ]

    def test_a_blank_line_separates_it_from_the_question_of_how_many(self, run):
        lines = run(INCOME, "1", *SALARY).lines
        at = lines.index("Sa te ardhura doni te shtoni? 1")
        assert lines[at + 1] == ""
        assert lines[at + 2] == "Vendosni pershkrimin: Paga e tetorit"

    def test_cancelling_the_first_question_goes_back_to_how_many(self, run, app):
        screen = run(INCOME, "1", "anulo", "anulo")
        assert screen.asked == ["Sa te ardhura doni te shtoni? ", "Vendosni pershkrimin: "] + [
            "Sa te ardhura doni te shtoni? "
        ]
        assert app.transactions() == []

    def test_a_budget_warning_still_comes(self, run, app):
        app.set_budget("Ushqim", Decimal("100"))
        screen = run(EXPENSE, "1", "Dyqani", "120", "po", "Ushqim", "")
        assert any("tejkaluar" in line for line in screen.lines)


class TestSeveral:
    def test_each_is_headed_with_its_place(self, run):
        lines = run(INCOME, "2", *SALARY, *BONUS, "ruaj").lines
        first = lines.index("Te Ardhura 1 nga 2")
        second = lines.index("Te Ardhura 2 nga 2")
        assert first < second
        assert lines[first - 1] == ""
        assert lines[second - 1] == ""

    def test_the_list_comes_before_anything_is_saved(self, run, app, monkeypatch):
        counted = {}
        real = Screen.__call__

        def looking(self, prompt=""):
            if prompt == "Veprimi: ":
                counted["at the list"] = app.count()
            return real(self, prompt)

        monkeypatch.setattr(Screen, "__call__", looking)
        run(INCOME, "2", *SALARY, *BONUS, "ruaj")
        assert counted["at the list"] == 0
        assert app.count() == 2

    def test_saving_saves_them_all_and_says_how_many(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, "ruaj")
        assert [row[0] for row in saved(app)] == ["Paga e tetorit", "Bonus"]
        assert screen.lines[-1] == "2 te ardhura u shtuan me sukses!"

    def test_expenses_say_so_in_their_own_words(self, run, app):
        screen = run(
            EXPENSE,
            "2",
            *("Buke", "1.20", "po", "Ushqim", ""),
            *("Qumesht", "0.90", "", "", ""),
            "ruaj",
        )
        assert "Shpenzime 1 nga 2" in screen.lines
        assert "Shpenzimet qe do te shtohen:" in screen.lines
        assert screen.lines[-1] == "2 shpenzime u shtuan me sukses!"

    def test_the_list_is_the_transactions_table(self, run):
        lines = run(INCOME, "2", *SALARY, *BONUS, "ruaj").lines
        at = lines.index("Te ardhurat qe do te shtohen:")
        assert lines[at - 1] == ""
        assert lines[at + 2].split() == ["#", "Data", "Lloji", "Pershkrimi", "Kategoria", "Shuma"]
        assert lines[at + 4].startswith(f"1 {TODAY} Te Ardhura Paga e tetorit")
        assert lines[at + 5].startswith(f"2 {TODAY} Te Ardhura Bonus")

    def test_the_commands_are_listed_and_spaced_out(self, run):
        lines = run(INCOME, "2", *SALARY, *BONUS, "ruaj").lines
        at = lines.index("Komandat:")
        assert lines[at - 1] == ""
        assert lines[at + 1 : at + 5] == [
            "  ndrysho 2   ndrysho rreshtin 2",
            "  fshi 2      hiq rreshtin 2",
            "  ruaj        ruaj te gjitha",
            "  anulo       dil pa ruajtur asgje",
        ]
        assert lines[at + 5] == ""
        assert lines[at + 6] == "Veprimi: ruaj"

    def test_a_category_typed_for_the_first_time_is_created_on_saving(self, run, app):
        run(EXPENSE, "2", "Kafe", "1.50", "po", "Kafene", "", "Uje", "0.50", "", "", "", "ruaj")
        assert [c.name for c in app.categories(EXPENSE)] == ["Kafene"]
        assert [row[3] for row in saved(app)] == ["Kafene", "Kafene"]


class TestCarriedOver:
    """From the second entry on, what the one before used is offered."""

    def test_the_date_is_offered_and_today_is_not_asked(self, run, app):
        screen = run(INCOME, "2", "Paga", "650", "jo", "01-10-2026", "Paga", "", *BONUS, "ruaj")
        assert "Data [01-10-2026] (Enter = pa ndryshim): " in screen.asked
        assert screen.asked.count("Te perdoret data e tanishme? (po/jo): ") == 1
        assert [row[2] for row in saved(app)] == ["01-10-2026", "01-10-2026"]

    def test_the_category_is_offered(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, "ruaj")
        assert "Kategoria [Paga] (Enter = pa ndryshim): " in screen.asked
        assert [row[3] for row in saved(app)] == ["Paga", "Paga"]

    def test_the_description_and_amount_are_always_asked_afresh(self, run):
        screen = run(INCOME, "2", *SALARY, *BONUS, "ruaj")
        assert screen.asked.count("Vendosni pershkrimin: ") == 2
        assert screen.asked.count("Vendosni shumen: ") == 2

    def test_a_carried_value_can_be_replaced(self, run, app):
        run(INCOME, "2", *SALARY, "Dhurate", "50", "02-10-2026", "Dhurata", "", "ruaj")
        gift = [row for row in saved(app) if row[0] == "Dhurate"][0]
        assert gift[2:4] == ("02-10-2026", "Dhurata")

    def test_a_carried_category_can_be_cleared(self, run, app):
        run(INCOME, "2", *SALARY, "Dhurate", "50", "", "-", "ruaj")
        assert saved(app)[1][3] is None

    def test_the_subcategory_is_offered_under_the_same_category(self, run, app):
        screen = run(
            EXPENSE,
            "2",
            *("Buke", "1.20", "po", "Ushqim", "Dyqan"),
            *("Qumesht", "0.90", "", "", ""),
            "ruaj",
        )
        assert "Nenkategoria [Dyqan] (Enter = pa ndryshim, '-' = fshij): " in screen.asked
        assert [row[4] for row in saved(app)] == ["Dyqan", "Dyqan"]

    def test_the_subcategory_is_asked_afresh_under_another_category(self, run, app):
        screen = run(
            EXPENSE,
            "2",
            *("Buke", "1.20", "po", "Ushqim", "Dyqan"),
            *("Autobus", "0.40", "", "Transport", ""),
            "ruaj",
        )
        assert screen.asked.count("Zgjidhni ose shkruani nenkategorine: ") == 2
        assert saved(app)[1][3:5] == ("Transport", None)

    def test_the_account_is_offered(self, run, app, capsys):
        app.add_account("Banka", BANK, Decimal("0"))
        app.add_account("Kesh", CASH, Decimal("0"))
        screen = run(INCOME, "2", *SALARY, "2", *BONUS, "", "ruaj")
        assert "Llogaria [Kesh] (Enter = pa ndryshim): " in screen.asked
        assert [row[5] for row in saved(app)] == ["Kesh", "Kesh"]

    def test_no_account_before_means_the_question_as_usual(self, run, app):
        app.add_account("Banka", BANK, Decimal("0"))
        screen = run(INCOME, "2", *SALARY, "", *BONUS, "", "ruaj")
        assert screen.asked.count("Zgjidhni llogarine: ") == 2
        assert [row[5] for row in saved(app)] == [None, None]

    def test_a_rule_that_disagrees_is_still_suggested(self, run, app):
        """A carried category is only a default, not this entry's own."""
        app.add_category_rule("KAFE", "Kafene", EXPENSE)
        screen = run(
            EXPENSE,
            "2",
            *("Buke", "1.20", "po", "Ushqim", ""),
            *("Kafe", "1.50", "", "", ""),
            "ruaj",
        )
        assert "  Sugjerim nga rregullat: Kafene" in screen.lines
        # Suggested, not decided: Enter kept the carried category.
        assert saved(app)[1][3] == "Ushqim"

    def test_a_rule_that_agrees_says_nothing(self, run, app):
        app.add_category_rule("KAFE", "Kafene", EXPENSE)
        screen = run(
            EXPENSE,
            "2",
            *("Kafe", "1.50", "po", "Kafene", ""),
            *("Kafe e dyte", "1.50", "", "", ""),
            "ruaj",
        )
        assert screen.text.count("Sugjerim nga rregullat") == 1


class TestNotKnowingHowMany:
    def test_it_asks_after_each_whether_there_is_another(self, run, app):
        screen = run(INCOME, "", *SALARY, "po", *BONUS, "jo", "ruaj")
        assert screen.asked.count("Te shtoni edhe nje? (po/jo): ") == 2
        assert len(saved(app)) == 2

    def test_the_headings_have_no_total(self, run):
        lines = run(INCOME, "", *SALARY, "po", *BONUS, "jo", "ruaj").lines
        assert "Te Ardhura 1" in lines
        assert "Te Ardhura 2" in lines
        assert not any(" nga " in line for line in lines)

    def test_the_question_is_set_apart(self, run):
        lines = run(INCOME, "", *SALARY, "jo").lines
        at = lines.index("Te shtoni edhe nje? (po/jo): jo")
        assert lines[at - 1] == ""

    def test_stopping_after_one_saves_it_at_once(self, run, app):
        screen = run(INCOME, "", *SALARY, "jo")
        assert len(saved(app)) == 1
        assert "Komandat:" not in screen.text
        assert screen.lines[-1] == "Te Ardhura eshte shtuar me sukses!"

    @pytest.mark.parametrize("bad", ["PO", " po", "yes", "1"])
    def test_only_yes_or_no_is_taken(self, run, bad):
        screen = run(INCOME, "", *SALARY, bad, "jo")
        assert "Ju lutem shkruani vetem 'po' ose 'jo'." in screen.lines

    def test_cancelling_it_goes_back_to_the_last_question(self, run, app):
        screen = run(INCOME, "", *SALARY, "anulo", "Bonusi", "jo")
        assert screen.asked[-3:] == [
            "Te shtoni edhe nje? (po/jo): ",
            "Zgjidhni ose shkruani nenkategorine: ",
            "Te shtoni edhe nje? (po/jo): ",
        ]
        assert saved(app)[0][4] == "Bonusi"


class TestSteppingBack:
    """Cancelling steps back one question, across entries too."""

    def test_from_the_second_entry_to_the_last_question_of_the_first(self, run, app):
        screen = run(INCOME, "2", *SALARY, "anulo", "Shtese", *BONUS, "ruaj")
        assert screen.asked[6:8] == [
            "Vendosni pershkrimin: ",
            "Zgjidhni ose shkruani nenkategorine: ",
        ]
        assert saved(app)[0][4] == "Shtese"

    def test_the_heading_says_which_entry_it_is_back_in(self, run):
        lines = run(INCOME, "2", *SALARY, "anulo", "", *BONUS, "ruaj").lines
        assert lines.count("Te Ardhura 1 nga 2") == 2
        assert lines.count("Te Ardhura 2 nga 2") == 2

    def test_back_into_an_account_question(self, run, app):
        app.add_account("Banka", BANK, Decimal("0"))
        screen = run(INCOME, "2", *SALARY, "1", "anulo", "", *BONUS, "", "ruaj")
        # The first entry's account, again after stepping back, then the second's.
        assert screen.asked.count("Zgjidhni llogarine: ") == 3
        assert [row[5] for row in saved(app)] == [None, None]

    def test_back_into_the_question_of_another(self, run, app):
        screen = run(INCOME, "", *SALARY, "po", "anulo", "jo")
        assert screen.asked[-2:] == [
            "Vendosni pershkrimin: ",
            "Te shtoni edhe nje? (po/jo): ",
        ]
        assert len(saved(app)) == 1

    def test_all_the_way_back_to_how_many(self, run, app):
        screen = run(INCOME, "2", "anulo", "1", *SALARY)
        assert screen.asked[:3] == [
            "Sa te ardhura doni te shtoni? ",
            "Vendosni pershkrimin: ",
            "Sa te ardhura doni te shtoni? ",
        ]
        assert len(saved(app)) == 1

    def test_and_out(self, run, app):
        # The second entry's first question, the first entry's five, then how many.
        backing = ["anulo"] * 7
        screen = run(INCOME, "2", *SALARY, *backing)
        assert screen.lines[-1] == "Anuluar."
        assert app.transactions() == []

    def test_answers_already_given_are_kept(self, run, app):
        run(INCOME, "2", *SALARY, "anulo", "", *BONUS, "ruaj")
        assert saved(app) == [
            ("Paga e tetorit", Decimal("650"), TODAY, "Paga", None, None),
            ("Bonus", Decimal("80"), TODAY, "Paga", None, None),
        ]


class TestTheList:
    def test_cancelling_saves_nothing(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, "anulo")
        assert app.transactions() == []
        assert screen.lines[-1] == "Anuluar."

    def test_the_cancel_word_is_taken_exactly(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, " anulo ", "ANULO", "anulo")
        assert screen.text.count("Veprim i panjohur. Shkruani nje nga komandat me lart.") == 2

    def test_a_row_can_be_taken_out(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, "fshi 1", "ruaj")
        assert [row[0] for row in saved(app)] == ["Bonus"]
        # One left is said the way one always was.
        assert screen.lines[-1] == "Te Ardhura eshte shtuar me sukses!"

    def test_the_list_is_shown_again_without_it(self, run):
        lines = run(INCOME, "2", *SALARY, *BONUS, "fshi 1", "ruaj").lines
        last = len(lines) - 1 - lines[::-1].index("Te ardhurat qe do te shtohen:")
        assert lines[last + 4].startswith(f"1 {TODAY} Te Ardhura Bonus")

    def test_several_rows_can_be_taken_out_at_once(self, run, app):
        three = (*SALARY, *BONUS, "Dhurate", "20", "", "", "")
        run(INCOME, "3", *three, "fshi 1, 3", "ruaj")
        assert [row[0] for row in saved(app)] == ["Bonus"]

    def test_taking_them_all_out_saves_nothing(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, "fshi 1-2")
        assert app.transactions() == []
        assert screen.lines[-1] == "Nuk mbeti asgje per te ruajtur."

    @pytest.mark.parametrize("bad", ["fshi 3", "fshi 0", "fshi x", "fshi 1-3", "ndrysho 3"])
    def test_a_row_that_is_not_there_is_refused(self, run, app, bad):
        screen = run(INCOME, "2", *SALARY, *BONUS, bad, "ruaj")
        assert "Nuk ka rresht me ate numer. Rreshtat jane nga 1 deri ne 2." in screen.lines
        assert len(saved(app)) == 2

    @pytest.mark.parametrize("bad", ["", "2", "ndrysho", "fshi", "Ruaj", "ruaj tani", "x"])
    def test_anything_else_is_refused(self, run, app, bad):
        screen = run(INCOME, "2", *SALARY, *BONUS, bad, "ruaj")
        assert "Veprim i panjohur. Shkruani nje nga komandat me lart." in screen.lines
        assert len(saved(app)) == 2

    def test_a_row_can_be_changed(self, run, app):
        # description, amount, date, category, subcategory - only the amount changes.
        run(INCOME, "2", *SALARY, *BONUS, "ndrysho 2", "", "95", "", "", "", "ruaj")
        assert saved(app)[1][:2] == ("Bonus", Decimal("95"))

    def test_changing_a_row_offers_what_it_holds(self, run):
        screen = run(INCOME, "2", *SALARY, *BONUS, "ndrysho 2", "", "", "", "", "", "ruaj")
        assert "Pershkrimi [Bonus]: " in screen.asked
        assert "Shuma [80.00]: " in screen.asked
        assert f"Data [{TODAY}] (Enter = pa ndryshim): " in screen.asked
        assert "Duke ndryshuar rreshtin 2" in screen.lines

    def test_cancelling_a_change_leaves_the_row_as_it_was(self, run, app):
        screen = run(INCOME, "2", *SALARY, *BONUS, "ndrysho 2", "anulo", "ruaj")
        assert saved(app)[1][:2] == ("Bonus", Decimal("80"))
        assert "Anuluar." in screen.lines

    def test_a_change_steps_back_too(self, run, app):
        run(INCOME, "2", *SALARY, *BONUS, "ndrysho 1", "", "anulo", "Paga", "", "", "", "", "ruaj")
        assert saved(app)[0][0] == "Paga"

    def test_the_english_words_work_too(self, run, app):
        """As at the import preview, whichever language the screen is in."""
        run(INCOME, "2", *SALARY, *BONUS, "edit 2", "", "95", "", "", "", "delete 1", "save")
        assert saved(app) == [("Bonus", Decimal("95"), TODAY, "Paga", None, None)]


class TestSavingTogether:
    def test_a_failure_saves_none_of_them(self, run, app, monkeypatch):
        real = type(app.db).add_transaction
        calls = {"n": 0}

        def flaky(self, transaction, connection=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return real(self, transaction, connection=connection)

        monkeypatch.setattr(type(app.db), "add_transaction", flaky)
        with pytest.raises(RuntimeError):
            run(EXPENSE, "2", "Kafe", "1.50", "po", "Kafene", "", "Uje", "0.50", "", "", "", "ruaj")
        monkeypatch.undo()
        assert app.transactions() == []
        assert app.categories(EXPENSE) == []

    def test_a_budget_is_warned_about_once(self, run, app):
        app.set_budget("Ushqim", Decimal("10"))
        screen = run(
            EXPENSE,
            "2",
            *("Buke", "8", "po", "Ushqim", ""),
            *("Qumesht", "6", "", "", ""),
            "ruaj",
        )
        assert sum("tejkaluar" in line for line in screen.lines) == 1

    def test_every_row_is_in_the_change_history(self, run, app):
        run(INCOME, "2", *SALARY, *BONUS, "ruaj")
        assert len(app.history(entity="transactions")) == 2


class TestTheMenu:
    @pytest.mark.parametrize(
        ("option", "question"),
        [(1, "Sa te ardhura doni te shtoni? "), (2, "Sa shpenzime doni te shtoni? ")],
    )
    def test_options_one_and_two_ask_how_many(self, app, monkeypatch, option, question):
        asked = []

        def fake_input(prompt=""):
            asked.append(prompt)
            return "anulo"

        monkeypatch.setattr("builtins.input", fake_input)
        MENU_ITEMS[option - 1][1](app)
        assert asked == [question]

    def test_the_menu_entries_keep_their_names(self):
        assert [key for key, _ in MENU_ITEMS[:2]] == ["menu_add_income", "menu_add_expense"]


class TestInEnglish:
    @pytest.fixture(autouse=True)
    def english(self):
        i18n.set_language("en")
        yield
        i18n.set_language("sq")

    def test_the_whole_flow_reads_in_english(self, run, app):
        screen = run(
            EXPENSE,
            "2",
            *("Bread", "1.20", "yes", "Food", ""),
            *("Milk", "0.90", "", "", ""),
            "save",
        )
        assert screen.asked[0] == "How many expenses do you want to add? "
        assert "  (Press Enter if you don't know how many)" in screen.lines
        assert "Expenses 1 of 2" in screen.lines
        assert "Expenses to be added:" in screen.lines
        assert "  delete 2    remove row 2" in screen.lines
        assert screen.lines[-1] == "2 expenses added successfully!"

    def test_income_has_its_own_words(self, run):
        screen = run(INCOME, "", *("Salary", "650", "yes", "Pay", ""), "no")
        assert screen.asked[0] == "How many income entries do you want to add? "
        assert "Add another one? (yes/no): " in screen.asked
        assert "Income 1" in screen.lines

    def test_the_albanian_words_work_at_the_list_too(self, run, app):
        run(INCOME, "2", *("Salary", "650", "yes", "Pay", ""), *("Bonus", "80", "", "", ""), "ruaj")
        assert app.count() == 2

    def test_cancelling_takes_the_english_word(self, run, app):
        screen = run(INCOME, "cancel")
        assert screen.lines[-1] == "Cancelled."


class TestTheCommandGuide:
    """The descriptions line up, in both languages, as at the import preview."""

    KEYS = ("review_cmd_edit", "review_cmd_remove", "review_cmd_save", "review_cmd_cancel")

    @staticmethod
    def description_column(line):
        """Where the description starts: after the padding that follows the
        command, which is the first run of two or more spaces after it."""
        import re

        return re.search(r"\S {2,}", line).end()

    @pytest.mark.parametrize("language", ["sq", "en"])
    def test_the_descriptions_line_up(self, language):
        from personal_finance.i18n import MESSAGES

        lines = [MESSAGES[language][key] for key in self.KEYS]
        assert len({self.description_column(line) for line in lines}) == 1, lines

    @pytest.mark.parametrize("language", ["sq", "en"])
    def test_they_line_up_with_nothing_else_in_the_line(self, language):
        """Indented like the row guide, two spaces, so the block reads as one."""
        from personal_finance.i18n import MESSAGES

        for key in self.KEYS:
            line = MESSAGES[language][key]
            assert line.startswith("  ") and not line.startswith("   "), line

    @pytest.mark.parametrize("language", ["sq", "en"])
    def test_each_command_shown_is_one_that_works(self, language):
        from personal_finance.i18n import MESSAGES
        from personal_finance.ui import EDIT_WORDS, REMOVE_WORDS, SAVE_WORDS

        words = [MESSAGES[language][key].split()[0] for key in self.KEYS]
        assert words[0] in EDIT_WORDS
        assert words[1] in REMOVE_WORDS
        assert words[2] in SAVE_WORDS
        i18n.set_language(language)
        try:
            assert words[3] in i18n.cancels()
        finally:
            i18n.set_language("sq")


class TestTheAppLayer:
    def test_add_transactions_returns_them_with_ids(self, app):
        entries = [
            {"description": "A", "amount": Decimal("1"), "occurred_on": "01-10-2026"},
            {"description": "B", "amount": Decimal("2"), "occurred_on": "02-10-2026"},
        ]
        created = app.add_transactions(INCOME, entries)
        assert [t.id for t in created] == [v.id for v in app.transactions()]
        assert all(t.id for t in created)

    def test_nothing_given_writes_nothing(self, app):
        assert app.add_transactions(INCOME, []) == []
        assert app.count() == 0

    def test_budget_warnings_are_given_once_per_category_and_month(self, app):
        app.set_budget("Ushqim", Decimal("10"))
        created = app.add_transactions(
            EXPENSE,
            [
                {
                    "description": "A",
                    "amount": Decimal("8"),
                    "occurred_on": "01-10-2026",
                    "category": "Ushqim",
                },
                {
                    "description": "B",
                    "amount": Decimal("6"),
                    "occurred_on": "02-10-2026",
                    "category": "Ushqim",
                },
                {
                    "description": "C",
                    "amount": Decimal("12"),
                    "occurred_on": "01-09-2026",
                    "category": "Ushqim",
                },
            ],
        )
        assert len(app.budget_warnings(created)) == 2

    def test_a_single_add_leaves_no_category_behind_when_it_fails(self, app, monkeypatch):
        def broken(self, transaction, connection=None):
            raise RuntimeError("disk full")

        monkeypatch.setattr(type(app.db), "add_transaction", broken)
        with pytest.raises(RuntimeError):
            app.add_transaction(EXPENSE, "Kafe", Decimal("1.50"), "01-10-2026", "Kafene")
        monkeypatch.undo()
        assert app.categories(EXPENSE) == []
