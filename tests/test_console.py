"""Tests for what only matters when a person is sitting at the program.

The window's title, holding the window open long enough to read why the program
ended, a written record of a crash, and noticing when the window is closed. A
script, a pipe or the tests must see none of it: nothing may wait for an Enter
nobody will press.
"""

import builtins
import getpass
import os
import re
import signal
import sys

import pytest

from personal_finance import __version__, cli, console, i18n
from personal_finance.app import FinanceApp
from personal_finance.config import DATABASE_FILE, data_path


@pytest.fixture(autouse=True)
def plain(monkeypatch):
    from personal_finance import colors

    i18n.set_language("sq")
    colors.configure(force_off=True)
    monkeypatch.setattr(console, "_window_closed", False)
    monkeypatch.setattr(console, "_saved_title", None)
    yield
    i18n.set_language("sq")


class FakeStream:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class Answers:
    """Replies for input(), and a record of what was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = []

    def __call__(self, prompt=""):
        self.asked.append(prompt)
        if not self.replies:
            raise AssertionError(f"asked for more than expected: {prompt!r}")
        return self.replies.pop(0)


class TestAttended:
    def test_a_terminal_on_both_ends(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", FakeStream(True))
        monkeypatch.setattr(sys, "stdout", FakeStream(True))
        assert console.attended()

    @pytest.mark.parametrize("stdin,stdout", [(False, True), (True, False), (False, False)])
    def test_not_a_pipe_or_a_redirect(self, monkeypatch, stdin, stdout):
        monkeypatch.setattr(sys, "stdin", FakeStream(stdin))
        monkeypatch.setattr(sys, "stdout", FakeStream(stdout))
        assert not console.attended()

    def test_not_the_tests(self):
        assert not console.attended()

    def test_a_stream_that_cannot_say_is_not_a_terminal(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", object())
        assert not console.attended()


class TestPause:
    def test_it_waits_for_enter_after_a_blank_line(self, monkeypatch):
        answers = Answers("")
        monkeypatch.setattr(builtins, "input", answers)
        console.pause("Shtypni Enter per te mbyllur...")
        assert answers.asked == ["\nShtypni Enter per te mbyllur..."]

    @pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
    def test_closing_the_input_instead_is_fine(self, monkeypatch, error):
        def closed(_prompt=""):
            raise error

        monkeypatch.setattr(builtins, "input", closed)
        console.pause("...")


class FakeKernel32:
    """The three Windows console functions the program uses, by their own names."""

    def __init__(self, title="Windows PowerShell"):
        self.title = title
        self.handlers = []

    def GetConsoleTitleW(self, buffer, _size):
        buffer.value = self.title
        return len(self.title)

    def SetConsoleTitleW(self, title):
        self.title = title
        return 1

    def SetConsoleCtrlHandler(self, handler, add):
        if add:
            self.handlers.append(handler)
        else:
            self.handlers.remove(handler)
        return 1


class TestTheTitle:
    def test_named_after_the_program_and_given_back_afterwards(self, monkeypatch):
        kernel32 = FakeKernel32()
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(console, "_kernel32", lambda: kernel32)
        console.set_title("Menaxheri i te Ardhurave dhe Shpenzimeve Personale")
        assert kernel32.title == "Menaxheri i te Ardhurave dhe Shpenzimeve Personale"
        console.restore_title()
        assert kernel32.title == "Windows PowerShell"

    def test_left_alone_off_windows(self, monkeypatch):
        """Elsewhere a title is an escape sequence no terminal can undo."""
        kernel32 = FakeKernel32()
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(console, "_kernel32", lambda: kernel32)
        console.set_title("Menaxheri")
        console.restore_title()
        assert kernel32.title == "Windows PowerShell"

    def test_no_console_functions_is_survivable(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(console, "_kernel32", lambda: None)
        console.set_title("Menaxheri")
        console.restore_title()

    def test_the_window_title_message(self):
        assert i18n.t("window_title") == "Menaxheri i te Ardhurave dhe Shpenzimeve Personale"


def crash_and_log():
    try:
        raise RuntimeError("diçka u prish")
    except RuntimeError:
        return console.log_crash()


class TestTheErrorLog:
    def test_it_is_gabimet_txt_in_the_gabimet_folder(self):
        path = crash_and_log()
        assert os.path.basename(path) == "gabimet.txt"
        assert os.path.basename(os.path.dirname(path)) == "Gabimet"
        assert os.path.dirname(os.path.dirname(path)) == os.environ["FINANCE_HOME"]

    def test_it_says_when_which_version_and_what(self):
        text = open(crash_and_log(), encoding="utf-8").read()
        assert re.search(r"=== \d\d-\d\d-\d{4} \d\d:\d\d:\d\d  v" + re.escape(__version__), text)
        assert "Python " in text
        assert "Traceback (most recent call last)" in text
        assert "RuntimeError: diçka u prish" in text

    def test_a_later_crash_does_not_replace_an_earlier_one(self):
        crash_and_log()
        text = open(crash_and_log(), encoding="utf-8").read()
        assert text.count("RuntimeError: diçka u prish") == 2

    def test_an_unwritable_place_is_survivable(self, monkeypatch, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("")
        monkeypatch.setenv("FINANCE_HOME", str(blocker))
        assert crash_and_log() is None


class TestTheWindowBeingClosed:
    @pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX hang-up")
    def test_a_hang_up_becomes_an_ordinary_exit(self):
        """So the program's own clean-up runs on the way out."""
        with pytest.raises(SystemExit) as stopped, console.CloseWatch(lambda: None):
            signal.raise_signal(signal.SIGHUP)
        assert stopped.value.code == 128 + signal.SIGHUP
        assert console.window_closed()

    @pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX hang-up")
    def test_the_previous_handlers_are_put_back(self):
        before = signal.getsignal(signal.SIGHUP)
        with console.CloseWatch(lambda: None):
            assert signal.getsignal(signal.SIGHUP) != before
        assert signal.getsignal(signal.SIGHUP) == before

    @pytest.mark.parametrize("event", console.CLOSING_EVENTS)
    def test_on_windows_closing_runs_the_cleanup(self, event):
        ran = []
        assert console.handle_console_event(event, lambda: ran.append(True)) is False
        assert ran == [True]
        assert console.window_closed()

    def test_on_windows_ctrl_c_is_left_to_the_usual_interrupt(self):
        ran = []
        assert console.handle_console_event(0, lambda: ran.append(True)) is False
        assert ran == []
        assert not console.window_closed()

    def test_a_cleanup_that_fails_does_not_stop_the_window_closing(self):
        def broken():
            raise RuntimeError("database locked")

        assert console.handle_console_event(console.CTRL_CLOSE_EVENT, broken) is False


