"""Tests for subcategories, suggestion ordering, and the delete message.

The ordering tests exist because a user hit this in real use: categories they
typed themselves were appended after the catch-all, so the suggestion list
ended on a specific category and "Te tjera" sat in the middle.
"""

from decimal import Decimal

import pytest

from personal_finance import colors, i18n
from personal_finance.collation import sort_names
from personal_finance.config import (
    EXPENSE,
    INCOME,
    OTHER_CATEGORY,
    SUGGESTED_CATEGORIES,
    SUGGESTED_SUBCATEGORIES,
)
from personal_finance.display import category_path, subcategory_display
from personal_finance.models import RecurringRule, Transaction
from personal_finance.reports import (
    has_subcategories,
    known_categories,
    known_subcategories,
    ordered_options,
    search,
    totals_by_subcategory,
)

from .conftest import make_transaction


def sub_transaction(category, subcategory, amount="10.00", trans_type=EXPENSE):
    return Transaction(
        lloji=trans_type,
        pershkrimi="Test",
        shuma=Decimal(amount),
        data="15-06-2026",
        kategoria=category,
        nenkategoria=subcategory,
    )


class TestOrderedOptions:
    def test_moves_the_catch_all_to_the_end(self):
        assert ordered_options(["A", OTHER_CATEGORY, "B"]) == ["A", "B", OTHER_CATEGORY]

    def test_leaves_a_list_without_it_alone(self):
        assert ordered_options(["A", "B"]) == ["A", "B"]

    def test_empty_list(self):
        assert ordered_options([]) == []

    def test_sorts_alphabetically(self):
        assert ordered_options(["C", "A", OTHER_CATEGORY, "B"]) == [
            "A",
            "B",
            "C",
            OTHER_CATEGORY,
        ]

    def test_sorting_is_case_insensitive(self):
        assert ordered_options(["banana", "Apple", "cherry"]) == [
            "Apple",
            "banana",
            "cherry",
        ]

    def test_albanian_letters_sort_in_alphabet_order(self):
        """Sorting on raw code points would push every accented word past Z."""
        assert ordered_options(["Zarf", "Ëmbëlsira", "Çaji", "Abonim"]) == [
            "Abonim",
            "Çaji",
            "Ëmbëlsira",
            "Zarf",
        ]

    def test_digraphs_follow_their_base_letter(self):
        """Every S word comes before every Sh word, as in Albanian."""
        assert ordered_options(["Shendetesi", "Sende", "Sy"]) == [
            "Sende",
            "Sy",
            "Shendetesi",
        ]

    def test_catch_all_stays_last_even_though_it_would_sort_earlier(self):
        # "Te tjera" would fall between S and U alphabetically.
        result = ordered_options(["Ushqim", OTHER_CATEGORY, "Shendetesi"])
        assert result == ["Shendetesi", "Ushqim", OTHER_CATEGORY]

    def test_duplicate_catch_all_appears_once(self):
        result = ordered_options(["A", OTHER_CATEGORY, OTHER_CATEGORY])
        assert result == ["A", OTHER_CATEGORY]


class TestCategoryOrdering:
    def test_catch_all_is_last_with_no_custom_categories(self):
        options = known_categories([], EXPENSE, SUGGESTED_CATEGORIES)
        assert options[-1] == OTHER_CATEGORY

    def test_catch_all_stays_last_when_a_custom_category_exists(self):
        """The reported bug: a typed category used to land after the catch-all."""
        transactions = [make_transaction(EXPENSE, category="Kafene")]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        assert options[-1] == OTHER_CATEGORY
        assert "Kafene" in options
        assert options.index("Kafene") < options.index(OTHER_CATEGORY)

    def test_catch_all_stays_last_with_several_custom_categories(self):
        transactions = [
            make_transaction(EXPENSE, category="Kafene"),
            make_transaction(EXPENSE, category="Femijet"),
            make_transaction(EXPENSE, category="Kafshet"),
        ]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        assert options[-1] == OTHER_CATEGORY
        for name in ("Kafene", "Femijet", "Kafshet"):
            assert options.index(name) < options.index(OTHER_CATEGORY)

    def test_applies_to_income_too(self):
        transactions = [make_transaction(INCOME, category="Qira e marrur")]
        options = known_categories(transactions, INCOME, SUGGESTED_CATEGORIES)
        assert options[-1] == OTHER_CATEGORY

    def test_no_duplicates(self):
        transactions = [
            make_transaction(EXPENSE, category="Kafene"),
            make_transaction(EXPENSE, category="Kafene"),
        ]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        assert options.count("Kafene") == 1

    def test_a_user_typed_catch_all_does_not_duplicate_it(self):
        transactions = [make_transaction(EXPENSE, category=OTHER_CATEGORY)]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        assert options.count(OTHER_CATEGORY) == 1
        assert options[-1] == OTHER_CATEGORY


