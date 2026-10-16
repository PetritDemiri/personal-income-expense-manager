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

    def test_why_they_could_not_run(self, first_launch):
        path = write_record(Result(NOT_RUN, reason="exit code 4: RuntimeError: broken"))
        lines = open(path, encoding="utf-8").read().splitlines()
        assert lines[-1] == "Arsyeja: exit code 4: RuntimeError: broken"

    def test_no_reason_when_there_is_none(self, first_launch):
        path = write_record(Result(RAN, passed=5))
        assert "Arsyeja" not in open(path, encoding="utf-8").read()

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
        assert run_suite(tiny) == Result(NOT_RUN, reason="no such file")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows' record of a program's streams")
    def test_windows_record_of_the_streams_is_never_asked(self, tiny):
        """Inside the .exe, while pytest has the screen, Windows' record of a
        program's keyboard and screen can name handles already closed. Asked
        for them, Windows refused to start the copy: "[WinError 6] The handle
        is invalid". Here that record names a handle nothing has, and the copy
        still starts, because it is handed each of its streams directly."""
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
        kernel32.SetStdHandle.restype = wintypes.BOOL

        keyboard_and_screen = (-10, -11)
        kept = {stream: kernel32.GetStdHandle(stream) for stream in keyboard_and_screen}
        try:
            for stream in keyboard_and_screen:
                assert kernel32.SetStdHandle(stream, 0x0FFFFFF0)
            result = run_suite(tiny)
        finally:
            for stream, handle in kept.items():
                kernel32.SetStdHandle(stream, handle)
        assert result == Result(RAN, passed=2, failed=1, skipped=1)

    def test_a_suite_that_cannot_start_says_why(self, tiny, capsys):
        """No report means no counts - but how it ended is still known."""
        conftest = os.path.join(tiny, "conftest.py")
        with open(conftest, "w", encoding="utf-8") as handle:
            handle.write('raise RuntimeError("broken on purpose")\n')
        result = run_suite(tiny)
        assert result.outcome == NOT_RUN
        assert result.reason == "exit code 4: RuntimeError: broken on purpose"
        # And what it said is shown, as it would have been.
        assert "broken on purpose" in capsys.readouterr().err


class TestHowARunEnded:
    @staticmethod
    def finished(code, said):
        return selftest.subprocess.CompletedProcess([], code, stderr=said)

    def test_its_exit_code_and_its_last_words(self):
        said = "Traceback (most recent call last):\n  ...\nValueError: no\n\n"
        assert selftest.how_it_ended(self.finished(1, said)) == "exit code 1: ValueError: no"

    def test_pytests_mark_is_left_off(self):
        said = "E   RuntimeError: broken\n"
        assert selftest.how_it_ended(self.finished(4, said)) == "exit code 4: RuntimeError: broken"

    def test_the_last_error_rather_than_the_last_line(self):
        said = (
            "ERROR: usage: financat [options] [file_or_dir]\n"
            "financat: error: unrecognized arguments: --no-such-option\n"
            "  inifile: None\n"
            "  rootdir: C:\\Temp\\_MEI123\n"
        )
        assert selftest.how_it_ended(self.finished(4, said)) == (
            "exit code 4: financat: error: unrecognized arguments: --no-such-option"
        )

    def test_whatever_it_said_last_when_it_reported_no_error(self):
        assert selftest.how_it_ended(self.finished(2, "stopped\n")) == "exit code 2: stopped"

    def test_a_run_that_said_nothing(self):
        assert selftest.how_it_ended(self.finished(3221225477, "")) == "exit code 3221225477"
        assert selftest.how_it_ended(self.finished(1, None)) == "exit code 1"


