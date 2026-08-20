"""Tests for locating the user's Documents folder.

The naive answer - `~/Documents` - is wrong on two of the three platforms this
runs on. Windows may have the folder relocated or redirected into OneDrive;
Linux localizes the name. Both are covered here, along with the rule that an
explicit path is always honoured.
"""

import os
import subprocess

import pytest

from personal_finance import locations
from personal_finance.locations import (
    EXPORT_DIR_ENV,
    documents_directory,
    has_explicit_directory,
    resolve_export_path,
)


@pytest.fixture(autouse=True)
def no_override(monkeypatch):
    monkeypatch.delenv(EXPORT_DIR_ENV, raising=False)


def set_home(monkeypatch, path):
    """Point the home directory at `path` on any platform.

    POSIX reads HOME; Windows reads USERPROFILE and ignores HOME completely.
    A test that sets only HOME therefore passes on Linux and macOS while
    silently reading the real user's folders when the suite runs on Windows -
    which is exactly what happened before this helper existed.
    """
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("USERPROFILE", str(path))


class TestExplicitDirectoryDetection:
    @pytest.mark.parametrize(
        "path",
        ["transaksionet.csv", "out.csv", "a.csv"],
    )
    def test_bare_filenames_have_no_directory(self, path):
        assert not has_explicit_directory(path)

    @pytest.mark.parametrize(
        "path",
        [
            "./out.csv",
            "../out.csv",
            "sub/out.csv",
            "/tmp/out.csv",
            os.path.join("nested", "out.csv"),
        ],
    )
    def test_anything_with_a_separator_is_a_choice(self, path):
        assert has_explicit_directory(path)

    def test_empty_path_is_not_a_choice(self):
        assert not has_explicit_directory("")


class TestPathResolution:
    def test_bare_filename_goes_to_documents(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, str(tmp_path))
        assert resolve_export_path("out.csv") == str(tmp_path / "out.csv")

    def test_explicit_relative_path_stays_relative_to_the_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, "/somewhere/else")
        monkeypatch.chdir(tmp_path)
        # A script doing `financat --eksporto ./out.csv && process ./out.csv`
        # must keep working.
        assert resolve_export_path("./out.csv") == str(tmp_path / "out.csv")

    def test_absolute_path_is_used_exactly(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, "/somewhere/else")
        target = str(tmp_path / "sub" / "out.csv")
        assert resolve_export_path(target) == os.path.abspath(target)

    def test_parent_relative_path_is_honoured(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, "/somewhere/else")
        nested = tmp_path / "nested"
        nested.mkdir()
        monkeypatch.chdir(nested)
        assert resolve_export_path("../out.csv") == str(tmp_path / "out.csv")

    def test_result_is_always_absolute(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, str(tmp_path))
        assert os.path.isabs(resolve_export_path("out.csv"))
        assert os.path.isabs(resolve_export_path("./out.csv"))

    def test_tilde_is_expanded(self, monkeypatch):
        set_home(monkeypatch, "/home/testuser")
        resolved = resolve_export_path(os.path.join("~", "out.csv"))
        assert "~" not in resolved


class TestEnvironmentOverride:
    def test_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, str(tmp_path))
        assert documents_directory() == str(tmp_path)

    def test_empty_override_is_ignored(self, monkeypatch):
        monkeypatch.setenv(EXPORT_DIR_ENV, "")
        assert documents_directory() != ""


class TestLinuxLocalizedFolder:
    """A German desktop has ~/Dokumente, not ~/Documents."""

    def test_xdg_answer_is_used(self, tmp_path, monkeypatch):
        localized = tmp_path / "Dokumente"
        localized.mkdir()
        monkeypatch.setattr(locations.sys, "platform", "linux")
        monkeypatch.setattr(
            locations,
            "_xdg_documents",
            lambda: str(localized),
        )
        assert documents_directory() == str(localized)

    def test_falls_back_when_xdg_has_no_answer(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "Documents").mkdir(parents=True)
        monkeypatch.setattr(locations.sys, "platform", "linux")
        monkeypatch.setattr(locations, "_xdg_documents", lambda: None)
        set_home(monkeypatch, str(home))
        assert documents_directory() == str(home / "Documents")

    def test_xdg_echoing_home_is_not_an_answer(self, tmp_path, monkeypatch):
        home = str(tmp_path)
        set_home(monkeypatch, home)

        def fake_run(*_args, **_kwargs):
            class Result:
                stdout = home + "\n"

            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert locations._xdg_documents() is None

    def test_missing_xdg_command_is_survivable(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise FileNotFoundError("xdg-user-dir not installed")

        monkeypatch.setattr(subprocess, "run", boom)
        assert locations._xdg_documents() is None

    def test_a_hanging_xdg_command_is_survivable(self, monkeypatch):
        def slow(*_args, **_kwargs):
            raise subprocess.TimeoutExpired("xdg-user-dir", 2)

        monkeypatch.setattr(subprocess, "run", slow)
        assert locations._xdg_documents() is None


class TestWindowsRelocatedFolder:
    """The folder may be moved, or redirected into OneDrive."""

    def test_registry_answer_is_used(self, tmp_path, monkeypatch):
        relocated = tmp_path / "OneDrive" / "Documents"
        relocated.mkdir(parents=True)
        monkeypatch.setattr(locations.sys, "platform", "win32")
        monkeypatch.setattr(locations, "_windows_documents", lambda: str(relocated))
        assert documents_directory() == str(relocated)

    def test_falls_back_when_the_registry_cannot_be_read(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "Documents").mkdir(parents=True)
        monkeypatch.setattr(locations.sys, "platform", "win32")
        monkeypatch.setattr(locations, "_windows_documents", lambda: None)
        set_home(monkeypatch, str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        assert documents_directory() == str(home / "Documents")


class TestFallbackChain:
    def test_home_is_used_when_documents_does_not_exist(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(locations.sys, "platform", "darwin")
        set_home(monkeypatch, str(home))
        assert documents_directory() == str(home)

    def test_never_returns_none(self, monkeypatch):
        """Export must never refuse to write because a folder was not found."""
        monkeypatch.setattr(locations.sys, "platform", "linux")
        monkeypatch.setattr(locations, "_xdg_documents", lambda: None)
        set_home(monkeypatch, "/nonexistent-path-12345")
        assert documents_directory() is not None

    def test_macos_uses_the_plain_documents_folder(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "Documents").mkdir(parents=True)
        monkeypatch.setattr(locations.sys, "platform", "darwin")
        set_home(monkeypatch, str(home))
        assert documents_directory() == str(home / "Documents")

    def test_macos_does_not_consult_xdg(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "Documents").mkdir(parents=True)
        monkeypatch.setattr(locations.sys, "platform", "darwin")
        set_home(monkeypatch, str(home))

        def should_not_run():
            raise AssertionError("xdg must not be consulted on macOS")

        monkeypatch.setattr(locations, "_xdg_documents", should_not_run)
        assert documents_directory() == str(home / "Documents")
