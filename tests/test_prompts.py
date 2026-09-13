"""Tests for how the interface asks questions.

Three things the prompts had got wrong, each of which only shows up when
someone is actually using the program: the hints differed from stage to
stage, several questions could not be cancelled at all, and a task six
questions long threw away five correct answers to fix the sixth.
"""

import os

import pytest

from personal_finance.locations import with_csv_suffix
from personal_finance.ui import BACK, parse_positions, run_stages


class TestSteppingBack:
    def test_answers_are_collected_in_order(self):
        assert run_stages([("a", lambda _v: 1), ("b", lambda _v: 2)]) == {"a": 1, "b": 2}

    def test_a_later_question_can_read_an_earlier_answer(self):
        answers = run_stages([("a", lambda _v: 10), ("b", lambda v: v["a"] + 5)])
        assert answers["b"] == 15

    def test_going_back_from_the_first_question_cancels(self):
        assert run_stages([("a", lambda _v: BACK)]) is None

    def test_going_back_returns_to_the_previous_question(self):
        """And keeps the answers already given: losing four correct answers
        to fix the fifth is its own kind of rudeness."""
        asked = []
        attempts = {"b": 0}

        def ask_a(_v):
            asked.append("a")
            return 1

        def ask_b(_v):
            asked.append("b")
            attempts["b"] += 1
            return BACK if attempts["b"] == 1 else 2

        answers = run_stages([("a", ask_a), ("b", ask_b)])
        assert asked == ["a", "b", "a", "b"]
        assert answers == {"a": 1, "b": 2}

    def test_the_sentinel_is_not_none(self):
        """None already means "no subcategory" and "no account"; the two must
        not be confused."""
        assert BACK is not None
        assert repr(BACK) == "BACK"

    def test_no_stages_at_all(self):
        assert run_stages([]) == {}


class TestParsingPositions:
    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("1", [1]),
            ("1, 2, 3", [1, 2, 3]),
            ("1,2,3", [1, 2, 3]),
            ("3 1 2", [3, 1, 2]),
            ("  2  ", [2]),
        ],
    )
    def test_accepted(self, typed, expected):
        assert parse_positions(typed, 5) == expected

    def test_a_repeat_is_counted_once(self):
        assert parse_positions("1, 1, 2", 5) == [1, 2]

    @pytest.mark.parametrize("typed", ["", "   ", None, "0", "6", "x", "1, x", "1, 6"])
    def test_refused(self, typed):
        assert parse_positions(typed, 5) is None

    def test_one_bad_number_refuses_the_whole_entry(self):
        """A typo in a list of rows to delete should stop the deletion, not
        quietly remove a different set from the one that was meant."""
        assert parse_positions("1, 2, 99", 5) is None


class TestTheCsvSuffix:
    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("transaksionet", "transaksionet.csv"),
            ("transaksionet.csv", "transaksionet.csv"),
            ("TRANSAKSIONET.CSV", "TRANSAKSIONET.CSV"),
            ("gushti.2026", "gushti.2026.csv"),
            ("  emri  ", "emri.csv"),
        ],
    )
    def test_it_is_added_when_missing(self, typed, expected):
        assert with_csv_suffix(typed) == expected

    def test_nothing_typed_stays_nothing(self):
        assert with_csv_suffix("") == ""
        assert with_csv_suffix(None) == ""

    def test_an_exported_file_gets_the_extension(self, app, tmp_path, monkeypatch):
        """Typing it is remembering a detail the program knows already, and
        forgetting it produced a file the computer could not open."""
        from decimal import Decimal

        from personal_finance.export import export_transactions
        from personal_finance.schema import EXPENSE

        monkeypatch.setenv("FINANCE_EXPORT_DIR", str(tmp_path))
        app.add_transaction(EXPENSE, "Qera", Decimal("300"), "01-09-2026", "Qera")

        _count, written = export_transactions("pa-prapashtese", app.transactions())
        assert written.endswith(".csv")


def _answers(values):
    """Feed a list of replies to input(), one per call."""
    queue = list(values)

    def fake_input(_prompt=""):
        if not queue:
            raise AssertionError("asked for more input than expected")
        return queue.pop(0)

    return fake_input


