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


# The registry names for the folders people actually keep downloads in. The
# value is authoritative in the same way Documents is: it follows the folder
# if it has been moved or redirected.
_WINDOWS_FOLDER_KEYS = {
    "documents": "Personal",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "desktop": "Desktop",
}

_XDG_NAMES = {
    "documents": "DOCUMENTS",
    "downloads": "DOWNLOAD",
    "desktop": "DESKTOP",
}

_ENGLISH_NAMES = {
    "documents": "Documents",
    "downloads": "Downloads",
    "desktop": "Desktop",
}


def _windows_folder(which):
    try:
        import winreg
    except ImportError:
        return None
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, _WINDOWS_FOLDER_KEYS[which])
        expanded = os.path.expandvars(value)
        return expanded if os.path.isdir(expanded) else None
    except (OSError, KeyError):
        return None


def _xdg_folder(which):
    """Ask XDG, since these folders may not be named in English."""
    try:
        result = subprocess.run(
            ["xdg-user-dir", _XDG_NAMES[which]],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, KeyError):
        return None
    path = result.stdout.strip()
    if not path or path == os.path.expanduser("~"):
        return None
    return path if os.path.isdir(path) else None


def user_folder(which):
    """One of the folders people keep files in, or None if it has none.

    Looked up the same way Documents is - the shell's own record on Windows,
    XDG elsewhere - because these folders are routinely moved, redirected into
    OneDrive, or named in another language.
    """
    if sys.platform == "win32":
        found = _windows_folder(which)
        if found:
            return found
    elif sys.platform != "darwin":
        found = _xdg_folder(which)
        if found:
            return found

    candidate = os.path.join(os.path.expanduser("~"), _ENGLISH_NAMES[which])
    return candidate if os.path.isdir(candidate) else None


def search_folders():
    """Where a file to import is looked for, in the order they are tried.

    The current directory first, because someone who ran the program from a
    folder probably means that one. Then downloads, since a bank statement
    arrives there and nowhere else.
    """
    found = [os.getcwd()]
    for which in ("downloads", "documents", "desktop"):
        path = user_folder(which)
        if path and path not in found:
            found.append(path)
    return found


def folder_label(path):
    """The name of a folder on its own, for saying where a file came from."""
    return os.path.basename(os.path.normpath(path)) or path


def find_import_candidates(name):
    """Every file matching `name` in the folders that are searched.

    An exact name matches on its own; a name with no extension matches every
    file of that name whatever its type, so someone need not remember whether
    the bank sent HTML or CSV. Returns (path, folder_label) pairs.
    """
    if has_explicit_directory(name):
        expanded = os.path.abspath(os.path.expanduser(name))
        if os.path.isfile(expanded):
            return [(expanded, folder_label(os.path.dirname(expanded)))]
        return []

    wanted = (name or "").strip()
    if not wanted:
        return []

    stem, extension = os.path.splitext(wanted)
    matches = []
    for folder in search_folders():
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            continue
        for entry in entries:
            full = os.path.join(folder, entry)
            if not os.path.isfile(full):
                continue
            if extension:
                hit = entry.casefold() == wanted.casefold()
            else:
                hit = os.path.splitext(entry)[0].casefold() == stem.casefold()
            if hit and full not in [path for path, _ in matches]:
                matches.append((full, folder_label(folder)))
    return matches


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


def with_csv_suffix(path):
    """Add .csv unless the name already ends in it.

    Typing the extension is remembering a detail the program knows already,
    and forgetting it produced a file the computer could not open. Any other
    ending is left alone and gains .csv: someone naming a file after a month,
    "gushti.2026", meant the whole of that as the name.
    """
    text = (path or "").strip()
    if not text:
        return text
    return text if text.casefold().endswith(".csv") else f"{text}.csv"


def resolve_export_path(path):
    """Turn what the user typed into an absolute path to write to.

    A bare filename lands in Documents; anything with a directory in it is
    resolved as given, relative to the current directory as a command-line
    tool should be. The .csv ending is added when it is missing.
    """
    path = with_csv_suffix(path)
    if has_explicit_directory(path):
        return os.path.abspath(os.path.expanduser(path))
    return os.path.abspath(os.path.join(documents_directory(), path))
