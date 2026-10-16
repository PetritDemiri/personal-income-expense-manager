"""Tests for the typing effect itself.

Messages appear letter by letter, questions twice as fast, and menus, lists
and tables a line at a time. Nothing keeps anyone waiting much more than a
second, Enter shows the rest at once without answering the next question, and
a script, a pipe or this test suite never sees any of it.

Time and keys are faked for most of these, so nothing actually waits. The
terminal tests at the end run the real thing in a terminal of its own, where
the platform has one.
"""

import io
import os
import re
import sys
import textwrap
import time

import pytest

from personal_finance import typewriter
from personal_finance.typewriter import ENTER, TYPING

NOT_POSIX = pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX terminal")


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeKeys:
    """Waits without waiting. `events` maps the nth wait to a key pressed
    during it; `late` is how much longer than asked each wait takes."""

    def __init__(self, clock):
        self.clock = clock
        self.pauses = []
        self.events = {}
        self.late = 0.0
        self.fail = None
        self.fail_closing = False
        self.opened = 0
        self.closed = 0

    def pause(self, seconds):
        if self.fail:
            raise self.fail
        self.pauses.append(seconds)
        self.clock.now += seconds + self.late
        return self.events.pop(len(self.pauses), None)

    def close(self):
        self.closed += 1
        if self.fail_closing:
            raise OSError("terminal gone")


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """Every test starts with the effect off and nothing remembered."""
    monkeypatch.setattr(typewriter, "_state", typewriter._State())


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(typewriter, "_clock", fake)
    return fake


@pytest.fixture
def keys(clock, monkeypatch):
    """The effect running at a pretend terminal. Returns its keys."""
    source = FakeKeys(clock)

    def open_keys():
        source.opened += 1
        return source

    monkeypatch.setattr(typewriter, "_open_keys", open_keys)
    typewriter._state.allowed = True
    return source


@pytest.fixture
def answers(monkeypatch):
    """Answers for input(), and the prompts it was given."""
    prompts = []

    def feed(*values):
        queue = list(values)

        def fake_input(prompt=""):
            prompts.append(prompt)
            if not queue:
                raise AssertionError(f"asked for more than expected: {prompt!r}")
            return queue.pop(0)

        monkeypatch.setattr("builtins.input", fake_input)
        return prompts

    return feed


class TestOffItIsPrintAndInput:
    """Off - flags, scripts, pipes, the tests - nothing changes at all."""

    def test_it_is_off_until_allowed(self):
        assert not typewriter.running()

    def test_say_prints(self, capsys):
        typewriter.say("Duke shtuar", "Te Ardhura", sep=" - ", end="!\n")
        assert capsys.readouterr().out == "Duke shtuar - Te Ardhura!\n"

    def test_roll_prints(self, capsys):
        typewriter.roll("1.", "Shtoni Te Ardhurat")
        assert capsys.readouterr().out == "1. Shtoni Te Ardhurat\n"

    def test_ask_is_input_with_its_prompt(self, answers):
        prompts = answers("Paga")
        assert typewriter.ask("Vendosni pershkrimin: ") == "Paga"
        assert prompts == ["Vendosni pershkrimin: "]

    def test_secret_is_getpass(self, monkeypatch):
        import getpass

        monkeypatch.setattr(getpass, "getpass", lambda prompt="": f"[{prompt}]")
        assert typewriter.secret("Fjalekalimi: ") == "[Fjalekalimi: ]"

    def test_nothing_waits_or_watches_the_keys(self, keys, capsys):
        typewriter._state.allowed = False
        typewriter.say("Anuluar.")
        typewriter.roll("1. Menu")
        assert keys.opened == 0
        assert capsys.readouterr().out == "Anuluar.\n1. Menu\n"


def at_a_terminal(monkeypatch, stdin=True, stdout=True):
    """Standard input and output that say whether they are a terminal.

    Called inside a test rather than from a fixture: pytest puts its own
    output capture back between setting up a fixture and running the test.
    """

    class Stream(io.StringIO):
        def __init__(self, terminal):
            super().__init__()
            self.terminal = terminal

        def isatty(self):
            return self.terminal

    monkeypatch.delenv("FINANCE_TYPING", raising=False)
    monkeypatch.setattr(sys, "stdin", Stream(stdin))
    monkeypatch.setattr(sys, "stdout", Stream(stdout))