class TestSubcategoryOrdering:
    def test_catch_all_is_last(self):
        options = known_subcategories([], EXPENSE, "Ushqim", SUGGESTED_SUBCATEGORIES)
        assert options[-1] == OTHER_CATEGORY

    def test_custom_subcategory_comes_before_the_catch_all(self):
        transactions = [sub_transaction("Ushqim", "Pazar")]
        options = known_subcategories(transactions, EXPENSE, "Ushqim", SUGGESTED_SUBCATEGORIES)
        assert options.index("Pazar") < options.index(OTHER_CATEGORY)

    def test_only_subcategories_of_the_requested_category(self):
        transactions = [
            sub_transaction("Ushqim", "Pazar"),
            sub_transaction("Transport", "Autobus"),
        ]
        options = known_subcategories(transactions, EXPENSE, "Ushqim", SUGGESTED_SUBCATEGORIES)
        assert "Pazar" in options
        assert "Autobus" not in options

    def test_unknown_category_still_learns_typed_subcategories(self):
        transactions = [sub_transaction("Kafene", "Espresso")]
        options = known_subcategories(transactions, EXPENSE, "Kafene", SUGGESTED_SUBCATEGORIES)
        assert options == ["Espresso"]


class TestTransactionSubcategory:
    def test_defaults_to_empty(self):
        assert make_transaction().nenkategoria == ""

    def test_round_trip_through_row(self):
        original = sub_transaction("Ushqim", "Dyqan")
        assert Transaction.from_row(original.to_row()) == original

    def test_row_without_the_column_loads_as_empty(self):
        """Files written before subcategories existed."""
        row = {
            "lloji": EXPENSE,
            "pershkrimi": "Qera",
            "shuma": "300",
            "data": "01-06-2026",
            "kategoria": "Qera",
        }
        assert Transaction.from_row(row).nenkategoria == ""

    def test_blank_subcategory_column_loads_as_empty(self):
        row = {
            "lloji": EXPENSE,
            "pershkrimi": "Qera",
            "shuma": "300",
            "data": "01-06-2026",
            "kategoria": "Qera",
            "nenkategoria": "   ",
        }
        assert Transaction.from_row(row).nenkategoria == ""

    def test_recurring_rule_carries_subcategory_to_generated_transactions(self):
        import datetime

        rule = RecurringRule(
            lloji=EXPENSE,
            pershkrimi="Internet",
            shuma=Decimal("30"),
            kategoria="Fatura",
            nenkategoria="Internet",
            frekuenca="mujore",
            data_fillimit="01-01-2026",
        )
        created = rule.to_transaction(datetime.date(2026, 6, 1))
        assert created.nenkategoria == "Internet"

    def test_recurring_rule_row_round_trip(self):
        rule = RecurringRule(
            lloji=EXPENSE,
            pershkrimi="Internet",
            shuma=Decimal("30.00"),
            kategoria="Fatura",
            nenkategoria="Internet",
            frekuenca="mujore",
            data_fillimit="01-01-2026",
        )
        assert RecurringRule.from_row(rule.to_row()) == rule


