"""The text of a release page: how to get the .exe, then the version's own
entry from CHANGELOG.md.

    python .github/release_notes.py notes.md v3.12.0

Without a tag it writes the notes for the program's own version, which is what
a build started by hand does. With one, it refuses a tag that is not the
program's version, so a release can never carry an .exe that calls itself
something else.
"""

import re
import sys
from pathlib import Path

from personal_finance import __version__

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

DOWNLOAD = """\
**Windows:** download `financat.exe` below. Nothing else needs installing. The
first time it opens, it runs its own tests on screen, which usually takes one
to five minutes. It is not signed, so Windows may say it protected your PC:
choose *More info*, then *Run anyway*.
"""


def entry(changelog, version):
    """One version's entry, without its heading, or None if it has none."""
    found = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    return found.group(1).strip() if found else None


def unwrapped(text):
    """Each paragraph and list item on a line of its own. A release page keeps
    every line break it is given, where a file in the repository does not."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        previous = lines[-1].strip() if lines else ""
        joins = previous and not previous.startswith("#") and stripped
        if joins and not stripped.startswith(("- ", "#")):
            lines[-1] += " " + stripped
        else:
            lines.append(line.rstrip())
    return "\n".join(lines)


def main(arguments):
    if not 1 <= len(arguments) <= 2:
        sys.exit("usage: release_notes.py OUTPUT [TAG]")
    output = Path(arguments[0])
    tag = arguments[1] if len(arguments) == 2 else f"v{__version__}"
    if tag != f"v{__version__}":
        sys.exit(f"The tag {tag} is not the program's version, which is {__version__}.")
    text = entry(CHANGELOG.read_text(encoding="utf-8"), __version__)
    if text is None:
        sys.exit(f"CHANGELOG.md has no entry for {__version__}.")
    output.write_text(unwrapped(f"{DOWNLOAD}\n{text}") + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
