"""Run the program for the first-run recording, with a password known in advance.

The setup screen is worth showing: it is the most distinctive thing the program
does, and the boxes filling as a code is typed only make sense on camera. But a
recording types fixed keystrokes, and the generated password is different every
time, so the two cannot meet without arranging it.

A first-run code lives only while the program that showed it is open, so it
cannot be written into the database beforehand - the program would discard it
on opening. Instead this runs the program itself, with the one function that
draws the password replaced. Nothing else about how it behaves changes: it
writes the file, checks the password, counts the attempts and expires the code
exactly as it always would. The only difference is that the recording knows
what to type.

Used by demo-setup.tape, through a shell function named financat, so the
recording shows the command a person would type. Not part of the program.
"""

import sys

from personal_finance import auth
from personal_finance.cli import main

# Drawn from the same alphabet as every generated password, so it looks like
# any other one the program hands out.
PASSWORD = "HJ7KQ2M4XRTP"


def run_with_known_password(argv=None):
    auth.generate_setup_password = lambda: PASSWORD
    return main(argv)


if __name__ == "__main__":
    sys.exit(run_with_known_password())