class TestWhenItRuns:
    def test_for_a_person_at_a_terminal(self, monkeypatch):
        at_a_terminal(monkeypatch)
        typewriter.allow(True)
        assert typewriter.running()

    def test_not_when_the_program_says_no(self, monkeypatch):
        at_a_terminal(monkeypatch)
        typewriter.allow(False)
        assert not typewriter.running()

    def test_it_is_taken_away_again(self, monkeypatch):
        """The command line does this on the way out."""
        at_a_terminal(monkeypatch)
        typewriter.allow(True)
        typewriter.allow(False)
        assert not typewriter.running()

    def test_not_when_switched_off_for_everyone(self, monkeypatch):
        at_a_terminal(monkeypatch)
        monkeypatch.setenv("FINANCE_TYPING", "0")
        typewriter.allow(True)
        assert not typewriter.running()

    def test_only_0_switches_it_off(self, monkeypatch):
        at_a_terminal(monkeypatch)
        monkeypatch.setenv("FINANCE_TYPING", "1")
        typewriter.allow(True)
        assert typewriter.running()

    @pytest.mark.parametrize(("stdin", "stdout"), [(False, True), (True, False)])
    def test_not_when_either_end_is_not_a_terminal(self, monkeypatch, stdin, stdout):
        at_a_terminal(monkeypatch, stdin=stdin, stdout=stdout)
        typewriter.allow(True)
        assert not typewriter.running()

    def test_not_for_someone_who_switched_it_off(self, monkeypatch):
        at_a_terminal(monkeypatch)
        typewriter.allow(True)
        typewriter.prefer(False)
        assert not typewriter.running()
        typewriter.prefer(True)
        assert typewriter.running()

    def test_allowing_it_starts_afresh(self, monkeypatch):
        at_a_terminal(monkeypatch)
        typewriter._state.skipping = True
        typewriter._state.spent = 5.0
        typewriter._state.pending = ["1"]
        typewriter.allow(True)
        assert (typewriter._state.skipping, typewriter._state.spent) == (False, 0.0)
        assert typewriter._state.pending == []

    def test_the_tests_switch_it_off(self):
        assert os.environ.get("FINANCE_TYPING") == "0"


class TestTyping:
    def test_the_text_is_exactly_what_print_writes(self, keys, capsys):
        typewriter.say("Te Ardhura", "u shtua", sep=" - ", end="!\n")
        assert capsys.readouterr().out == "Te Ardhura - u shtua!\n"

    def test_a_letter_at_a_time(self, keys):
        typewriter.say("Anuluar.")
        # "Anuluar." and the newline.
        assert len(keys.pauses) == 9
        assert sum(keys.pauses) == pytest.approx(9 / 40)

    def test_a_slow_terminal_does_not_make_it_slower(self, keys, clock):
        """The letters keep to a schedule: time lost writing one is not
        waited again on top of the next."""
        keys.late = 0.01
        start = clock.now
        typewriter.say("Anuluar.")
        assert clock.now - start == pytest.approx(9 / 40 + 0.01)

    def test_a_question_twice_as_fast(self, keys, answers):
        answers("Paga")
        assert typewriter.ask("Pershkrimi: ") == "Paga"
        assert sum(keys.pauses) == pytest.approx(len("Pershkrimi: ") / 80)

    def test_the_question_is_not_shown_twice(self, keys, answers, capsys):
        """It is on screen already: input() would print it again."""
        prompts = answers("x")
        typewriter.ask("Pershkrimi: ")
        assert prompts == [""]
        assert capsys.readouterr().out == "Pershkrimi: "

    def test_a_long_message_is_typed_faster_not_for_longer(self, keys):
        typewriter.say("x" * 400)
        assert sum(keys.pauses) == pytest.approx(typewriter.MOST_FOR_ONE["typed"])

    def test_a_long_question_too(self, keys, answers):
        answers("x")
        typewriter.ask("x" * 400)
        assert sum(keys.pauses) == pytest.approx(typewriter.MOST_FOR_ONE["quick"])

    def test_a_colour_code_is_written_whole(self, keys, capsys):
        coloured = "\x1b[1m\x1b[31mGabim\x1b[0m"
        typewriter.say(coloured)
        assert capsys.readouterr().out == coloured + "\n"
        # Five letters and the newline: no wait inside a colour code.
        assert len(keys.pauses) == 6

    def test_stopped_part_way_its_colour_is_still_closed(self, keys, capsys):
        """Ctrl+C mid-message: what comes next is not left in its colour."""
        waited = keys.pause

        def interrupted(seconds):
            if len(keys.pauses) == 2:
                raise KeyboardInterrupt
            return waited(seconds)

        keys.pause = interrupted
        with pytest.raises(KeyboardInterrupt):
            typewriter.say("\x1b[1m\x1b[36mMire se vini\x1b[0m")
        assert capsys.readouterr().out == "\x1b[1m\x1b[36mMir\x1b[0m"
        assert keys.closed == 1

    def test_the_terminal_is_put_back_after_every_message(self, keys):
        typewriter.say("Anuluar.")
        typewriter.say("Anuluar.")
        assert keys.opened == keys.closed == 2


