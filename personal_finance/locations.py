"""Vendndodhjet e sistemit / Platform locations.

Finding the user's Documents folder, which is not `~/Documents` on two of the
three platforms this runs on:

Windows may have the folder relocated, or redirected into OneDrive, which is
common enough that assuming the default path is wrong for a lot of people. The
shell records the real location in the registry.

Linux localizes the name - a German desktop has `~/Dokumente`. The XDG
specification records the real name in a config file, and `xdg-user-dir` reads
it.

macOS genuinely is `~/Documents`.

Every lookup can fail, so each one falls back: the platform's answer, then the
home directory, then the current directory. Export must never refuse to write
because a folder could not be identified.
"""

import os
import subprocess
import sys

# Overrides everything below. For anyone who keeps exports somewhere specific.
EXPORT_DIR_ENV = "FINANCE_EXPORT_DIR"


def _windows_documents():
    """Read the real Documents path from the shell's own record of it.

    The registry value is authoritative: it follows the folder if it has been
    moved or redirected into OneDrive, which the default path does not.
    """
    try:
        import winreg
    except ImportError:
        return None

    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")
        # The stored value often contains %USERPROFILE%.
        expanded = os.path.expandvars(value)
        return expanded if os.path.isdir(expanded) else None
    except OSError:
        return None


def _xdg_documents():
    """Ask XDG for the Documents folder, which may not be in English."""
    try:
        result = subprocess.run(
            ["xdg-user-dir", "DOCUMENTS"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    path = result.stdout.strip()
    # xdg-user-dir echoes the home directory when it has no answer, which is
    # not an answer.
    if not path or path == os.path.expanduser("~"):
        return None
    return path if os.path.isdir(path) else None


def documents_directory():
    """The user's Documents folder, or the best available substitute.

    Never returns None: falls back to the home directory, then to the current
    directory, so a caller can always write somewhere.
    """
    override = os.environ.get(EXPORT_DIR_ENV)
    if override:
        return override

    if sys.platform == "win32":
        found = _windows_documents()
        if found:
            return found
    elif sys.platform != "darwin":
        found = _xdg_documents()
        if found:
            return found

    # macOS, and the fallback for the other two.
    candidate = os.path.join(os.path.expanduser("~"), "Documents")
    if os.path.isdir(candidate):
        return candidate

    home = os.path.expanduser("~")
    if os.path.isdir(home):
        return home

    return os.getcwd()


def has_explicit_directory(path):
    """Whether the user chose where the file goes.

    A bare name like `transaksionet.csv` means "somewhere sensible". Anything
    with a separator - `./out.csv`, `../out.csv`, an absolute path - is a
    choice, and choices are honoured.
    """
    if not path:
        return False
    head, _tail = os.path.split(path)
    return bool(head)


def resolve_export_path(path):
    """Turn what the user typed into an absolute path to write to.

    A bare filename lands in Documents; anything with a directory in it is
    resolved as given, relative to the current directory as a command-line
    tool should be.
    """
    if has_explicit_directory(path):
        return os.path.abspath(os.path.expanduser(path))
    return os.path.abspath(os.path.join(documents_directory(), path))
