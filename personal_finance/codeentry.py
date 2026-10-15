"""Kutite e kodit / Boxed code entry.

Typing a one-time code into boxes that fill as you go, the way a verification
code is entered on a phone. The boxes are drawn on one line and redrawn after
every keystroke, so the code is never typed into an unmarked void.

This needs the terminal in raw mode, which is two different mechanisms:
`termios` on anything POSIX, `msvcrt` on Windows. Both are standard library.
Neither works when standard input is a pipe rather than a terminal, which is
how the tests and any script run this, so there is a third path that simply
reads a line - the same code is accepted either way.

Nothing here validates a code. It collects characters and hands them back.
"""

import sys

from . import typewriter
from .colors import BOLD, CYAN, DIM, paint

EMPTY = "_"
GROUP_SIZE = 3


def render(typed, length, group_size=GROUP_SIZE):
    """The boxes as they should look with `typed` entered so far.

    Filled boxes show their character, the next one is highlighted, and the
    rest are blank. Grouping is visual only - the separator is never part of
    the code.
    """
    cells = []
    for index in range(length):
        if index and index % group_size == 0:
            cells.append(" ")
        if index < len(typed):
            cells.append(paint(f"[{typed[index]}]", BOLD))
        elif index == len(typed):
            cells.append(paint(f"[{EMPTY}]", CYAN))
        else:
            cells.append(paint(f"[{EMPTY}]", DIM))
    return "".join(cells)


def _supported():
    """Whether the terminal can be read a keystroke at a time."""
    if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return False
    if sys.platform == "win32":
        try:
            import msvcrt  # noqa: F401
        except ImportError:
            return False
        return True
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except ImportError:
        return False
    return True


def _read_key_windows():
    import msvcrt

    key = msvcrt.getwch()
    # Arrow and function keys arrive as two reads; discard the second so a
    # stray arrow press does not land in a box.
    if key in ("\x00", "\xe0"):
        msvcrt.getwch()
        return None
    return key


def _read_key_posix():
    import termios
    import tty

    handle = sys.stdin.fileno()
    saved = termios.tcgetattr(handle)
    try:
        tty.setraw(handle)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(handle, termios.TCSADRAIN, saved)


def read_key():
    """One keystroke, or None for a key that should be ignored."""
    if sys.platform == "win32":
        return _read_key_windows()
    return _read_key_posix()


def prompt_code(label, length, allowed=None):
    """Collect `length` characters into boxes. Returns the text, or None.

    Fills as you type and submits itself once the last box is filled, which
    is what makes it feel like a code field rather than a text field.
    Backspace corrects; Escape and Ctrl+C cancel.

    Where the terminal cannot be read a keystroke at a time - a pipe, a
    script, the tests - it falls back to reading a whole line, and the same
    input is accepted.

    A code typed in full, Enter and all, while the text before the boxes was
    still appearing goes into the boxes as if typed there.
    """
    try:
        return _collect(label, length, allowed)
    finally:
        # A question answered: what follows starts afresh, as after any other.
        typewriter.settle()


def _collect(label, length, allowed):
    ahead = typewriter.typed_ahead()
    if ahead is not None:
        typed = "".join(key for key in ahead if _fits(key, allowed))[:length]
        sys.stdout.write("\r\033[K" + label + render(typed, length) + "\n")
        sys.stdout.flush()
        return typed

    if not _supported():
        try:
            return input(label)
        except EOFError:
            return None

    typed = ""
    while True:
        sys.stdout.write("\r\033[K" + label + render(typed, length))
        sys.stdout.flush()

        key = read_key()
        if key is None:
            continue

        # Raw mode disables the usual interrupt, so it is handled by hand.
        if key in ("\x03", "\x1b"):
            sys.stdout.write("\n")
            return None
        if key in ("\r", "\n"):
            sys.stdout.write("\n")
            return typed
        if key in ("\x7f", "\x08"):
            typed = typed[:-1]
            continue
        if not _fits(key, allowed) or len(typed) >= length:
            continue

        typed += key
        if len(typed) == length:
            # Redraw once more so the last character is seen before moving on.
            sys.stdout.write("\r\033[K" + label + render(typed, length) + "\n")
            sys.stdout.flush()
            return typed


def _fits(key, allowed):
    """Whether a key may go into a box."""
    return key.isprintable() and (allowed is None or key in allowed)
