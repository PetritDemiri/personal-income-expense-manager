"""Ngjyrat / Terminal colors.

Colors are opt-out and fail safe: if anything about the terminal is unclear,
output is plain. Callers always pad text to width *before* calling paint(),
because ANSI escape codes are invisible on screen but still count as
characters, and would otherwise break every table column.
"""

import os
import sys

from .config import EXPENSE, INCOME, TRANSFER

GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

_enabled = False


def detect_support(stream=None):
    """Whether it looks safe to print ANSI colors to a stream."""
    stream = stream or sys.stdout

    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR") is not None:
        return True
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if sys.platform == "win32":
        # Modern Windows terminals support ANSI once virtual terminal
        # processing is enabled. If that call fails, fall back to plain text.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # -11 = STD_OUTPUT_HANDLE, 7 = the default output mode combined
            # with ENABLE_VIRTUAL_TERMINAL_PROCESSING.
            return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
        except Exception:
            return False
    return True


def configure(force_off=False, stream=None):
    """Decide once, at start-up, whether colors are used."""
    global _enabled
    _enabled = False if force_off else detect_support(stream)
    return _enabled


def is_enabled():
    return _enabled


def paint(text, *styles):
    """Wrap text in ANSI styles, or return it unchanged when colors are off."""
    if not _enabled or not styles:
        return text
    return f"{''.join(styles)}{text}{RESET}"


def type_color(trans_type):
    """Green for income, red for expenses, cyan for transfers.

    A transfer must not be green or red: it is neither money gained nor money
    lost, and colouring it either way would misread at a glance.
    """
    if trans_type == INCOME:
        return GREEN
    if trans_type == EXPENSE:
        return RED
    if trans_type == TRANSFER:
        return CYAN
    return ""


def amount_color(amount):
    """Green for a non-negative balance, red once it goes below zero."""
    return GREEN if amount >= 0 else RED
