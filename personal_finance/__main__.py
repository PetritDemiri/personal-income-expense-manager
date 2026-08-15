"""Allows `python -m personal_finance`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
