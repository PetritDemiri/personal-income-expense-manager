# Demo recording script for the README GIF.
#
# Requires VHS: https://github.com/charmbracelet/vhs
#   brew install vhs                                    (macOS)
#   go install github.com/charmbracelet/vhs@latest      (anywhere with Go)
#
# On Windows, run this under WSL. The tape uses a POSIX shell for the
# scratch directory and the date helper, and ttyd is awkward to install
# natively.
#
# Then run:  vhs demo.tape
# Produces:  demo.gif
#
# Runs against a throwaway data directory, so the real database is never
# touched and no real transaction appears on camera.
#
# Dates are generated from the current month rather than hardcoded, so the
# monthly report and the budget bar show real figures whenever this is
# recorded rather than an empty month.

Output demo.gif

Set FontSize 15
Set Width 1150
Set Height 760
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms

# --- Seed a scratch database, off camera ---

Hide
Type "export FINANCE_DATA_DIR=$(mktemp -d) && clear"
Enter
Sleep 500ms

Type "financat --shto-llogari 'Banka' Banke 850 > /dev/null"
Enter
Type "financat --shto-llogari 'Kesh' Kesh 40 > /dev/null"
Enter

Type "financat --shto-te-ardhura --pershkrimi 'Paga e korrikut' --shuma 1200 --data $(date +01-%m-%Y) --kategoria Paga --llogaria Banka > /dev/null"
Enter
Type "financat --shto-shpenzime --pershkrimi 'Qera e banesës' --shuma 300 --data $(date +02-%m-%Y) --kategoria Qera --llogaria Banka > /dev/null"
Enter
Type "financat --transfero Banka Kesh --shuma 200 --pershkrimi 'Terheqje ne ATM' --data $(date +05-%m-%Y) > /dev/null"
Enter
Type "financat --shto-shpenzime --pershkrimi 'Ushqime nga dyqani' --shuma 185.40 --data $(date +10-%m-%Y) --kategoria Ushqim --nenkategoria Dyqan --llogaria Kesh > /dev/null"
Enter
Type "financat --cakto-buxhet Ushqim 200 > /dev/null && clear"
Enter
Sleep 500ms
Show

# --- The demo ---

# Transactions, with the account and subcategory columns appearing only
# because something uses them.
Type "financat --lista"
Enter
Sleep 4s

# Summary, category breakdown, and per-account balances. The transfer is
# counted as neither income nor spending.
Type "financat --gjendja"
Enter
Sleep 5s

# Monthly report with a per-category breakdown.
Type "financat --raporti"
Enter
Sleep 4s

# Budget usage, warning as the limit approaches.
Type "financat --buxhetet"
Enter
Sleep 3s

# Every change to financial data is recorded.
Type "financat --historia"
Enter
Sleep 4s

# The same data in English. Stored values stay Albanian; only labels change.
Type "financat --gjuha en --balance"
Enter
Sleep 4s