class TestInsideTheExe:
    """The .exe has no Python beside it to start pytest with. Its first launch
    starts the .exe itself, in its test mode, which runs pytest inside it.

    Whether this is the .exe is set by hand in each test: these tests also run
    inside the .exe, the first time it opens.
    """

    class Started:
        """What run_suite started, with what environment and which streams."""

        def __init__(self):
            self.commands = []
            self.environments = []
            self.streams = []

        def __call__(self, command, **kwargs):
            self.commands.append(command)
            self.environments.append(kwargs["env"])
            self.streams.append({name: kwargs.get(name) for name in ("stdin", "stdout", "stderr")})
            return selftest.subprocess.CompletedProcess(command, 0, stderr="")

    @pytest.fixture
    def started(self, monkeypatch):
        """What run_suite would have started, without starting anything."""
        started = self.Started()
        monkeypatch.setattr(selftest.subprocess, "run", started)
        monkeypatch.delenv(selftest.FRESH_COPY_ENV, raising=False)
        return started

    @staticmethod
    def without_report(command):
        return [part for part in command if not part.startswith("--junit-xml=")]

    def test_a_copy_of_the_source_starts_python(self, started, monkeypatch, tmp_path):
        monkeypatch.delattr(sys, "frozen", raising=False)
        run_suite(str(tmp_path / "tests"))
        assert started.commands[0][:3] == [sys.executable, "-m", "pytest"]

    def test_the_exe_starts_itself_in_its_test_mode(self, started, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        run_suite(str(tmp_path / "tests"))
        assert started.commands[0][:2] == [sys.executable, selftest.TEST_MODE]

    def test_both_run_the_same_tests_the_same_way(self, started, monkeypatch, tmp_path):
        tests = str(tmp_path / "tests")
        monkeypatch.delattr(sys, "frozen", raising=False)
        run_suite(tests)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        run_suite(tests)
        source, exe = (self.without_report(command) for command in started.commands)
        assert source[3:] == exe[2:] == selftest.pytest_arguments(tests)
        assert source[3] == tests

    def test_the_exes_second_copy_is_a_program_of_its_own(self, started, monkeypatch, tmp_path):
        """Started as a part of the first, sharing what it unpacked, it never
        ran on Windows - and said nothing about why."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        run_suite(str(tmp_path / "tests"))
        assert started.environments[0][selftest.FRESH_COPY_ENV] == "1"

    def test_python_is_started_as_it_always_was(self, started, monkeypatch, tmp_path):
        monkeypatch.delattr(sys, "frozen", raising=False)
        run_suite(str(tmp_path / "tests"))
        assert selftest.FRESH_COPY_ENV not in started.environments[0]

    @pytest.mark.parametrize("frozen", [True, False])
    def test_every_stream_is_handed_over(self, started, monkeypatch, tmp_path, frozen):
        """None is left for the system to find. Inside the .exe, Windows'
        record of where they are named handles already closed: "[WinError 6]
        The handle is invalid", and the copy never started."""
        monkeypatch.setattr(sys, "frozen", frozen, raising=False)
        run_suite(str(tmp_path / "tests"))
        assert started.streams[0] == {
            "stdin": selftest.subprocess.DEVNULL,
            "stdout": selftest.SCREEN,
            "stderr": selftest.subprocess.PIPE,
        }

    def test_the_test_mode_runs_pytest_inside(self, monkeypatch):
        given = []
        monkeypatch.setattr(pytest, "main", lambda arguments: given.append(arguments) or 3)
        assert selftest.run_inside(["tests", "-q"]) == 3
        assert given == [["tests", "-q"]]


class TestCheckingACopy:
    """`--run-bundled-tests` and nothing more: the check a first launch makes,
    started by hand - a second copy runs the tests, and the first says how it
    went. How a release is checked before it is published, so the check is
    the first launch's own rather than a likeness of it."""

    @pytest.fixture
    def runs(self, monkeypatch):
        """Each check gets this result, and the suite it was given is kept."""
        given = []

        def answer(result):
            def run(tests):
                given.append(tests)
                return result

            monkeypatch.setattr(selftest, "run_suite", run)
            return given

        return answer

    def test_it_runs_the_suite_packed_inside_the_way_a_first_launch_does(self, runs, capsys):
        given = runs(Result(RAN, passed=12, skipped=3))
        assert selftest.run_inside([]) == 0
        assert given == [selftest.tests_directory()]
        assert "Te gjitha 12 testet kaluan." in capsys.readouterr().out

    def test_a_failure_fails_it(self, runs, capsys):
        runs(Result(RAN, passed=10, failed=2))
        assert selftest.run_inside([]) == 1
        assert "2 teste deshtuan" in capsys.readouterr().out

    @pytest.mark.parametrize("outcome", [NOT_RUN, INTERRUPTED])
    def test_so_does_a_run_that_did_not_finish(self, runs, outcome):
        runs(Result(outcome))
        assert selftest.run_inside([]) == 1

    def test_and_says_why(self, runs, capsys):
        runs(Result(NOT_RUN, reason="[WinError 6] The handle is invalid"))
        selftest.run_inside([])
        assert "Arsyeja: [WinError 6] The handle is invalid" in capsys.readouterr().out

    def test_it_is_not_a_first_launch(self, runs, first_launch):
        """Nothing is written down: the program has still not been opened."""
        runs(Result(RAN, passed=12))
        selftest.run_inside([])
        assert not os.path.exists(record_path())

    def test_a_copy_without_tests_says_so(self, monkeypatch, capsys):
        monkeypatch.setattr(selftest, "tests_directory", lambda: None)
        monkeypatch.setattr(selftest, "run_suite", lambda _tests: pytest.fail("ran"))
        assert selftest.run_inside([]) == 1
        assert "no tests" in capsys.readouterr().err


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
        assert "zakonisht zgjat nje deri ne pese minuta" in shown

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

    def test_and_why(self, first_launch, capsys):
        result = Result(NOT_RUN, reason="exit code 4: RuntimeError: broken")
        run_on_first_launch(Pauses(), run=FakeRun(result))
        shown = capsys.readouterr().out
        assert "Arsyeja: exit code 4: RuntimeError: broken" in shown
        assert record_path() in shown

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
        assert "usually takes one to five minutes" in shown
        assert "All 7 tests passed." in shown
        assert pauses.messages == ["Press Enter to continue..."]
