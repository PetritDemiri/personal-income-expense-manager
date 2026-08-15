"""Tests for Albanian collation.

The alphabet has 36 letters, nine of them digraphs. Sorting by Unicode code
point gets two things wrong: accented letters land past Z, and each digraph is
treated as two separate characters, which interleaves (for example) the S and
Sh words instead of keeping every S word ahead of every Sh word.
"""

import pytest

from personal_finance.collation import (
    ALPHABET,
    DIGRAPHS,
    sort_key,
    sort_names,
    tokenize,
)


class TestAlphabet:
    def test_has_thirty_six_letters(self):
        assert len(ALPHABET) == 36

    def test_has_nine_digraphs(self):
        assert len(DIGRAPHS) == 9

    def test_the_nine_digraphs_are_the_expected_ones(self):
        assert DIGRAPHS == {"dh", "gj", "ll", "nj", "rr", "sh", "th", "xh", "zh"}

    def test_no_duplicate_letters(self):
        assert len(set(ALPHABET)) == len(ALPHABET)

    def test_every_digraph_directly_follows_its_base_letter(self):
        for digraph in DIGRAPHS:
            base = digraph[0]
            assert ALPHABET.index(digraph) == ALPHABET.index(base) + 1, digraph


class TestTokenize:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("shi", ["sh", "i"]),
            ("dhoma", ["dh", "o", "m", "a"]),
            ("gjuha", ["gj", "u", "h", "a"]),
            ("llamba", ["ll", "a", "m", "b", "a"]),
            ("njeri", ["nj", "e", "r", "i"]),
            ("rruga", ["rr", "u", "g", "a"]),
            ("thika", ["th", "i", "k", "a"]),
            ("xhaketa", ["xh", "a", "k", "e", "t", "a"]),
            ("zhurma", ["zh", "u", "r", "m", "a"]),
        ],
    )
    def test_each_digraph_is_one_token(self, text, expected):
        assert tokenize(text) == expected

    def test_single_letters_stay_single(self):
        assert tokenize("mal") == ["m", "a", "l"]

    def test_digraph_inside_a_word(self):
        assert tokenize("mall") == ["m", "a", "ll"]

    def test_three_repeated_letters_take_the_digraph_first(self):
        assert tokenize("alll") == ["a", "ll", "l"]

    def test_is_case_insensitive(self):
        assert tokenize("SHI") == tokenize("shi") == ["sh", "i"]
        assert tokenize("Sh") == ["sh"]

    def test_accented_letters_are_single_tokens(self):
        assert tokenize("çaj") == ["ç", "a", "j"]
        assert tokenize("ëmbël") == ["ë", "m", "b", "ë", "l"]

    def test_decomposed_accents_are_recognised(self):
        """e + combining diaeresis must tokenise the same as a composed ë."""
        composed = "\u00eb"
        decomposed = "e\u0308"
        assert tokenize(composed) == tokenize(decomposed) == ["ë"]

    def test_spaces_and_punctuation_are_kept_as_tokens(self):
        assert tokenize("a-b") == ["a", "-", "b"]


class TestDigraphOrdering:
    """The whole point: every base-letter word precedes every digraph word."""

    @pytest.mark.parametrize(
        "base_word,digraph_word",
        [
            ("Duke", "Dhoma"),
            ("Guri", "Gjuha"),
            ("Luli", "Llamba"),
            ("Nuse", "Njeri"),
            ("Ruaj", "Rruga"),
            ("Sende", "Shendetesi"),
            ("Tuli", "Thika"),
            ("Xixa", "Xhaketa"),
            ("Zogu", "Zhurma"),
        ],
    )
    def test_base_letter_sorts_before_its_digraph(self, base_word, digraph_word):
        assert sort_names([digraph_word, base_word]) == [base_word, digraph_word]

    def test_even_a_late_base_letter_word_precedes_the_digraph(self):
        """ "Sy" beats "Shi" because S as a letter comes before Sh."""
        assert sort_names(["Shi", "Sy"]) == ["Sy", "Shi"]

    def test_all_s_words_come_before_all_sh_words(self):
        names = ["Shtepi", "Sende", "Shi", "Sy", "Sa"]
        assert sort_names(names) == ["Sa", "Sende", "Sy", "Shi", "Shtepi"]

    def test_naive_sorting_would_get_this_wrong(self):
        """Guards the point of the module: Python's default disagrees."""
        names = ["Shi", "Sy"]
        assert sorted(names) != sort_names(names)