class TestRolling:
    def test_a_line_at_a_time(self, keys, capsys):
        for number in range(1, 22):
            typewriter.roll(f"{number}. Menu")
        assert capsys.readouterr().out.count("Menu") == 21
        assert keys.pauses == [typewriter.LINE_SECONDS] * 21

    def test_a_whole_menu_in_under_half_a_second(self, keys):
        for number in range(1, 22):
            typewriter.roll(f"{number}. Menu")
        assert sum(keys.pauses) < 0.5

    def test_the_terminal_is_put_back_after_every_line(self, keys):
        typewriter.roll("1. Menu")
        typewriter.roll("2. Menu")
        assert keys.opened == keys.closed == 2


class TestNothingKeepsAnyoneWaiting:
    MESSAGE = "Nje mesazh mjaft i gjate sa te zere kohe ne ekran."

    def test_everything_between_two_questions_together(self, keys, capsys):
        for _ in range(10):
            typewriter.say(self.MESSAGE)
        for number in range(200):
            typewriter.roll(f"{number}. rresht")
        assert sum(keys.pauses) <= typewriter.MOST_BETWEEN_QUESTIONS + 0.05
        shown = capsys.readouterr().out
        assert shown.count(self.MESSAGE) == 10
        assert shown.count("rresht") == 200

    def test_a_long_list_alone_is_held_to_it_too(self, keys, capsys):
        for number in range(200):
            typewriter.roll(f"{number}. rresht")
        assert len(keys.pauses) >= 50
        # The last line may start just inside the limit and end just past it.
        most = typewriter.MOST_BETWEEN_QUESTIONS + typewriter.LINE_SECONDS
        assert sum(keys.pauses) == pytest.approx(most) or sum(keys.pauses) < most
        assert capsys.readouterr().out.count("rresht") == 200

    def test_past_that_the_rest_appears_at_once(self, keys):
        for _ in range(10):
            typewriter.say(self.MESSAGE)
        opened = keys.opened
        typewriter.say(self.MESSAGE)
        typewriter.roll("1. Menu")
        assert keys.opened == opened

    def test_a_question_starts_the_count_again(self, keys, answers):
        answers("")
        for _ in range(10):
            typewriter.say(self.MESSAGE)
        typewriter.ask("? ")
        before = len(keys.pauses)
        typewriter.say("Anuluar.")
        assert len(keys.pauses) == before + 9


