"""Tests for the tests that run the first time the program is opened.

The first launch runs the suite on screen, says how it went, waits for Enter,
and writes down that it has run in Documents\\Financat\\Testet\\testet.txt -
which is how it knows never to run again. These tests drive that with a fake
run, and once with a real one against a tiny suite of their own: the real
suite cannot run itself from inside itself.
"""

import os
import re
import sys
import textwrap

import pytest

from personal_finance import __version__, i18n, selftest
from personal_finance.selftest import (
    INTERRUPTED,
    NOT_RUN,
    RAN,
    Result,
    due,
    read_report,
    record_path,
    run_on_first_launch,
    run_suite,
    write_record,
)


@pytest.fixture
def first_launch(monkeypatch):
    """A machine where the tests have never run, and are allowed to."""
    monkeypatch.delenv("FINANCE_SKIP_TESTS", raising=False)
    i18n.set_language("sq")
    yield
    i18n.set_language("sq")


class FakeRun:
    """Stands in for running the suite, and remembers whether it was asked to."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self, _tests):
        self.calls += 1
        return self.result


class Pauses:
    def __init__(self):
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)


class TestWhenTheyRun:
    def test_on_the_first_launch(self, first_launch):
        assert due()

    def test_not_once_they_have_run(self, first_launch):
        write_record(Result(RAN, passed=3))
        assert not due()

    def test_not_when_switched_off(self, first_launch, monkeypatch):
        """What the suite itself sets, so it can never start itself."""
        monkeypatch.setenv("FINANCE_SKIP_TESTS", "1")
        assert not due()

    def test_not_where_there_is_no_test_suite(self, first_launch, monkeypatch):
        monkeypatch.setattr(selftest, "tests_directory", lambda: None)
        assert not due()

    def test_not_without_pytest(self, first_launch, monkeypatch):
        monkeypatch.setattr(selftest, "pytest_available", lambda: False)
        assert not due()

    def test_deleting_the_record_brings_them_back(self, first_launch):
        path = write_record(Result(RAN, passed=3))
        os.remove(path)
        assert due()


class TestFindingTheSuite:
    def layout(self, root, project='name = "personal-finance-manager"', conftest=True):
        (root / "tests").mkdir(parents=True)
        if conftest:
            (root / "tests" / "conftest.py").write_text("")
        if project is not None:
            (root / "pyproject.toml").write_text(f"[project]\n{project}\n")
        return root

    def test_this_copy_has_one(self):
        assert selftest.tests_directory() is not None

    def test_found_beside_the_package(self, tmp_path):
        root = self.layout(tmp_path)
        assert selftest.tests_directory(str(root)) == str(root / "tests")

    def test_a_tests_folder_belonging_to_something_else_is_ignored(self, tmp_path):
        """An installed copy can sit next to another package's "tests"."""
        root = self.layout(tmp_path, project='name = "something-else"')
        assert selftest.tests_directory(str(root)) is None

    def test_none_without_a_project_file(self, tmp_path):
        assert selftest.tests_directory(str(self.layout(tmp_path, project=None))) is None

    def test_none_without_a_conftest(self, tmp_path):
        assert selftest.tests_directory(str(self.layout(tmp_path, conftest=False))) is None