class TestDeletingSeveral:
    @pytest.fixture
    def five(self, app):
        from decimal import Decimal

        from personal_finance.schema import EXPENSE

        for index in range(1, 6):
            app.add_transaction(
                EXPENSE,
                f"Shpenzim {index}",
                Decimal(index * 10),
                f"0{index}-09-2026",
                "Test",
            )
        return app

    def test_positions_are_resolved_before_anything_is_removed(self, five):
        """Deleting by position one at a time would shift every row below the
        first deletion up, and the second number would name a different
        transaction than the one on screen."""
        rows = five.transactions()
        chosen = [rows[position - 1] for position in parse_positions("2, 4", len(rows))]
        for view in chosen:
            five.delete_transaction(view.id)

        left = [t.description for t in five.transactions()]
        assert left == ["Shpenzim 1", "Shpenzim 3", "Shpenzim 5"]

    def test_deleting_returns_what_was_removed(self, five):
        rows = five.transactions()
        removed = [five.delete_transaction(rows[0].id), five.delete_transaction(rows[1].id)]
        assert [r.description for r in removed] == ["Shpenzim 1", "Shpenzim 2"]

    def test_the_deleted_table_keeps_the_numbers_that_were_on_screen(
        self, five, capsys, monkeypatch
    ):
        """Renumbering them from one would leave the user unable to tell which
        rows had gone, which is the only reason to print the table at all."""
        from personal_finance import colors, i18n
        from personal_finance.ui import delete_transaction

        i18n.set_language("sq")
        colors.configure(force_off=True)
        monkeypatch.setattr("builtins.input", _answers(["5, 3", "po"]))
        capsys.readouterr()

        delete_transaction(five)
        shown = capsys.readouterr().out
        table = shown[shown.index("Transaksionet e fshira") :]
        numbers = [line.split()[0] for line in table.split("\n") if line[:1].isdigit()]
        assert numbers == ["3", "5"]

    def test_the_right_rows_are_the_ones_removed(self, five, capsys, monkeypatch):
        from personal_finance import colors, i18n
        from personal_finance.ui import delete_transaction

        i18n.set_language("sq")
        colors.configure(force_off=True)
        monkeypatch.setattr("builtins.input", _answers(["5, 3", "po"]))
        capsys.readouterr()

        delete_transaction(five)
        left = [t.description for t in five.transactions()]
        assert left == ["Shpenzim 1", "Shpenzim 2", "Shpenzim 4"]

    def test_every_deletion_is_recorded(self, five):
        rows = five.transactions()
        for view in rows[:2]:
            five.delete_transaction(view.id)
        deletions = [e for e in five.history(entity="transactions") if e.action == "delete"]
        assert len(deletions) == 2


class TestFindingAFileToImport:
    """Naming a file should not mean knowing where the program looks or what
    the bank called the format.

    Before this, a bare name was opened relative to whatever folder the
    program happened to be started from, and failing produced an errno and an
    English message from the operating system - nothing anyone could act on,
    and not in the language they chose.
    """

    @pytest.fixture
    def folders(self, tmp_path, monkeypatch):
        import personal_finance.locations as locations

        made = {}
        for name in ("Downloads", "Documents", "Desktop"):
            made[name.lower()] = tmp_path / name
            made[name.lower()].mkdir()
        monkeypatch.setattr(locations, "user_folder", lambda which: str(made[which]))
        monkeypatch.chdir(tmp_path)
        return made

    def test_a_file_is_found_by_its_exact_name(self, folders):
        from personal_finance.locations import find_import_candidates

        (folders["downloads"] / "raporti.csv").write_text("x")
        found = find_import_candidates("raporti.csv")
        assert len(found) == 1
        assert found[0][1] == "Downloads"

    def test_the_extension_need_not_be_typed(self, folders):
        """Nobody should have to remember whether the bank sent HTML or CSV."""
        from personal_finance.locations import find_import_candidates

        (folders["downloads"] / "raporti.csv").write_text("x")
        assert len(find_import_candidates("raporti")) == 1

    def test_every_matching_format_is_offered(self, folders):
        from personal_finance.locations import find_import_candidates

        (folders["downloads"] / "raporti.csv").write_text("x")
        (folders["downloads"] / "raporti.htm").write_text("x")
        names = sorted(os.path.basename(p) for p, _ in find_import_candidates("raporti"))
        assert names == ["raporti.csv", "raporti.htm"]

    def test_each_match_says_which_folder_it_came_from(self, folders):
        from personal_finance.locations import find_import_candidates

        (folders["downloads"] / "raporti.csv").write_text("x")
        (folders["documents"] / "raporti.htm").write_text("x")
        labels = sorted(label for _p, label in find_import_candidates("raporti"))
        assert labels == ["Documents", "Downloads"]

    def test_downloads_is_searched_before_documents(self, folders):
        """A bank statement arrives there and nowhere else."""
        from personal_finance.locations import folder_label, search_folders

        order = [folder_label(f) for f in search_folders()]
        assert order.index("Downloads") < order.index("Documents")

    def test_a_full_path_is_used_as_given(self, tmp_path):
        from personal_finance.locations import find_import_candidates

        target = tmp_path / "diku" / "raporti.csv"
        target.parent.mkdir()
        target.write_text("x")
        found = find_import_candidates(str(target))
        assert found[0][0] == str(target)

    def test_nothing_matching_finds_nothing(self, folders):
        from personal_finance.locations import find_import_candidates

        assert find_import_candidates("mungon") == []

    def test_an_empty_name_finds_nothing(self, folders):
        from personal_finance.locations import find_import_candidates

        assert find_import_candidates("") == []
        assert find_import_candidates("   ") == []

    def test_a_folder_is_not_offered_as_a_file(self, folders):
        from personal_finance.locations import find_import_candidates

        (folders["downloads"] / "raporti").mkdir()
        assert find_import_candidates("raporti") == []