class TestEnter:
    def test_it_shows_the_rest_at_once(self, keys, capsys):
        keys.events = {3: ENTER}
        typewriter.say("Duke shtuar Te Ardhura...")
        assert capsys.readouterr().out == "Duke shtuar Te Ardhura...\n"
        assert len(keys.pauses) == 3

    def test_and_everything_else_until_the_next_question(self, keys, capsys):
        keys.events = {2: ENTER}
        typewriter.say("Menu:")
        for number in range(1, 22):
            typewriter.roll(f"{number}. Menu")
        assert len(keys.pauses) == 2
        assert capsys.readouterr().out.count("Menu") == 22

    def test_the_question_itself_appears_at_once_too(self, keys, answers, capsys):
        prompts = answers("1")
        keys.events = {2: ENTER}
        typewriter.say("Menu:")
        assert typewriter.ask("Zgjedhja: ") == "1"
        assert prompts == ["Zgjedhja: "]
        assert len(keys.pauses) == 2

    def test_the_next_screen_types_again(self, keys, answers):
        answers("1")
        keys.events = {2: ENTER}
        typewriter.say("Menu:")
        typewriter.ask("Zgjedhja: ")
        before = len(keys.pauses)
        typewriter.say("Anuluar.")
        assert len(keys.pauses) == before + 9

    def test_any_key_does_the_same(self, keys):
        """Someone already typing their answer is not made to wait either."""
        keys.events = {1: TYPING}
        typewriter.say("Duke shtuar Te Ardhura...")
        assert len(keys.pauses) == 1


class TestAnswersTypedAhead:
    """POSIX: an answer typed in full while text was still appearing."""

    def test_it_answers_the_next_question(self, keys, answers, capsys):
        answers()
        typewriter._state.pending = ["Paga"]
        assert typewriter.ask("Pershkrimi: ") == "Paga"
        # Shown as if typed there.
        assert capsys.readouterr().out == "Pershkrimi: Paga\n"

    def test_only_that_one(self, keys, answers):
        answers("Bonus")
        typewriter._state.pending = ["Paga"]
        typewriter.ask("? ")
        assert typewriter.ask("? ") == "Bonus"

    def test_several_answer_in_order(self, keys, answers):
        answers()
        typewriter._state.pending = ["1", "Paga"]
        assert typewriter.ask("? ") == "1"
        assert typewriter.ask("? ") == "Paga"

    def test_while_answers_wait_the_screens_appear_at_once(self, keys, answers):
        """Their answer is already given: nobody needs to watch them."""
        answers()
        typewriter._state.pending = ["1", "Paga"]
        typewriter.ask("? ")
        typewriter.say("Anuluar.")
        assert keys.pauses == []
        typewriter.ask("? ")
        typewriter.say("Anuluar.")
        assert len(keys.pauses) == 9

    def test_one_typed_while_the_question_appears(self, keys, answers, capsys):
        answers()

        def typed_ahead(seconds):
            keys.clock.now += seconds
            typewriter._state.pending.append("Paga")
            return TYPING

        keys.pause = typed_ahead
        assert typewriter.ask("Pershkrimi: ") == "Paga"
        assert capsys.readouterr().out == "Pershkrimi: Paga\n"

    def test_a_question_asked_another_way_takes_the_oldest(self):
        typewriter._state.pending = ["1", "Paga"]
        assert typewriter.typed_ahead() == "1"
        assert typewriter.typed_ahead() == "Paga"
        assert typewriter.typed_ahead() is None

    def test_a_password_typed_ahead_is_never_shown(self, keys, capsys, monkeypatch):
        import getpass

        monkeypatch.setattr(getpass, "getpass", lambda prompt="": pytest.fail("asked again"))
        typewriter._state.pending = ["Fjalekalimi1"]
        assert typewriter.secret("Fjalekalimi: ") == "Fjalekalimi1"
        assert capsys.readouterr().out == "Fjalekalimi: \n"


