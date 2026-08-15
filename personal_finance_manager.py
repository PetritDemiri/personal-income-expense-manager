#!/usr/bin/env python3
"""Backward-compatible entry point.

The application now lives in the `personal_finance` package. This shim keeps
`python3 personal_finance_manager.py` working exactly as before, so existing
scripts, aliases, and habits do not break.
"""

import sys

from personal_finance.cli import main

if __name__ == "__main__":
    sys.exit(main())