class TestTotalsBySubcategory:
    def test_groups_and_sums(self):
        transactions = [
            sub_transaction("Ushqim", "Dyqan", "30"),
            sub_transaction("Ushqim", "Dyqan", "20"),
            sub_transaction("Ushqim", "Restorant", "40"),
        ]
        assert totals_by_subcategory(transactions, EXPENSE, "Ushqim") == [
            ("Restorant", Decimal("40")),
            ("Dyqan", Decimal("50")),
        ] or totals_by_subcategory(transactions, EXPENSE, "Ushqim") == [
            ("Dyqan", Decimal("50")),
            ("Restorant", Decimal("40")),
        ]

    def test_largest_named_subcategory_first(self):
        transactions = [
            sub_transaction("Ushqim", "Dyqan", "50"),
            sub_transaction("Ushqim", "Restorant", "40"),
        ]
        rows = totals_by_subcategory(transactions, EXPENSE, "Ushqim")
        assert rows[0] == ("Dyqan", Decimal("50"))

    def test_unsubcategorised_amounts_sort_last(self):
        transactions = [
            sub_transaction("Ushqim", "", "1000"),
            sub_transaction("Ushqim", "Dyqan", "5"),
        ]
        rows = totals_by_subcategory(transactions, EXPENSE, "Ushqim")
        assert rows[-1][0] == ""

    def test_ignores_other_categories(self):
        transactions = [
            sub_transaction("Ushqim", "Dyqan", "50"),
            sub_transaction("Transport", "Taksi", "20"),
        ]
        rows = totals_by_subcategory(transactions, EXPENSE, "Ushqim")
        assert len(rows) == 1


class TestHasSubcategories:
    def test_false_when_none_used(self):
        assert not has_subcategories([make_transaction(), make_transaction()])

    def test_true_when_any_used(self):
        assert has_subcategories([make_transaction(), sub_transaction("Ushqim", "Dyqan")])

    def test_false_for_empty(self):
        assert not has_subcategories([])


class TestSearchIncludesSubcategory:
    def test_matches_a_subcategory(self):
        transactions = [sub_transaction("Ushqim", "Restorant")]
        assert len(search(transactions, "Restorant")) == 1

    def test_is_case_insensitive(self):
        transactions = [sub_transaction("Ushqim", "Restorant")]
        assert len(search(transactions, "restorant")) == 1


class TestDisplayHelpers:
    def test_subcategory_display_falls_back_to_a_dash(self):
        assert subcategory_display("") == "-"
        assert subcategory_display("Dyqan") == "Dyqan"

    def test_category_path_with_subcategory(self):
        assert category_path(sub_transaction("Ushqim", "Dyqan")) == "Ushqim / Dyqan"

    def test_category_path_without_subcategory(self):
        assert category_path(make_transaction(category="Qera")) == "Qera"


class TestDeleteMessage:
    """The delete confirmation was missing the category entirely."""

    @pytest.fixture(autouse=True)
    def plain(self):
        i18n.set_language("sq")
        colors.configure(force_off=True)

    def test_includes_the_category(self, app, capsys, monkeypatch):
        from personal_finance.ui import delete_transaction

        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-06-2026", "Qera")
        capsys.readouterr()

        monkeypatch.setattr("builtins.input", lambda _="": "1")
        delete_transaction(app)
        output = capsys.readouterr().out
        assert "U fshi:" in output
        assert "Qera" in output

    def test_includes_the_subcategory_when_there_is_one(self, app, capsys, monkeypatch):
        from personal_finance.ui import delete_transaction

        app.add_transaction(EXPENSE, "Buke", Decimal("1.20"), "01-06-2026", "Ushqim", "Dyqan")
        capsys.readouterr()

        monkeypatch.setattr("builtins.input", lambda _="": "1")
        delete_transaction(app)
        assert "Ushqim / Dyqan" in capsys.readouterr().out

    def test_english_message_also_has_the_category(self, app, capsys, monkeypatch):
        from personal_finance.ui import delete_transaction

        app.add_transaction(EXPENSE, "Rent", Decimal("300"), "01-06-2026", "Qera")
        capsys.readouterr()

        i18n.set_language("en")
        monkeypatch.setattr("builtins.input", lambda _="": "1")
        delete_transaction(app)
        output = capsys.readouterr().out
        i18n.set_language("sq")
        assert "Deleted:" in output
        assert "Qera" in output