class TestItNeverStopsTheProgram:
    """Where the terminal fails the effect, the effect goes - not the program.
    The text still appears in full, at once."""

    def test_keys_that_cannot_be_read(self, keys, capsys):
        keys.fail = OSError("terminal gone")
        typewriter.say("Anuluar.")
        assert capsys.readouterr().out == "Anuluar.\n"
        assert not typewriter.running()

    def test_any_other_failure_while_waiting(self, keys, capsys):
        keys.fail = ValueError("closed")
        typewriter.say("Anuluar.")
        typewriter.roll("1. Menu")
        assert capsys.readouterr().out == "Anuluar.\n1. Menu\n"
        assert not typewriter.running()

    def test_a_terminal_that_cannot_be_put_back(self, keys, capsys):
        keys.fail_closing = True
        typewriter.say("Anuluar.")
        assert capsys.readouterr().out == "Anuluar.\n"
        assert not typewriter.running()

    @pytest.fixture
    def no_keys(self, monkeypatch):
        def broken(_handle):
            raise OSError("not a terminal")

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(typewriter, "PosixKeys", broken)
        typewriter._state.allowed = True

    def test_keys_that_cannot_be_watched(self, no_keys, capsys):
        typewriter.say("Anuluar.")
        assert capsys.readouterr().out == "Anuluar.\n"
        assert not typewriter.running()

    def test_a_line_when_keys_cannot_be_watched(self, no_keys, capsys):
        typewriter.roll("1. Menu")
        assert capsys.readouterr().out == "1. Menu\n"
        assert not typewriter.running()


