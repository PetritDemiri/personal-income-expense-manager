"""Testet e hapjes se pare / The first-launch tests.

The first time a person opens the program, it runs its own test suite on
screen, says how it went, waits for Enter, and writes down that it has done so
in Documents\\Financat\\Testet\\testet.txt. That file is how it knows never to
do it again. Deleting it brings the tests back on the next launch.

The tests run only where they exist - a copy of the source with pytest
installed, or the Windows .exe, which has both packed inside it - and only for
a person at a terminal. A script, a piped command or a flagged run never waits
on them. FINANCE_SKIP_TESTS turns them off altogether, which is what the test
suite itself sets so it can never start itself, and what the demo recordings
set so they do not film it.

They run in a process of their own rather than inside the program. pytest
takes over the standard streams while it works and, on Windows, does not hand
the originals back, after which a password typed at the first-run setup was
shown on screen as it was typed. In a separate process nothing it does can
reach the program's own input. A copy of the source starts that process with
Python. The .exe has no Python to start - it is the only program there is - so
it starts itself, in its test mode, and runs pytest inside that.
"""

import datetime
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from xml.etree import ElementTree

from . import __version__
from .colors import BOLD, CYAN, DIM, GREEN, RED, YELLOW, paint
from .i18n import t
from .locations import TESTS_FOLDER, app_subdirectory

SKIP_ENV = "FINANCE_SKIP_TESTS"
RECORD_FILE = "testet.txt"

# What the .exe is started with to run the tests packed inside it. Read by the
# .exe's own starting point before anything else, never by the program.
TEST_MODE = "--run-bundled-tests"
# Tells PyInstaller's start-up code that a copy of the .exe is a program of its
# own rather than a part of the copy that started it.
FRESH_COPY_ENV = "PYINSTALLER_RESET_ENVIRONMENT"

# How a run ended, as written into the record.
RAN = "ran"
NOT_RUN = "not_run"
INTERRUPTED = "interrupted"

# The project's own name, used to tell its test suite from any other folder
# called "tests" that happens to sit beside an installed package.
PROJECT_NAME = 'name = "personal-finance-manager"'


@dataclass
class Result:
    outcome: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    # Why they could not run, when they could not: the error that stopped
    # them starting, or how the run ended without a report.
    reason: str = ""


def record_path():
    return os.path.join(app_subdirectory(TESTS_FOLDER), RECORD_FILE)


def tests_directory(root=None):
    """The test suite of this copy of the program, or None where it has none.

    The suite is found beside the package in a copy of the source. An
    installed copy has no tests, and a folder called "tests" next to it may
    belong to something else entirely, so the project file beside the suite
    has to name this project.
    """
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tests = os.path.join(root, "tests")
    if not os.path.isfile(os.path.join(tests, "conftest.py")):
        return None
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as handle:
            if PROJECT_NAME not in handle.read():
                return None
    except OSError:
        return None
    return tests


def pytest_available():
    import importlib.util

    return importlib.util.find_spec("pytest") is not None


def due():
    """Whether this launch is the one that should run the tests."""
    if os.environ.get(SKIP_ENV):
        return False
    if os.path.exists(record_path()):
        return False
    return tests_directory() is not None and pytest_available()