class TestBreakdownAlignment:
    """Amount columns must not depend on which names a category happens to use.

    Reported from real use: an income block whose only subcategory name was
    short put its amount one column LEFT of the category amounts, while an
    expense block with a longer name put it two columns right. Both blocks were
    produced by the same code - only the name lengths differed.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        i18n.set_language("sq")
        colors.configure(force_off=True)

    @staticmethod
    def columns(transactions, trans_type, capsys):
        from personal_finance.display import print_category_breakdown

        print_category_breakdown(transactions, trans_type)
        lines = [line for line in capsys.readouterr().out.split("\n") if "€" in line]
        category_ends = {len(line.rstrip()) for line in lines if not line.startswith("      ")}
        sub_ends = {len(line.rstrip()) for line in lines if line.startswith("      ")}
        return category_ends, sub_ends

    def test_reported_income_case_now_aligns(self, capsys):
        transactions = [
            sub_transaction("Investime", "Shitje", "135.00", INCOME),
            sub_transaction("Rimbursim", "", "20.00", INCOME),
        ]
        categories, subs = self.columns(transactions, INCOME, capsys)
        assert len(categories) == 1
        assert len(subs) == 1
        # The subcategory amount used to sit one column to the LEFT.
        assert min(subs) > min(categories)

    def test_subcategory_amounts_sit_exactly_two_columns_right(self, capsys):
        transactions = [
            sub_transaction("Ushqim", "Restorant", "20.00"),
            sub_transaction("Ushqim", "Delivery", "5.00"),
            sub_transaction("Rimbursim", "", "100.00"),
        ]
        categories, subs = self.columns(transactions, EXPENSE, capsys)
        assert min(subs) - min(categories) == 2

    def test_short_subcategory_name_does_not_pull_the_column_left(self, capsys):
        """A one-word subcategory used to drag its amount left of the category."""
        transactions = [
            sub_transaction("Transport", "Bus", "5.00"),
            sub_transaction("Fatura", "", "40.00"),
        ]
        categories, subs = self.columns(transactions, EXPENSE, capsys)
        assert min(subs) - min(categories) == 2

    def test_long_subcategory_name_does_not_fling_the_column_right(self, capsys):
        """A long name widens both columns together, keeping the offset at two."""
        transactions = [
            sub_transaction("Ushqim", "Supermarketi i madh", "9.00"),
            sub_transaction("Qera", "", "300.00"),
        ]
        categories, subs = self.columns(transactions, EXPENSE, capsys)
        assert min(subs) - min(categories) == 2

    def test_all_categories_share_one_column(self, capsys):
        transactions = [
            sub_transaction("Ushqim", "Dyqan", "5.00"),
            sub_transaction("Transport", "Taksi", "12.00"),
            sub_transaction("Argetim", "", "40.00"),
        ]
        categories, _ = self.columns(transactions, EXPENSE, capsys)
        assert len(categories) == 1

    def test_all_subcategories_share_one_column_across_categories(self, capsys):
        """Different categories' subcategories must land in the same column."""
        transactions = [
            sub_transaction("Ushqim", "Restorant", "20.00"),
            sub_transaction("Transport", "Bus", "3.00"),
        ]
        _, subs = self.columns(transactions, EXPENSE, capsys)
        assert len(subs) == 1

    def test_large_amounts_do_not_break_alignment(self, capsys):
        transactions = [
            sub_transaction("Paga", "Baze", "1234567.89", INCOME),
            sub_transaction("Bonus", "", "12.00", INCOME),
        ]
        categories, subs = self.columns(transactions, INCOME, capsys)
        assert len(categories) == 1
        assert len(subs) == 1
        assert min(subs) - min(categories) == 2

    def test_block_without_subcategories_still_aligns(self, capsys):
        transactions = [
            make_transaction(EXPENSE, category="Qera", amount="300.00"),
            make_transaction(EXPENSE, category="Fatura", amount="40.00"),
        ]
        categories, subs = self.columns(transactions, EXPENSE, capsys)
        assert len(categories) == 1
        assert subs == set()