# ---------------------------------------------------------------------------
# The program as a whole
# ---------------------------------------------------------------------------


@pytest.fixture
def at_the_program(monkeypatch):
    """A person at a terminal, as far as the program can tell."""
    monkeypatch.setattr(console, "attended", lambda: True)
    titles = []
    monkeypatch.setattr(console, "set_title", titles.append)
    monkeypatch.setattr(console, "restore_title", lambda: titles.append("restored"))
    return titles


def ends_with(monkeypatch, code=None, error=None):
    def run(_args, _interactive, _attended):
        if error is not None:
            raise error
        return code

    monkeypatch.setattr(cli, "run_program", run)


class TestTheWindowStaysOpen:
    @pytest.mark.parametrize("code", [1, 2])
    def test_after_a_failure_until_enter(self, at_the_program, monkeypatch, code):
        answers = Answers("")
        monkeypatch.setattr(builtins, "input", answers)
        ends_with(monkeypatch, code=code)
        assert cli.main([]) == code
        assert answers.asked == ["\nShtypni Enter per te mbyllur..."]

    @pytest.mark.parametrize("code", [0, 130])
    def test_not_after_leaving_on_purpose(self, at_the_program, monkeypatch, code):
        monkeypatch.setattr(builtins, "input", Answers())
        ends_with(monkeypatch, code=code)
        assert cli.main([]) == code

    def test_never_for_a_script(self, monkeypatch):
        monkeypatch.setattr(builtins, "input", Answers())
        ends_with(monkeypatch, code=1)
        assert cli.main([]) == 1

    def test_never_for_a_flagged_run(self, at_the_program, monkeypatch):
        monkeypatch.setattr(builtins, "input", Answers())
        ends_with(monkeypatch, code=1)
        assert cli.main(["--lista"]) == 1