def run_suite(tests):
    """Run the suite in a process of its own and count what happened.

    Its output goes straight to the window, exactly as running pytest by hand
    would show it. The counts come from the JUnit report pytest writes, not
    from reading that output. Ctrl+C stops the tests rather than the program.

    When they cannot run, the result says why. What the run wrote to standard
    error is kept for that, and still shown, once it has ended.
    """
    root = os.path.dirname(tests)
    handle, report = tempfile.mkstemp(prefix="financat-", suffix=".xml")
    os.close(handle)

    environment = dict(os.environ)
    # The suite must never start itself, and plugins installed on this
    # machine have no business in a check of this program.
    environment[SKIP_ENV] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if getattr(sys, "frozen", False):
        # The .exe's second copy starts as a program of its own, unpacking
        # itself afresh, rather than as a part of this one sharing what this
        # one unpacked. Started as a part, on Windows it never ran the tests
        # and said nothing about why.
        environment[FRESH_COPY_ENV] = "1"
    command = [*pytest_command(), *pytest_arguments(tests), f"--junit-xml={report}"]
    try:
        try:
            finished = subprocess.run(
                command,
                cwd=root,
                env=environment,
                check=False,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
        except KeyboardInterrupt:
            return Result(INTERRUPTED)
        except OSError as error:
            return Result(NOT_RUN, reason=str(error))
        if finished.stderr:
            sys.stderr.write(finished.stderr)
            sys.stderr.flush()
        result = read_report(report)
        if result.outcome == NOT_RUN:
            result.reason = how_it_ended(finished)
        return result
    finally:
        try:
            os.remove(report)
        except OSError:
            pass


def how_it_ended(finished):
    """A run that wrote no report: its exit code, and the last error it
    reported - or, where it reported none, the last thing it said."""
    said = [line.strip() for line in (finished.stderr or "").splitlines() if line.strip()]
    errors = [line for line in said if "error" in line.lower()]
    reason = f"exit code {finished.returncode}"
    if said:
        last = (errors or said)[-1]
        # pytest marks the line of an error with "E" in front.
        if last.startswith("E "):
            last = last[1:].strip()
        reason += f": {last}"
    return reason


def pytest_command():
    """How to start pytest in a process of its own."""
    if getattr(sys, "frozen", False):
        # The .exe: there is no Python beside it to start, so it starts itself.
        return [sys.executable, TEST_MODE]
    return [sys.executable, "-m", "pytest"]


def pytest_arguments(tests):
    """The suite, run the way the first launch runs it."""
    return [
        tests,
        # Settings from the project file are replaced, so what is shown does
        # not depend on how the project is configured for its developers.
        "-o",
        "addopts=",
        "-q",
        "-p",
        "no:cacheprovider",
        "--rootdir",
        os.path.dirname(tests),
    ]


def run_inside(arguments):
    """The .exe's test mode: pytest, run inside this program.

    What the first launch starts, in a process of its own, where there is no
    Python to start pytest with. Given nothing, it runs the suite packed into
    the .exe - which is how a release is checked before it is published.
    """
    import pytest

    if not arguments:
        tests = tests_directory()
        if tests is None:
            print("There are no tests in this copy of the program.", file=sys.stderr)
            return int(pytest.ExitCode.USAGE_ERROR)
        arguments = pytest_arguments(tests)
    return int(pytest.main(arguments))


def read_report(path):
    """Count passes, failures and skips in a JUnit report."""
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return Result(NOT_RUN)

    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if not suites:
        return Result(NOT_RUN)

    tests = failures = errors = skipped = 0
    for suite in suites:
        tests += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    failed = failures + errors
    return Result(RAN, passed=max(tests - failed - skipped, 0), failed=failed, skipped=skipped)


def write_record(result, path=None):
    """Write down that the tests have run, and how. Returns the path, or None."""
    path = path or record_path()
    status = {
        RAN: t("record_ran"),
        NOT_RUN: t("record_not_run"),
        INTERRUPTED: t("record_interrupted"),
    }[result.outcome]
    stamp = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    lines = [
        t("record_title"),
        f"{t('record_date')}: {stamp}",
        f"{t('record_version')}: {__version__}",
        f"{t('record_status')}: {status}",
        f"{t('record_passed')}: {result.passed}",
        f"{t('record_failed')}: {result.failed}",
        f"{t('record_skipped')}: {result.skipped}",
    ]
    if result.reason:
        lines.append(f"{t('record_reason')}: {result.reason}")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        return None
    return path


def run_on_first_launch(pause, run=run_suite):
    """Run the tests if this is the first launch, show how it went, and wait.

    Returns whether they ran. The record is written however the run ended -
    passed, failed, interrupted or impossible - because the point is that it
    happens once, not that it keeps happening until it succeeds. A failure is
    written down to be looked at, rather than shown again on every launch.
    """
    if not due():
        return False

    print(paint(f"\n{t('window_title')}", BOLD, CYAN))
    print()
    print(t("tests_first_launch"))
    print(t("tests_explain"))
    print(t("tests_duration"))
    print()

    result = run(tests_directory())
    saved = write_record(result)

    print()
    if result.outcome == INTERRUPTED:
        print(paint(t("tests_interrupted"), YELLOW))
    elif result.outcome == NOT_RUN:
        print(paint(t("tests_not_run"), YELLOW))
        if result.reason:
            print(paint(f"{t('record_reason')}: {result.reason}", DIM))
    elif result.failed:
        print(paint(t("tests_some_failed", count=result.failed), BOLD, RED))
    else:
        print(paint(t("tests_all_passed", count=result.passed), BOLD, GREEN))
    if saved and (result.failed or result.outcome != RAN):
        print(t("tests_saved", path=saved))
    pause(t("press_enter_continue"))
    return True
