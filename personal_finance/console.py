"""Dritarja / The console window.

What only matters when a person is sitting at the program rather than a script
driving it: the window's title, holding the window open long enough to read the
last thing printed, a written record of a crash, and noticing when the window
is closed while something is still on screen.

A double-clicked console window disappears the instant the program ends. A
crash, three wrong passwords or a cancelled setup all end it, and without a
pause the reason would vanish with the window before anyone could read it.
"""

import datetime
import os
import platform
import signal
import sys
import traceback

from . import __version__
from .colors import BOLD, RED, paint
from .i18n import t
from .locations import ERRORS_FOLDER, app_subdirectory

ERROR_LOG = "gabimet.txt"

# Windows console events. Closing the window, signing out of Windows and
# shutting it down all end the program without Python unwinding, so whatever
# must happen first has to happen in a handler.
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6
CLOSING_EVENTS = (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT)

# Set when the terminal went away. Nothing is printed or asked after that:
# there is nobody left to read it, and writing to a closed terminal only fails.
_window_closed = False

_saved_title = None


def attended():
    """Whether a person is at a terminal, rather than a script, a pipe or the tests."""
    for stream in (sys.stdin, sys.stdout):
        try:
            if not stream.isatty():
                return False
        except (AttributeError, ValueError, OSError):
            return False
    return True


def window_closed():
    return _window_closed


def pause(message):
    """Wait for Enter, so the last thing printed can be read before the window goes."""
    try:
        input(f"\n{message}")
    except (EOFError, KeyboardInterrupt, OSError):
        try:
            print()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# The title
# ---------------------------------------------------------------------------


def _kernel32():
    """The Windows console functions, or None anywhere they do not exist."""
    try:
        import ctypes

        return ctypes.windll.kernel32
    except (ImportError, AttributeError, OSError):
        return None


def set_title(title):
    """Name the window after the program, remembering what it was called before.

    Windows only. Elsewhere a title is set by an escape sequence that not every
    terminal honours and none can undo, so the window is left as it was.
    """
    global _saved_title
    if sys.platform != "win32":
        return
    kernel32 = _kernel32()
    if kernel32 is None:
        return
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(1024)
        if kernel32.GetConsoleTitleW(buffer, len(buffer)):
            _saved_title = buffer.value
        kernel32.SetConsoleTitleW(title)
    except (AttributeError, OSError, ValueError):
        pass


def restore_title():
    """Give the window back the title it had, so the shell is not left misnamed."""
    global _saved_title
    if _saved_title is None or sys.platform != "win32":
        return
    kernel32 = _kernel32()
    if kernel32 is not None:
        try:
            kernel32.SetConsoleTitleW(_saved_title)
        except (AttributeError, OSError, ValueError):
            pass
    _saved_title = None


# ---------------------------------------------------------------------------
# Crashes
# ---------------------------------------------------------------------------


def error_log_path():
    return os.path.join(app_subdirectory(ERRORS_FOLDER), ERROR_LOG)


def log_crash():
    """Append the exception being handled to the error log. Returns its path, or None.

    Each entry says when, which version, and on what - the first three
    questions anyone asks about a crash - followed by the traceback itself.
    Appended rather than overwritten, so an earlier crash is not lost to a
    later one.
    """
    path = error_log_path()
    stamp = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    system = f"Python {platform.python_version()}, {platform.platform()}"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"=== {stamp}  v{__version__}  ({system}) ===\n")
            handle.write(traceback.format_exc())
            handle.write("\n")
    except OSError:
        return None
    return path


def report_crash(path):
    """Say that something went wrong, and where it was written down."""
    try:
        print(paint(f"\n{t('crash_title')}", BOLD, RED))
        if path:
            print(t("crash_saved", path=path))
            print(t("crash_keep"))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# The window being closed
# ---------------------------------------------------------------------------


def handle_console_event(event, cleanup):
    """What to do with one Windows console event.

    Closing the window runs the cleanup. Always returns False, so Windows
    carries on with whatever it was doing - closing the window, or turning
    Ctrl+C into the usual interrupt.
    """
    global _window_closed
    if event in CLOSING_EVENTS:
        _window_closed = True
        try:
            cleanup()
        except Exception:
            # The window is going either way, and the next launch clears
            # whatever this could not.
            pass
    return False


class CloseWatch:
    """Run a cleanup when the window is closed, not only when the program ends.

    On Windows the close button ends the process without Python unwinding,
    but gives a handler a few seconds first; the cleanup runs there, on a
    thread of its own. Elsewhere, closing a terminal sends a hang-up, which is
    turned into an ordinary exit so that the program's own clean-up runs on
    the way out - the cleanup given here is not needed for that.

    Installed only while a person is at the program, and removed afterwards,
    so nothing lingers into whatever runs next.
    """

    def __init__(self, cleanup):
        self.cleanup = cleanup
        self._handler = None
        self._previous = {}

    def __enter__(self):
        if sys.platform == "win32":
            self._watch_windows()
        else:
            self._watch_posix()
        return self

    def __exit__(self, *_exc):
        if self._handler is not None:
            kernel32 = _kernel32()
            if kernel32 is not None:
                try:
                    kernel32.SetConsoleCtrlHandler(self._handler, False)
                except (AttributeError, OSError):
                    pass
            self._handler = None
        for number, previous in self._previous.items():
            try:
                signal.signal(number, previous)
            except (ValueError, OSError, TypeError):
                pass
        self._previous = {}
        return False

    def _watch_windows(self):
        kernel32 = _kernel32()
        if kernel32 is None:
            return
        try:
            import ctypes
            from ctypes import wintypes

            prototype = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
            # Kept on the object: Windows calls back into it, so it must not
            # be collected while it is installed.
            self._handler = prototype(lambda event: handle_console_event(event, self.cleanup))
            kernel32.SetConsoleCtrlHandler(self._handler, True)
        except (AttributeError, OSError, TypeError):
            self._handler = None

    def _watch_posix(self):
        for name in ("SIGHUP", "SIGTERM"):
            number = getattr(signal, name, None)
            if number is None:
                continue
            try:
                self._previous[number] = signal.signal(number, self._on_signal)
            except (ValueError, OSError):
                # Signals can only be caught on the main thread.
                pass

    def _on_signal(self, number, _frame):
        global _window_closed
        _window_closed = True
        # Closing a terminal can deliver this more than once, and a second one
        # arriving mid-cleanup would cut the cleanup short.
        try:
            signal.signal(number, signal.SIG_IGN)
        except (ValueError, OSError):
            pass
        raise SystemExit(128 + number)