class TestACrash:
    def test_is_written_down_said_and_held_on_screen(self, at_the_program, monkeypatch, capsys):
        answers = Answers("")
        monkeypatch.setattr(builtins, "input", answers)
        ends_with(monkeypatch, error=RuntimeError("diçka u prish"))
        assert cli.main([]) == 1
        shown = capsys.readouterr().out
        assert "Ndodhi nje gabim i papritur." in shown
        assert console.error_log_path() in shown
        assert answers.asked == ["\nShtypni Enter per te mbyllur..."]
        assert "diçka u prish" in open(console.error_log_path(), encoding="utf-8").read()

    def test_a_script_still_sees_it_raised(self, monkeypatch):
        """A script or a scheduled task needs the failure, not a message."""
        ends_with(monkeypatch, error=RuntimeError("diçka u prish"))
        with pytest.raises(RuntimeError):
            cli.main(["--lista"])
        assert os.path.exists(console.error_log_path())

    def test_after_the_window_closed_nothing_is_written_or_asked(
        self, at_the_program, monkeypatch, capsys
    ):
        """Whatever breaks on the way out of a closed terminal broke because of
        that, and there is nobody left to read about it."""
        monkeypatch.setattr(builtins, "input", Answers())
        monkeypatch.setattr(console, "_window_closed", True)
        ends_with(monkeypatch, error=OSError("input/output error"))
        assert cli.main([]) == 129
        assert not os.path.exists(console.error_log_path())


class TestTheTitleAndTheTests:
    def test_the_window_is_named_and_given_back(self, at_the_program, monkeypatch):
        ends_with(monkeypatch, code=0)
        cli.main([])
        assert at_the_program == ["Menaxheri i te Ardhurave dhe Shpenzimeve Personale", "restored"]

    def test_given_back_after_a_crash_too(self, at_the_program, monkeypatch):
        monkeypatch.setattr(builtins, "input", Answers(""))
        ends_with(monkeypatch, error=RuntimeError("x"))
        cli.main([])
        assert at_the_program[-1] == "restored"

    def test_not_for_a_script(self, monkeypatch):
        titles = []
        monkeypatch.setattr(console, "set_title", titles.append)
        ends_with(monkeypatch, code=0)
        cli.main([])
        assert titles == []

    def test_in_english(self, at_the_program, monkeypatch):
        ends_with(monkeypatch, code=0)
        cli.main(["--gjuha", "en"])
        assert at_the_program[0] == "Personal Income and Expense Manager"

    def test_the_first_launch_tests_only_for_a_person(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "personal_finance.selftest.run_on_first_launch", lambda pause: calls.append(pause)
        )
        claimed()
        monkeypatch.setattr(builtins, "input", Answers("21"))
        cli.main([])
        assert calls == []

        monkeypatch.setattr(console, "attended", lambda: True)
        monkeypatch.setattr(console, "set_title", lambda _title: None)
        monkeypatch.setattr(builtins, "input", Answers("21"))
        cli.main([])
        assert len(calls) == 1


def claimed(password=None):
    """The database the program will open, with one user in it."""
    app = FinanceApp(path=data_path(DATABASE_FILE), quiet=True)
    if password:
        app.set_password(app.users()[0].id, password)
    app.close()


class TestARefusedSignIn:
    """Three wrong passwords end the program. That is a failure, not leaving
    on purpose - so a person at the program gets to read why it ended."""

    def wrong_passwords(self, monkeypatch):
        attempts = iter(["Gabim1234", "Gabim1234", "Gabim1234"])
        monkeypatch.setattr(getpass, "getpass", lambda _prompt="": next(attempts))

    def test_it_ends_with_a_failure(self, monkeypatch):
        claimed(password="Fjalekalimi1")
        self.wrong_passwords(monkeypatch)
        monkeypatch.setattr(builtins, "input", Answers("1"))
        assert cli.main([]) == 1

    def test_the_window_stays_open_after_it(self, at_the_program, monkeypatch, capsys):
        claimed(password="Fjalekalimi1")
        self.wrong_passwords(monkeypatch)
        answers = Answers("1", "")
        monkeypatch.setattr(builtins, "input", answers)
        assert cli.main([]) == 1
        assert answers.asked[-1] == "\nShtypni Enter per te mbyllur..."

    def test_leaving_from_the_sign_in_screen_is_not_a_failure(self, monkeypatch):
        claimed(password="Fjalekalimi1")
        monkeypatch.setattr(builtins, "input", Answers("3"))
        assert cli.main([]) == 0