class TestUnreadableFiles:
    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def test_a_missing_file_is_explained_in_words(self, tmp_path, capsys):
        """Not an errno, and not in English when Albanian was chosen."""
        from personal_finance.ui import read_import_file

        assert read_import_file(str(tmp_path / "mungon.csv")) is None
        output = capsys.readouterr().out
        assert "nuk u gjet" in output
        assert "Errno" not in output

    def test_a_folder_is_named_as_a_folder(self, tmp_path, capsys):
        from personal_finance.ui import read_import_file

        (tmp_path / "dosje").mkdir()
        assert read_import_file(str(tmp_path / "dosje")) is None
        assert "eshte nje dosje" in capsys.readouterr().out

    def test_a_readable_file_comes_back(self, tmp_path):
        from personal_finance.ui import read_import_file

        target = tmp_path / "raporti.csv"
        target.write_text("Data,Shuma\n")
        assert read_import_file(str(target)).startswith(b"Data")


class TestNamingTheFoldersHonestly:
    """The folders are named as they are on the machine, not translated.

    Telling someone in Albanian to put a file in "Dokumente" sends them
    looking for a folder Windows calls "Documents". The names come from the
    filesystem, so they are right whatever language either is in.
    """

    def test_the_hint_uses_the_real_names(self, tmp_path, monkeypatch, capsys):
        import personal_finance.locations as locations
        from personal_finance import colors, i18n
        from personal_finance.ui import import_from_file

        made = {}
        for name in ("Downloads", "Documents", "Desktop"):
            made[name.lower()] = tmp_path / name
            made[name.lower()].mkdir()
        monkeypatch.setattr(locations, "user_folder", lambda which: str(made[which]))
        monkeypatch.chdir(tmp_path)
        i18n.set_language("sq")
        colors.configure(force_off=True)
        monkeypatch.setattr("builtins.input", lambda _prompt="": "anulo")
        capsys.readouterr()

        import_from_file(None)
        shown = capsys.readouterr().out
        assert "Downloads" in shown and "Documents" in shown
        assert "Dokumente" not in shown and "Shkarkime" not in shown


class TestRanges:
    """One parser for both screens, so selecting rows to import and choosing
    rows to delete are typed the same way."""

    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("5", [5]),
            ("1, 2, 3", [1, 2, 3]),
            ("5-9", [5, 6, 7, 8, 9]),
            ("1, 3, 5-9", [1, 3, 5, 6, 7, 8, 9]),
            ("2 5-7", [2, 5, 6, 7]),
            ("3-3", [3]),
        ],
    )
    def test_accepted(self, typed, expected):
        assert parse_positions(typed, 10) == expected

    def test_a_backwards_range_is_read_forwards(self):
        """ "9-5" can only have meant one thing."""
        assert parse_positions("9-5", 10) == [5, 6, 7, 8, 9]

    def test_a_range_covering_everything(self):
        assert parse_positions("1-10", 10) == list(range(1, 11))

    def test_overlapping_parts_are_not_repeated(self):
        assert parse_positions("1-3, 2-4", 10) == [1, 2, 3, 4]

    @pytest.mark.parametrize("typed", ["0-2", "1-99", "1--3", "a-3", "3-", "-3"])
    def test_a_bad_range_refuses_the_whole_entry(self, typed):
        assert parse_positions(typed, 10) is None

    def test_a_range_past_the_end_refuses_everything(self):
        """Not "take the part that fits": a typo should stop the task."""
        assert parse_positions("1, 2, 8-99", 10) is None