class TestAccentedLetters:
    def test_c_cedilla_follows_c(self):
        assert sort_names(["Çaji", "Cak"]) == ["Cak", "Çaji"]

    def test_e_diaeresis_follows_e(self):
        assert sort_names(["Ëmbëlsira", "Etje"]) == ["Etje", "Ëmbëlsira"]

    def test_accented_letters_do_not_land_past_z(self):
        assert sort_names(["Zarf", "Ëmbëlsira"]) == ["Ëmbëlsira", "Zarf"]

    def test_c_cedilla_precedes_d(self):
        assert sort_names(["Duke", "Çaji"]) == ["Çaji", "Duke"]

    def test_e_diaeresis_precedes_f(self):
        assert sort_names(["Fatura", "Ëmbëlsira"]) == ["Ëmbëlsira", "Fatura"]


class TestFullAlphabetOrder:
    def test_one_word_per_letter_sorts_into_alphabet_order(self):
        # A word starting with each letter, deliberately shuffled.
        words = [letter + "x" for letter in ALPHABET]
        shuffled = list(reversed(words))
        assert sort_names(shuffled) == words

    def test_sorting_is_idempotent(self):
        names = ["Shi", "Çaji", "Zhurma", "Abonim", "Ëmbëlsira"]
        once = sort_names(names)
        assert sort_names(once) == once


class TestNonAlbanianInput:
    def test_w_sits_between_v_and_x(self):
        assert sort_names(["Xixa", "Wifi", "Veshje"]) == ["Veshje", "Wifi", "Xixa"]

    def test_english_names_sort_normally(self):
        names = ["Delivery", "Books", "Alcohol", "Coffee"]
        assert sort_names(names) == ["Alcohol", "Books", "Coffee", "Delivery"]

    def test_digits_sort_before_letters(self):
        assert sort_names(["Abonim", "2024"]) == ["2024", "Abonim"]

    def test_numbers_sort_numerically_within_a_run(self):
        assert sort_names(["9x", "10x"])[0] == "9x"

    def test_unknown_scripts_do_not_crash(self):
        result = sort_names(["Abonim", "日本", "Zarf"])
        assert len(result) == 3
        assert result[0] == "Abonim"

    def test_empty_string_sorts_first(self):
        assert sort_names(["Abonim", ""])[0] == ""


class TestSortKey:
    def test_case_does_not_change_the_primary_key(self):
        assert sort_key("Ushqim")[0] == sort_key("ushqim")[0]

    def test_case_is_still_a_stable_tiebreaker(self):
        result = sort_names(["ushqim", "Ushqim"])
        assert result == sorted(result, key=sort_key)
        assert len(set(result)) == 2

    def test_prefix_sorts_before_longer_name(self):
        assert sort_names(["Kafene", "Kafe"]) == ["Kafe", "Kafene"]

    def test_sort_names_does_not_mutate_its_input(self):
        names = ["Zarf", "Abonim"]
        original = list(names)
        sort_names(names)
        assert names == original


class TestNumberRuns:
    """Digits are grouped so they compare as numbers, not character by character."""

    def test_digit_runs_are_single_tokens(self):
        assert tokenize("kredia10") == ["k", "r", "e", "d", "i", "a", "10"]

    def test_ten_sorts_after_nine(self):
        assert sort_names(["Kredia 10", "Kredia 9"]) == ["Kredia 9", "Kredia 10"]

    def test_a_longer_run_of_numbers(self):
        names = ["Muaji 11", "Muaji 2", "Muaji 1", "Muaji 20"]
        assert sort_names(names) == ["Muaji 1", "Muaji 2", "Muaji 11", "Muaji 20"]

    def test_years_still_sort_correctly(self):
        assert sort_names(["2025 taksa", "2024 taksa"]) == [
            "2024 taksa",
            "2025 taksa",
        ]

    def test_leading_zeros_do_not_change_the_value(self):
        assert sort_names(["Muaji 007", "Muaji 8"]) == ["Muaji 007", "Muaji 8"]
