"""Where financat.exe starts.

The .exe cannot start the way `python -m personal_finance` does, so it starts
here. It does one more thing than that: the first-launch tests run in a process
of their own, and the .exe has no Python to start that process with - so it
starts itself, with --run-bundled-tests, and runs pytest inside.

Built into the .exe by financat.spec, beside this file.
"""

import sys

from personal_finance import selftest
from personal_finance.cli import main

if __name__ == "__main__":
    if sys.argv[1:2] == [selftest.TEST_MODE]:
        sys.exit(selftest.run_inside(sys.argv[2:]))
    sys.exit(main())