class TestTogglingSeveral:
    """Several rows move together rather than each flipping on its own, so a
    range reads as one decision about those rows."""

    def make(self, count, selected=True):
        from decimal import Decimal

        from personal_finance.importing import Candidate

        return [
            Candidate(
                row_number=index + 2,
                description=f"Rreshti {index + 1}",
                amount=Decimal("10"),
                occurred_on="01-09-2026",
                selected=selected,
            )
            for index in range(count)
        ]

    def test_one_row_toggles(self):
        from personal_finance.ui import toggle_candidates

        candidates = self.make(3)
        toggle_candidates(candidates, [2])
        assert [c.selected for c in candidates] == [True, False, True]

    def test_several_all_turn_off_when_all_were_on(self):
        from personal_finance.ui import toggle_candidates

        candidates = self.make(5)
        toggle_candidates(candidates, [2, 3, 4])
        assert [c.selected for c in candidates] == [True, False, False, False, True]

    def test_several_all_turn_on_when_any_was_off(self):
        """Otherwise a mixed selection would look untouched."""
        from personal_finance.ui import toggle_candidates

        candidates = self.make(5)
        candidates[2].selected = False
        toggle_candidates(candidates, [2, 3, 4])
        assert all(c.selected for c in candidates[1:4])

    def test_rows_that_cannot_be_imported_are_left_alone(self):
        from personal_finance.ui import toggle_candidates

        candidates = self.make(3, selected=False)
        candidates[1].problem = "date"
        toggle_candidates(candidates, [1, 2, 3])
        assert candidates[1].selected is False
        assert candidates[0].selected and candidates[2].selected


class TestTheImportCommandGuide:
    """The commands are listed one per line with what each does.

    A single line mixing two styles - "numri = zgjidh/hiq" explaining itself
    while "'te gjitha'" only named a word - left the reader guessing at half
    of it. The four ways of naming rows are shown as four examples, since the
    syntax alone does not say which is which.
    """

    ROW_KEYS = (
        "rows_single",
        "rows_several",
        "rows_range",
        "rows_mixed",
    )
    REST_KEYS = (
        "import_cmd_all",
        "import_cmd_none",
        "import_cmd_category",
        "import_cmd_import",
        "import_cmd_cancel",
    )

    @pytest.mark.parametrize("language", ["sq", "en"])
    def test_every_line_exists_in_both_languages(self, language):
        from personal_finance import i18n

        i18n.set_language(language)
        try:
            for key in ("rows_guide", "import_cmd_rest", *self.ROW_KEYS, *self.REST_KEYS):
                assert i18n.t(key).strip()
        finally:
            i18n.set_language("sq")

    @staticmethod
    def description_column(line):
        """Where the description starts: after the padding that follows the
        command, which is the last run of two or more spaces."""
        import re as _re

        gaps = list(_re.finditer(r" {2,}", line.rstrip()))
        return gaps[-1].end()

    @pytest.mark.parametrize("language", ["sq", "en"])
    def test_the_descriptions_line_up(self, language):
        """Ragged columns in a guide are harder to read than no columns."""
        from personal_finance import i18n

        i18n.set_language(language)
        try:
            for group in (self.ROW_KEYS, self.REST_KEYS):
                columns = {self.description_column(i18n.t(key)) for key in group}
                assert len(columns) == 1, (
                    f"descriptions start at different columns: "
                    f"{[(key, i18n.t(key)) for key in group]}"
                )
        finally:
            i18n.set_language("sq")

    @pytest.mark.parametrize("language", ["sq", "en"])
    def test_each_way_of_naming_rows_is_shown(self, language):
        """The syntax alone does not say which form is which."""
        from personal_finance import i18n

        i18n.set_language(language)
        try:
            shown = " ".join(i18n.t(key) for key in self.ROW_KEYS)
            assert "5, 6, 7" in shown
            assert "1-3" in shown
            # Two singles and a range, so "mixed" is unmistakable: "2, 5-9"
            # could be read as one of each.
            assert "3, 4, 5-9" in shown
        finally:
            i18n.set_language("sq")

    def test_the_examples_actually_parse(self):
        """A guide that shows something the program refuses would be worse
        than no guide."""
        for typed in ("5", "5, 6, 7", "1-3", "3, 4, 5-9"):
            assert parse_positions(typed, 10) is not None