class TestSuggestionListOrdering:
    """Suggestion lists are alphabetical, with the catch-all pinned last.

    Requested from real use: a category the user typed was appended to the end
    of the list, so the order depended on when it was first used rather than on
    anything the reader could predict.
    """

    def test_builtin_categories_are_alphabetical(self):
        options = known_categories([], EXPENSE, SUGGESTED_CATEGORIES)
        assert options[:-1] == sort_names(options[:-1])
        assert options[-1] == OTHER_CATEGORY

    def test_custom_category_takes_its_alphabetical_place(self):
        # "Abonim" must come first, not last, even though it was added later.
        transactions = [make_transaction(EXPENSE, category="Abonim")]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        assert options[0] == "Abonim"
        assert options[-1] == OTHER_CATEGORY

    def test_several_custom_categories_interleave_correctly(self):
        transactions = [
            make_transaction(EXPENSE, category="Kafene"),
            make_transaction(EXPENSE, category="Abonim"),
            make_transaction(EXPENSE, category="Zarf"),
        ]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        assert options[0] == "Abonim"
        assert options[-2] == "Zarf"
        assert options[-1] == OTHER_CATEGORY
        assert options.index("Kafene") < options.index("Qera")

    def test_income_categories_are_alphabetical_too(self):
        options = known_categories([], INCOME, SUGGESTED_CATEGORIES)
        assert options[:-1] == sort_names(options[:-1])
        assert options[-1] == OTHER_CATEGORY

    def test_albanian_category_sorts_under_its_base_letter(self):
        transactions = [make_transaction(EXPENSE, category="Ëmbëlsira")]
        options = known_categories(transactions, EXPENSE, SUGGESTED_CATEGORIES)
        # Between Argetim and Fatura, not shoved past Veshje.
        assert options.index("Argetim") < options.index("Ëmbëlsira")
        assert options.index("Ëmbëlsira") < options.index("Fatura")

    def test_builtin_subcategories_are_alphabetical(self):
        options = known_subcategories([], EXPENSE, "Ushqim", SUGGESTED_SUBCATEGORIES)
        assert options[:-1] == sort_names(options[:-1])
        assert options[-1] == OTHER_CATEGORY

    def test_custom_subcategory_takes_its_alphabetical_place(self):
        transactions = [sub_transaction("Ushqim", "Delivery")]
        options = known_subcategories(transactions, EXPENSE, "Ushqim", SUGGESTED_SUBCATEGORIES)
        assert options[0] == "Delivery"
        assert options[-1] == OTHER_CATEGORY

    def test_subcategories_of_an_unlisted_category_are_alphabetical(self):
        transactions = [
            sub_transaction("Kafene", "Espresso"),
            sub_transaction("Kafene", "Americano"),
        ]
        options = known_subcategories(transactions, EXPENSE, "Kafene", SUGGESTED_SUBCATEGORIES)
        assert options == ["Americano", "Espresso"]

    def test_ordering_is_stable_regardless_of_insertion_order(self):
        """Two users who add the same categories in different orders see the same list."""
        first = [
            make_transaction(EXPENSE, category="Zarf"),
            make_transaction(EXPENSE, category="Abonim"),
        ]
        second = [
            make_transaction(EXPENSE, category="Abonim"),
            make_transaction(EXPENSE, category="Zarf"),
        ]
        assert known_categories(first, EXPENSE, SUGGESTED_CATEGORIES) == known_categories(
            second, EXPENSE, SUGGESTED_CATEGORIES
        )