class TestTheRecord:
    def test_it_is_testet_txt_in_the_testet_folder(self):
        path = record_path()
        assert os.path.basename(path) == "testet.txt"
        assert os.path.basename(os.path.dirname(path)) == "Testet"
        assert os.path.dirname(os.path.dirname(path)) == os.environ["FINANCE_HOME"]

    def test_what_it_says(self, first_launch):
        path = write_record(Result(RAN, passed=1145, failed=2, skipped=1))
        lines = open(path, encoding="utf-8").read().splitlines()
        assert lines[0] == "Testet e para"
        assert re.fullmatch(r"Data: \d\d-\d\d-\d{4} \d\d:\d\d:\d\d", lines[1])
        assert lines[2:] == [
            f"Versioni: {__version__}",
            "Gjendja: u ekzekutuan",
            "Kaluan: 1145",
            "Deshtuan: 2",
            "U anashkaluan: 1",
        ]

    @pytest.mark.parametrize(
        "outcome,status",
        [(NOT_RUN, "nuk mund te ekzekutoheshin"), (INTERRUPTED, "u nderprene")],
    )
    def test_it_is_written_however_the_run_ended(self, first_launch, outcome, status):
        path = write_record(Result(outcome))
        assert f"Gjendja: {status}" in open(path, encoding="utf-8").read()

    def test_in_english(self, first_launch):
        i18n.set_language("en")
        path = write_record(Result(RAN, passed=5))
        text = open(path, encoding="utf-8").read()
        assert text.startswith("First tests\n")
        assert "Passed: 5" in text

    def test_an_unwritable_place_is_survivable(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("")
        assert write_record(Result(RAN), path=str(blocker / "testet.txt")) is None


class TestReadingTheReport:
    def write(self, tmp_path, body):
        path = tmp_path / "report.xml"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_counts(self, tmp_path):
        path = self.write(
            tmp_path,
            '<testsuites><testsuite name="pytest" tests="10" failures="2" errors="1" '
            'skipped="3"/></testsuites>',
        )
        assert read_report(path) == Result(RAN, passed=4, failed=3, skipped=3)

    def test_a_single_suite_without_the_wrapper(self, tmp_path):
        path = self.write(tmp_path, '<testsuite tests="4" failures="0" errors="0" skipped="0"/>')
        assert read_report(path) == Result(RAN, passed=4)

    def test_a_missing_report(self, tmp_path):
        assert read_report(str(tmp_path / "missing.xml")).outcome == NOT_RUN

    def test_a_broken_report(self, tmp_path):
        assert read_report(self.write(tmp_path, "<testsuites")).outcome == NOT_RUN


class TestRunningARealSuite:
    """A real pytest, in a process of its own, against a tiny suite."""

    @pytest.fixture
    def tiny(self, tmp_path):
        root = tmp_path / "project"
        tests = root / "tests"
        tests.mkdir(parents=True)
        (root / "pyproject.toml").write_text('[project]\nname = "personal-finance-manager"\n')
        (tests / "conftest.py").write_text("")
        (tests / "test_tiny.py").write_text(
            textwrap.dedent(
                """
                import os
                import pytest

                def test_one():
                    assert True

                def test_told_not_to_start_itself():
                    assert os.environ.get("FINANCE_SKIP_TESTS") == "1"

                def test_broken():
                    assert False

                @pytest.mark.skip(reason="not here")
                def test_skipped():
                    pass
                """
            )
        )
        return str(tests)

    def test_what_happened_is_counted(self, tiny):
        assert run_suite(tiny) == Result(RAN, passed=2, failed=1, skipped=1)

    def test_the_programs_own_input_is_left_alone(self, tiny):
        """Change 8. Run inside the program, pytest replaced the standard
        streams for good on Windows, and the first-run setup then showed the
        password as it was typed. In a process of its own it cannot."""
        before = (sys.stdin, sys.stdout, sys.stderr)
        descriptors = [os.fstat(number) for number in (0, 1, 2)]
        run_suite(tiny)
        assert (sys.stdin, sys.stdout, sys.stderr) == before
        after = [os.fstat(number) for number in (0, 1, 2)]
        assert [(d.st_dev, d.st_ino) for d in after] == [(d.st_dev, d.st_ino) for d in descriptors]

    def test_no_report_is_left_behind(self, tiny, tmp_path, monkeypatch):
        monkeypatch.setattr(selftest.tempfile, "tempdir", str(tmp_path))
        run_suite(tiny)
        assert not list(tmp_path.glob("financat-*.xml"))

    def test_ctrl_c_stops_the_tests_not_the_program(self, tiny, monkeypatch):
        def interrupted(*_args, **_kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(selftest.subprocess, "run", interrupted)
        assert run_suite(tiny).outcome == INTERRUPTED

    def test_an_interpreter_that_cannot_start_is_survivable(self, tiny, monkeypatch):
        def missing(*_args, **_kwargs):
            raise OSError("no such file")

        monkeypatch.setattr(selftest.subprocess, "run", missing)
        assert run_suite(tiny).outcome == NOT_RUN


class TestTheFirstLaunch:
    def test_they_run_once_and_never_again(self, first_launch, capsys):
        run = FakeRun(Result(RAN, passed=12))
        assert run_on_first_launch(Pauses(), run=run)
        assert not run_on_first_launch(Pauses(), run=run)
        assert run.calls == 1
        assert os.path.exists(record_path())

    def test_it_says_what_is_happening_and_how_long_it_takes(self, first_launch, capsys):
        run_on_first_launch(Pauses(), run=FakeRun(Result(RAN, passed=12)))
        shown = capsys.readouterr().out
        assert "Kjo eshte hera e pare qe hapet programi." in shown
        assert "programi kontrollon veten me testet e tij" in shown
        assert "nje deri ne tre minuta" in shown

    def test_it_waits_for_enter_after_showing_the_result(self, first_launch, capsys):
        pauses = Pauses()
        run_on_first_launch(pauses, run=FakeRun(Result(RAN, passed=12)))
        assert pauses.messages == ["Shtypni Enter per te vazhduar..."]
        assert "Te gjitha 12 testet kaluan." in capsys.readouterr().out

    def test_failures_are_reported_with_where_the_record_is(self, first_launch, capsys):
        run_on_first_launch(Pauses(), run=FakeRun(Result(RAN, passed=10, failed=2)))
        shown = capsys.readouterr().out
        assert "2 teste deshtuan. Programi vazhdon normalisht." in shown
        assert record_path() in shown

    def test_an_interrupted_run_is_said_so_and_not_repeated(self, first_launch, capsys):
        run_on_first_launch(Pauses(), run=FakeRun(Result(INTERRUPTED)))
        assert "Testet u nderprene" in capsys.readouterr().out
        assert not due()

    def test_a_run_that_could_not_start_is_said_so(self, first_launch, capsys):
        run_on_first_launch(Pauses(), run=FakeRun(Result(NOT_RUN)))
        assert "nuk mund te ekzekutoheshin" in capsys.readouterr().out

    def test_nothing_happens_when_they_are_not_due(self, first_launch, monkeypatch, capsys):
        monkeypatch.setenv("FINANCE_SKIP_TESTS", "1")
        pauses = Pauses()
        run = FakeRun(Result(RAN))
        assert not run_on_first_launch(pauses, run=run)
        assert run.calls == 0 and pauses.messages == []
        assert capsys.readouterr().out == ""

    def test_in_english(self, first_launch, capsys):
        i18n.set_language("en")
        pauses = Pauses()
        run_on_first_launch(pauses, run=FakeRun(Result(RAN, passed=7)))
        shown = capsys.readouterr().out
        assert "one to three minutes" in shown
        assert "All 7 tests passed." in shown
        assert pauses.messages == ["Press Enter to continue..."]