class TestThePreviewIsSpacedOut:
    """Blank lines between the blocks, so a long screen can be read.

    The table, the count, the commands and the prompt each stand apart; what
    the user typed stays attached to what it produced.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    def candidates(self):
        from decimal import Decimal

        from personal_finance.importing import Candidate

        return [
            Candidate(
                row_number=index + 2,
                description=f"Rreshti {index + 1}",
                amount=Decimal("10"),
                occurred_on="01-09-2026",
            )
            for index in range(3)
        ]

    def test_the_table_is_preceded_by_a_blank_line(self, capsys):
        from personal_finance.display import print_candidates

        print("paraprak")
        print_candidates(self.candidates(), ".", "dd-mm-yyyy")
        lines = capsys.readouterr().out.split("\n")
        assert lines[0] == "paraprak"
        assert lines[1] == ""

    def test_the_count_is_preceded_by_a_blank_line(self, capsys):
        from personal_finance.display import print_candidates

        print_candidates(self.candidates(), ".", "dd-mm-yyyy")
        lines = capsys.readouterr().out.split("\n")
        position = next(i for i, line in enumerate(lines) if "Zgjedhur:" in line)
        assert lines[position - 1] == ""

    def test_an_empty_preview_still_says_so(self, capsys):
        from personal_finance.display import print_candidates

        print_candidates([], ".", "dd-mm-yyyy")
        assert "Nuk ka asnje rresht" in capsys.readouterr().out


class TestTheDeleteScreenIsSpacedOut:
    """The table, the guide, the question and the result each stand apart.

    What the user typed stays attached to what it produced: cancelling, and
    the line saying what was deleted, follow straight on.
    """

    @pytest.fixture(autouse=True)
    def plain(self):
        from personal_finance import colors, i18n

        i18n.set_language("sq")
        colors.configure(force_off=True)
        yield
        i18n.set_language("sq")

    @pytest.fixture
    def four(self, app):
        from decimal import Decimal

        from personal_finance.schema import EXPENSE

        for index in range(1, 5):
            app.add_transaction(
                EXPENSE,
                f"Rreshti {index}",
                Decimal(index * 10),
                f"0{index}-09-2026",
                "Test",
            )
        return app

    def shown(self, app, capsys, monkeypatch, replies):
        from personal_finance.ui import delete_transaction

        monkeypatch.setattr("builtins.input", _answers(replies))
        capsys.readouterr()
        delete_transaction(app)
        return capsys.readouterr().out.split("\n")

    def test_a_blank_line_separates_the_table_from_the_guide(self, four, capsys, monkeypatch):
        lines = self.shown(four, capsys, monkeypatch, ["anulo"])
        guide = next(i for i, line in enumerate(lines) if "Zgjidhni rreshtat" in line)
        assert lines[guide - 1] == ""

    def test_a_blank_line_separates_the_guide_from_the_question(self, four, capsys, monkeypatch):
        lines = self.shown(four, capsys, monkeypatch, ["anulo"])
        cancel_hint = next(i for i, line in enumerate(lines) if "anulo' per" in line)
        assert lines[cancel_hint + 1] == ""

    def test_a_blank_line_precedes_what_was_deleted(self, four, capsys, monkeypatch):
        lines = self.shown(four, capsys, monkeypatch, ["1-2", "po"])
        result = next(i for i, line in enumerate(lines) if "U fshine" in line)
        assert lines[result - 1] == ""

    def test_the_same_for_a_single_deletion(self, four, capsys, monkeypatch):
        lines = self.shown(four, capsys, monkeypatch, ["1"])
        result = next(i for i, line in enumerate(lines) if "U fshi:" in line)
        assert lines[result - 1] == ""
