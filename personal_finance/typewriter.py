"""Efekti i shkrimit / The typing effect.

What the program says appears letter by letter, as if someone were typing it.
Not everything is said the same way:

- typed:   headings and messages, about 40 letters a second
- quick:   questions, about twice that
- rolling: menus, lists, tables, reports and the hints above a question,
           a line at a time
- instant: errors, passwords, the code boxes, crash reports and the
           first-launch tests - anything that must not wait

A long message is typed faster rather than for longer, and everything shown
between two questions together never takes much more than a second; past
that, the rest appears at once. Pressing Enter shows the rest straight away,
until the next question - and that Enter is used up, so it can never answer
the next question by accident.

It runs only for a person at a terminal: a run with flags, a script, a pipe
and the test suite all get plain output. Each user can switch it off for
themselves in the users menu, and FINANCE_TYPING=0 switches it off for
everyone.

Watching for Enter while text appears is two different mechanisms. POSIX:
the terminal holds a line until Enter, so `select` says input is waiting
exactly when Enter has been pressed; echo is off meanwhile, so the Enter does
not break the line being typed. An answer typed in full while text was still
appearing is kept, and answers the next question. Windows: the console's input
queue is looked at without taking anything from it, and only an Enter is
taken - any other key is the start of an answer and is left where it is.
"""

import getpass
import os
import re
import sys
import time

from .console import attended

TYPED = "typed"
QUICK = "quick"

# Seconds per letter.
LETTER_SECONDS = {TYPED: 1 / 40, QUICK: 1 / 80}
# The longest one message or question may take. A longer one is typed faster,
# rather than leaving someone watching a paragraph arrive.
MOST_FOR_ONE = {TYPED: 0.6, QUICK: 0.3}
# Seconds per line of a menu, list or table: a 21-line menu rolls in in under
# half a second.
LINE_SECONDS = 0.02
# Everything shown between two questions together. Past this the rest appears
# at once, so no screen ever keeps anyone waiting.
MOST_BETWEEN_QUESTIONS = 1.2

SWITCH_ENV = "FINANCE_TYPING"

ENTER = "enter"
TYPING = "typing"

# A colour code is written whole: half of one on screen is garbage.
ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class _State:
    def __init__(self):
        # A person at a terminal - set by the command line, never by a script.
        self.allowed = False
        # The signed-in person's own choice.
        self.wanted = True
        # Enter was pressed: everything until the next question appears at once.
        self.skipping = False
        # Seconds spent appearing since the last question.
        self.spent = 0.0
        # POSIX only: answers typed in full while text was still appearing,
        # oldest first. Each answers the next question.
        self.pending = []


_state = _State()

# Seams for the tests: the clock, and where keys come from.
_clock = time.monotonic


def allow(on):
    """Let the effect run, if `on` and this really is a person at a terminal."""
    _state.allowed = bool(on) and os.environ.get(SWITCH_ENV) != "0" and attended()
    _state.pending = []
    settle()


def prefer(on):
    """The signed-in person's own choice."""
    _state.wanted = bool(on)


def running():
    return _state.allowed and _state.wanted


def settle():
    """A question was answered: the next screen starts afresh - at once, while
    answers typed ahead are still waiting, since its answer is already given."""
    _state.skipping = bool(_state.pending)
    _state.spent = 0.0


def _animating():
    return running() and not _state.skipping


# ---------------------------------------------------------------------------
# Saying things
# ---------------------------------------------------------------------------


def say(*parts, sep=" ", end="\n", speed=TYPED):
    """Print like print(), typed out letter by letter when the effect runs."""
    if not _animating() or _over_budget():
        print(*parts, sep=sep, end=end)
        return
    text = sep.join(str(part) for part in parts) + end
    _type(text, LETTER_SECONDS[speed], MOST_FOR_ONE[speed])


