# How financat.exe, the Windows download on every release, is built.
#
#     pip install -e ".[dev,build]"
#     pyinstaller windows/financat.spec --noconfirm
#
# Run from the project folder. Writes dist\financat.exe: one file, Python and
# all, with nothing else to install. .github/workflows/release.yml builds it
# the same way for every release. PyInstaller builds for the system it runs
# on, so the Windows .exe has to be built on Windows.
#
# The test suite goes inside too, with pytest, so the .exe runs its own tests
# the first time it opens, as a copy of the source does.

import ast
import importlib.util
import os

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = os.path.dirname(SPECPATH)  # noqa: F821 - provided by PyInstaller
TESTS = os.path.join(ROOT, "tests")

# pytest and what it needs. It imports much of itself on demand, so the
# analysis would not see it all.
PYTEST = ["pytest", "_pytest", "pluggy", "iniconfig", "packaging", "pygments"]
# Used by pytest on Windows for colour, where it is installed.
OPTIONAL = ["colorama"]


def installed(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def imported_by_tests():
    """Every module the tests import. They go in as files rather than through
    the analysis, so anything only they use would otherwise be left out."""
    names = set()
    for directory, subdirectories, files in os.walk(TESTS):
        subdirectories[:] = [d for d in subdirectories if d != "__pycache__"]
        for name in files:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(directory, name), encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module)
                    # "from x import y" may name a module as well as a value.
                    names.update(f"{node.module}.{alias.name}" for alias in node.names)
    ours = ("personal_finance", "tests")
    return sorted(
        name for name in names if name.split(".")[0] not in ours and installed(name)
    )


parts = PYTEST + [name for name in OPTIONAL if installed(name)]

hiddenimports = collect_submodules("personal_finance")
for name in parts:
    hiddenimports += collect_submodules(name)
# Imported inside functions, and only on Windows.
hiddenimports += ["winreg", "msvcrt"]
hiddenimports += imported_by_tests()

# The tests go in as real files, since pytest collects them from disk. Cached
# bytecode is left behind: it belongs to the machine that made it.
datas = []
for directory, subdirectories, files in os.walk(TESTS):
    subdirectories[:] = [d for d in subdirectories if d != "__pycache__"]
    for name in files:
        if not name.endswith(".pyc"):
            datas.append(
                (os.path.join(directory, name), os.path.relpath(directory, ROOT))
            )
# The project file beside them is how the program knows they are its own.
datas.append((os.path.join(ROOT, "pyproject.toml"), "."))
# pytest and its helpers read their versions from their installed metadata.
for name in parts:
    if name not in ("_pytest",):
        datas += copy_metadata(name)

a = Analysis(
    [os.path.join(SPECPATH, "financat.py")],  # noqa: F821 - provided by PyInstaller
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    # The program's own source goes in beside its compiled form: some tests
    # read it, and a crash report can then show the lines it happened on.
    module_collection_mode={"personal_finance": "pyz+py"},
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="financat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Left off: compressed executables are flagged by antivirus far more often.
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
