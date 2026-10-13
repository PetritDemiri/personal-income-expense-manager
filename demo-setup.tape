# Recording of the first run: how an empty database is claimed.
#
#     vhs demo-setup.tape        (from the project folder)
#
# Produces demo-setup.gif.
#
# A recording types fixed keystrokes and the generated password is different
# every time. A code lives only while the program that showed it is open, so it
# cannot be arranged beforehand; instead `financat` is defined, off camera, to
# run demo_setup.py, which runs the program itself with a known password.
# Nothing else about the program changes: it writes the file, checks the
# password, counts the three attempts and expires the code exactly as it always
# does.
#
# The two password fields near the end show nothing as they are typed. That is
# `getpass` doing its job, and it is what anyone setting a password sees.

Output demo-setup.gif

Set FontSize 15
Set Width 1100
Set Height 720
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms

# --- Off camera: a scratch folder, and financat with a known password ---

Hide
# Two statements, not one: bash expands every word of a command before making
# any of its assignments, so `export A=$(mktemp -d) B=$A` leaves B empty.
Type "export FINANCE_DATA_DIR=$(mktemp -d)"
Enter
Sleep 500ms
# Everything the program writes goes to the scratch folder, and the tests that
# run on a first launch are switched off - they are not what this recording is
# of. Naming the data folder also keeps the program from copying a finance.db
# it finds in this folder, which in a working copy may well be a real one.
Type "export FINANCE_EXPORT_DIR=$FINANCE_DATA_DIR FINANCE_HOME=$FINANCE_DATA_DIR FINANCE_SKIP_TESTS=1"
Enter
Sleep 500ms
Type "financat() { python3 demo_setup.py; }"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 1s
Show

# --- The recording ---

# An empty database hands out credentials rather than letting whoever runs the
# program own it.
Type "financat"
Enter
Sleep 4s

# The password is read from the file the program just wrote. Typed into boxes
# that fill as they go, and the last one submits on its own.
Type "HJ7KQ2M4XRTP"
Sleep 3s

# Then the administrator chooses their own name and password. The two password
# fields show nothing, which is what setting a password looks like.
Type "Petrit"
Enter
Sleep 1s
Type "Fjalekalimi1"
Enter
Sleep 1s
Type "Fjalekalimi1"
Enter
Sleep 4s

# Signed in, and the generated credentials are gone: the file is deleted and
# the password that was in it no longer works.
Type "21"
Enter
Sleep 3s