def roll(*parts, sep=" ", end="\n"):
    """Print like print(), one line of a menu, list or table at a time."""
    print(*parts, sep=sep, end=end)
    if not _animating() or _over_budget():
        return
    sys.stdout.flush()
    _pause(LINE_SECONDS)


def ask(prompt=""):
    """input(), with the question typed out quickly when the effect runs."""
    try:
        answer = typed_ahead()
        if answer is not None:
            print(f"{prompt}{answer}")
            return answer
        if not _animating():
            return input(prompt)
        say(prompt, end="", speed=QUICK)
        # Typed in full while the question itself was appearing.
        answer = typed_ahead()
        if answer is not None:
            print(answer)
            return answer
        return input()
    finally:
        settle()


def secret(prompt):
    """getpass(): always at once, and never shown - not even when typed ahead."""
    try:
        answer = typed_ahead()
        if answer is not None:
            print(prompt)
            return answer
        return getpass.getpass(prompt)
    finally:
        settle()


def typed_ahead():
    """The oldest answer typed in full while text was appearing, taken - or
    None. A question asked some other way than ask() takes it from here, so
    it answers that question rather than a later one."""
    return _state.pending.pop(0) if _state.pending else None


def _over_budget(elapsed=0.0):
    return _state.spent + elapsed >= MOST_BETWEEN_QUESTIONS


def _type(text, per_letter, most):
    """Write text a letter at a time, colour codes whole, watching for Enter."""
    pieces = [piece for piece in re.split(f"({ESCAPE.pattern})", text) if piece]
    letters = sum(len(piece) for piece in pieces if not ESCAPE.fullmatch(piece))
    per_letter = min(per_letter, most / max(letters, 1))

    out = sys.stdout
    keys = _open_keys()
    if keys is None:
        out.write(text)
        out.flush()
        return

    start = _clock()
    written = 0
    index = 0
    try:
        for index, piece in enumerate(pieces):
            if ESCAPE.fullmatch(piece):
                out.write(piece)
                continue
            for position, letter in enumerate(piece):
                elapsed = _clock() - start
                if _state.skipping or _over_budget(elapsed):
                    out.write(piece[position:] + "".join(pieces[index + 1 :]))
                    out.flush()
                    return
                out.write(letter)
                out.flush()
                written += 1
                wait = start + written * per_letter - _clock()
                if wait > 0:
                    _wait(keys, wait)
        out.flush()
    except BaseException:
        # Stopped part-way - Ctrl+C. The rest of the text is not shown, but
        # its colour codes are, so a colour it started does not run on into
        # whatever is shown next.
        try:
            out.write("".join(piece for piece in pieces[index + 1 :] if ESCAPE.fullmatch(piece)))
            out.flush()
        except Exception:
            pass
        raise
    finally:
        _close(keys)
        _state.spent += _clock() - start


def _pause(seconds):
    """Wait between lines, unless Enter says not to."""
    keys = _open_keys()
    if keys is None:
        return
    start = _clock()
    try:
        _wait(keys, seconds)
    finally:
        _close(keys)
        _state.spent += _clock() - start


# Nothing about the effect may ever stop the program. Where the terminal fails
# it, the effect is switched off for the rest of the run and the text still
# appears - at once.


def _wait(keys, seconds):
    """Wait, noticing Enter."""
    try:
        event = keys.pause(seconds)
    except Exception:
        _state.allowed = False
        _state.skipping = True
        return
    if event in (ENTER, TYPING):
        _state.skipping = True


def _close(keys):
    """Put the terminal back as it was."""
    try:
        keys.close()
    except Exception:
        _state.allowed = False


# ---------------------------------------------------------------------------
# Watching for Enter
# ---------------------------------------------------------------------------


def _open_keys():
    """Something to wait on that notices keys, or None if there is none."""
    try:
        if sys.platform == "win32":
            return WindowsKeys()
        return PosixKeys(sys.stdin.fileno())
    except Exception:
        _state.allowed = False
        return None