class TestOpeningTheKeys:
    def test_posix_watches_standard_input(self, monkeypatch):
        opened = []
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(sys, "stdin", type("In", (), {"fileno": lambda self: 7})())
        monkeypatch.setattr(typewriter, "PosixKeys", lambda handle: opened.append(handle) or 1)
        assert typewriter._open_keys() == 1
        assert opened == [7]

    def test_windows_watches_the_console(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(typewriter, "WindowsKeys", lambda: "console")
        assert typewriter._open_keys() == "console"


@NOT_POSIX
class TestPosixKeys:
    """The real terminal machinery, on a terminal made for the test."""

    @pytest.fixture
    def terminal(self):
        leader, follower = os.openpty()
        yield leader, follower
        os.close(leader)
        os.close(follower)

    @staticmethod
    def echoing(handle):
        import termios

        return bool(termios.tcgetattr(handle)[3] & termios.ECHO)

    def test_typing_is_not_shown_while_text_appears(self, terminal):
        _, follower = terminal
        keys = typewriter.PosixKeys(follower)
        assert not self.echoing(follower)
        keys.close()
        assert self.echoing(follower)

    def test_nothing_pressed(self, terminal):
        _, follower = terminal
        keys = typewriter.PosixKeys(follower)
        assert keys.pause(0.01) is None
        keys.close()

    def test_enter_is_taken(self, terminal):
        import select

        leader, follower = terminal
        keys = typewriter.PosixKeys(follower)
        os.write(leader, b"\n")
        assert keys.pause(2) == ENTER
        keys.close()
        assert select.select([follower], [], [], 0)[0] == []
        assert typewriter._state.pending == []

    def test_an_answer_typed_ahead_is_kept(self, terminal):
        leader, follower = terminal
        keys = typewriter.PosixKeys(follower)
        os.write(leader, "Kafe me qumësht\n".encode())
        assert keys.pause(2) == TYPING
        keys.close()
        assert typewriter._state.pending == ["Kafe me qumësht"]

    def test_two_answers_stay_two_and_in_order(self, terminal):
        leader, follower = terminal
        keys = typewriter.PosixKeys(follower)
        os.write(leader, b"1\nPaga\n")
        assert keys.pause(2) == TYPING
        assert keys.pause(2) == TYPING
        keys.close()
        assert typewriter._state.pending == ["1", "Paga"]

    def test_an_enter_in_the_last_moment_is_still_taken(self, terminal):
        """Pressed after the last wait but before the question: it was meant
        for the text, and must not answer the question."""
        import select

        leader, follower = terminal
        keys = typewriter.PosixKeys(follower)
        os.write(leader, b"\n")
        time.sleep(0.05)
        keys.close()
        assert select.select([follower], [], [], 0)[0] == []


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

KEY_DOWN, KEY_UP = 1, 0
MOUSE_EVENT = 0x0002


def fill(buffer, events):
    for index, (event_type, down, virtual_key) in enumerate(events):
        buffer[index].event_type = event_type
        buffer[index].key.key_down = down
        buffer[index].key.virtual_key = virtual_key


def queue(*events):
    """A console input queue: (event type, key down, virtual key) each."""
    buffer = (typewriter._console_structures() * typewriter.LOOK_AHEAD)()
    fill(buffer, events)
    return buffer, len(events)


ENTER_DOWN = (typewriter.KEY_EVENT, KEY_DOWN, typewriter.VK_RETURN)
LETTER_DOWN = (typewriter.KEY_EVENT, KEY_DOWN, ord("P"))


class TestTheWindowsQueue:
    def test_the_layout_is_the_one_windows_uses(self):
        import ctypes

        record = typewriter._console_structures()
        assert ctypes.sizeof(record) == 20
        assert record.key.offset == 4

    def test_a_record_exactly_as_windows_writes_it(self):
        import struct

        record = typewriter._console_structures()
        # Event type, padding, then the key: down, repeats, virtual key,
        # scan code, character, control keys.
        layout = "<H2xiHHHHI"
        pressed = struct.pack(layout, typewriter.KEY_EVENT, 1, 1, typewriter.VK_RETURN, 28, 13, 0)
        released = struct.pack(layout, typewriter.KEY_EVENT, 0, 1, typewriter.VK_RETURN, 28, 13, 0)
        events = (record * 2).from_buffer_copy(released + pressed)
        assert typewriter.first_enter(events, 2) == (ENTER, 2)

    def test_nothing_pressed(self):
        assert typewriter.first_enter(*queue()) == (None, 0)

    def test_enter(self):
        assert typewriter.first_enter(*queue(ENTER_DOWN)) == (ENTER, 1)

    def test_any_other_key_first_is_left_for_the_question(self):
        assert typewriter.first_enter(*queue(LETTER_DOWN, ENTER_DOWN)) == (TYPING, 0)

    def test_releases_and_the_mouse_are_passed_over(self):
        """Including the release of the Enter that started the program."""
        events = queue(
            (typewriter.KEY_EVENT, KEY_UP, typewriter.VK_RETURN),
            (MOUSE_EVENT, 0, 0),
            ENTER_DOWN,
        )
        assert typewriter.first_enter(*events) == (ENTER, 3)


class FakeKernel32:
    """The three console calls, over a list of input events."""

    def __init__(self, *events, peek_fails=False):
        self.events = list(events)
        self.taken = []
        self.peek_fails = peek_fails

    def GetStdHandle(self, which):  # noqa: N802 - the Windows name
        assert which == typewriter.STD_INPUT_HANDLE
        return 7

    def PeekConsoleInputW(self, handle, buffer, length, count):  # noqa: N802
        if self.peek_fails:
            return 0
        waiting = self.events[:length]
        fill(buffer, waiting)
        count._obj.value = len(waiting)
        return 1

    def ReadConsoleInputW(self, handle, buffer, length, count):  # noqa: N802
        self.taken.append(length)
        del self.events[:length]
        count._obj.value = length
        return 1


class TestWindowsKeys:
    @pytest.fixture(autouse=True)
    def no_sleeping(self, monkeypatch):
        monkeypatch.setattr(typewriter.time, "sleep", lambda _seconds: None)

    @pytest.mark.skipif(sys.platform != "win32", reason="the real Windows console functions")
    def test_the_real_console_is_left_as_everything_else_finds_it(self):
        """The rest of the program calls the same functions through the shared
        ctypes.windll, and a type declared there would change them for it."""
        import ctypes

        before = ctypes.windll.kernel32.GetStdHandle.restype
        typewriter.WindowsKeys().pause(0)
        assert ctypes.windll.kernel32.GetStdHandle.restype is before

    def test_enter_is_taken(self):
        kernel = FakeKernel32(ENTER_DOWN)
        assert typewriter.WindowsKeys(kernel).pause(0.02) == ENTER
        assert kernel.taken == [1]
        assert kernel.events == []

    def test_any_other_key_is_left_for_the_question(self):
        kernel = FakeKernel32(LETTER_DOWN)
        assert typewriter.WindowsKeys(kernel).pause(0.02) == TYPING
        assert kernel.taken == []
        assert kernel.events == [LETTER_DOWN]

    def test_nothing_pressed(self):
        kernel = FakeKernel32()
        assert typewriter.WindowsKeys(kernel).pause(0.02) is None
        assert kernel.taken == []

    def test_a_console_that_cannot_be_read(self):
        kernel = FakeKernel32(ENTER_DOWN, peek_fails=True)
        assert typewriter.WindowsKeys(kernel).pause(0.02) is None
        assert kernel.taken == []


# ---------------------------------------------------------------------------
# A real terminal
# ---------------------------------------------------------------------------

PROGRAM = textwrap.dedent(
    """
    import time
    from personal_finance import typewriter

    typewriter.allow(True)
    print("RUNNING", typewriter.running(), flush=True)
    started = time.monotonic()
    for number in range(1, 6):
        typewriter.say(f"Mesazhi {number}: shkruhet shkronje pas shkronje, aq i gjate sa ka kohe.")
    took = time.monotonic() - started
    answer = typewriter.ask("Pyetja: ")
    print(f"TOOK={took:.2f} ANSWER=[{answer}]", flush=True)
    """
)


@NOT_POSIX
@pytest.mark.skipif(getattr(sys, "frozen", False), reason="needs Python to start the program")
class TestARealTerminal:
    """The whole thing, in a terminal of its own: Enter pressed while text
    appears, an answer typed ahead, and nothing pressed at all."""

    @staticmethod
    def run(steps):
        """Start the program; for each (text, keys), wait until the text is on
        screen and then press the keys. Returns the screen and the result."""
        import pty
        import select
        import signal

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        environment = {**os.environ, "PYTHONPATH": root}
        environment.pop("FINANCE_TYPING", None)
        pid, handle = pty.fork()
        if pid == 0:  # pragma: no cover - the child becomes the program
            try:
                os.execve(sys.executable, [sys.executable, "-c", PROGRAM], environment)
            finally:
                os._exit(127)

        shown = b""

        def read(seconds):
            """Take what is on screen; False once the program has gone."""
            nonlocal shown
            if not select.select([handle], [], [], seconds)[0]:
                return True
            try:
                chunk = os.read(handle, 65536)
            except OSError:
                return False
            shown += chunk
            return bool(chunk)

        def wait_for(pattern, seconds=15):
            deadline = time.monotonic() + seconds
            while not re.search(pattern, shown) and time.monotonic() < deadline:
                if not read(0.01):
                    return

        try:
            for text, typed in steps:
                wait_for(re.escape(text.encode()))
                os.write(handle, typed)
            wait_for(rb"ANSWER=\[[^\]]*\]")
        finally:
            # Left to finish on its own, and stopped only if it never does.
            deadline = time.monotonic() + 10
            while os.waitpid(pid, os.WNOHANG)[0] == 0:
                if time.monotonic() > deadline:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
                    break
                read(0.01)
            os.close(handle)

        screen = shown.decode("utf-8", "replace").replace("\r", "")
        found = re.search(r"TOOK=([0-9.]+) ANSWER=\[([^\]]*)\]", screen)
        assert found, screen
        return screen, float(found.group(1)), found.group(2)

    def test_enter_shows_the_rest_at_once_and_answers_nothing(self):
        screen, took, answer = self.run([("Mesazhi 1", b"\r"), ("Pyetja: ", b"Paga\r")])
        assert took < 0.9
        assert answer == "Paga"
        for number in range(1, 6):
            assert f"Mesazhi {number}: shkruhet" in screen

    def test_an_answer_typed_ahead_answers_the_question(self):
        screen, took, answer = self.run([("Mesazhi 1", b"Paga\r")])
        assert took < 0.9
        assert answer == "Paga"
        assert "Pyetja: Paga" in screen

    def test_nothing_pressed_takes_little_more_than_a_second(self):
        """Five messages of most of a second each, cut short together."""
        screen, took, answer = self.run([("Pyetja: ", b"Paga\r")])
        assert "RUNNING True" in screen
        assert typewriter.MOST_BETWEEN_QUESTIONS - 0.2 <= took < 2.0
        assert answer == "Paga"