class PosixKeys:
    """The terminal holds a line until Enter is pressed, so input waiting
    means Enter was. Echo is off meanwhile, so the Enter cannot break the line
    being typed - and neither is an answer typed ahead shown twice."""

    def __init__(self, handle):
        import termios

        self.handle = handle
        self.saved = termios.tcgetattr(handle)
        quiet = termios.tcgetattr(handle)
        quiet[3] &= ~termios.ECHO
        termios.tcsetattr(handle, termios.TCSANOW, quiet)

    def close(self):
        import termios

        try:
            # An Enter pressed in the last moment is still the text's, not
            # the next question's.
            self._take(0)
        finally:
            termios.tcsetattr(self.handle, termios.TCSANOW, self.saved)

    def pause(self, seconds):
        return self._take(max(seconds, 0))

    def _take(self, seconds):
        """Wait up to `seconds` for a line, and take it if there is one."""
        import select

        ready, _, _ = select.select([self.handle], [], [], seconds)
        if not ready:
            return None
        # The terminal hands over one line per read.
        line = os.read(self.handle, 4096).decode("utf-8", "replace").rstrip("\r\n")
        if line:
            # A whole answer typed ahead: it answers the next question.
            _state.pending.append(line)
            return TYPING
        return ENTER


# Windows console input. Only key presses are read, but every kind of event
# takes the same 20 bytes. Laid out with fixed-size fields so it is the same
# everywhere - ctypes.wintypes sizes differ off Windows.
KEY_EVENT = 0x0001
VK_RETURN = 0x0D
STD_INPUT_HANDLE = -10
LOOK_AHEAD = 32


def _console_structures():
    import ctypes

    class KeyEventRecord(ctypes.Structure):
        _fields_ = [
            ("key_down", ctypes.c_int32),
            ("repeat_count", ctypes.c_uint16),
            ("virtual_key", ctypes.c_uint16),
            ("virtual_scan", ctypes.c_uint16),
            ("character", ctypes.c_uint16),
            ("control_keys", ctypes.c_uint32),
        ]

    class InputRecord(ctypes.Structure):
        _fields_ = [("event_type", ctypes.c_uint16), ("key", KeyEventRecord)]

    return InputRecord


def first_enter(records, count):
    """What the waiting input means: (ENTER, how many to take) when the first
    key pressed is Enter, (TYPING, 0) when it is anything else, (None, 0) when
    nothing has been pressed. Key releases, the mouse and focus changes are
    not presses and are passed over."""
    for index in range(count):
        record = records[index]
        if record.event_type != KEY_EVENT or not record.key.key_down:
            continue
        if record.key.virtual_key == VK_RETURN:
            return ENTER, index + 1
        return TYPING, 0
    return None, 0


class WindowsKeys:
    """Look at the console's input without taking it; take only an Enter."""

    def __init__(self, kernel32=None):
        import ctypes

        if kernel32 is None:
            # A copy of its own, so declaring a function's types here changes
            # nothing for the rest of the program, which shares ctypes.windll.
            kernel32 = ctypes.WinDLL("kernel32")
            # A handle is pointer-sized; the default would cut it to 32 bits.
            kernel32.GetStdHandle.restype = ctypes.c_void_p
        self.ctypes = ctypes
        self.kernel32 = kernel32
        self.handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        self.records = (_console_structures() * LOOK_AHEAD)()

    def close(self):
        return None

    def pause(self, seconds):
        time.sleep(max(seconds, 0))
        handle = self.ctypes.c_void_p(self.handle)
        count = self.ctypes.c_uint32(0)
        if not self.kernel32.PeekConsoleInputW(
            handle, self.records, LOOK_AHEAD, self.ctypes.byref(count)
        ):
            return None
        event, take = first_enter(self.records, count.value)
        if event == ENTER:
            taken = self.ctypes.c_uint32(0)
            self.kernel32.ReadConsoleInputW(handle, self.records, take, self.ctypes.byref(taken))
        return event
