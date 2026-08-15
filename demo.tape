# Demo recording script for the README GIF.
#
# Requires VHS: https://github.com/charmbracelet/vhs
#   brew install vhs      (macOS)
#   go install github.com/charmbracelet/vhs@latest
#
# Then run:  vhs demo.tape
# Produces:  demo.gif
#
# Runs against a throwaway data directory so your real transactions.csv is
# never touched or shown on camera.

Output demo.gif

Set FontSize 15
Set Width 1100
Set Height 700
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms

# Use a scratch data directory, seeded with a few sample transactions.
Hide
Type "export FINANCE_DATA_DIR=$(mktemp -d) && clear"
Enter
Sleep 500ms
Type "financat --shto-te-ardhura --pershkrimi 'Paga e korrikut' --shuma 1200 --data 01-07-2026 --kategoria Paga > /dev/null"
Enter
Type "financat --shto-shpenzime --pershkrimi 'Qera e banesës' --shuma 300 --data 02-07-2026 --kategoria Qera > /dev/null"
Enter
Type "financat --shto-shpenzime --pershkrimi 'Ushqime nga dyqani' --shuma 185.40 --data 10-07-2026 --kategoria Ushqim > /dev/null"
Enter
Type "financat --cakto-buxhet Ushqim 200 > /dev/null && clear"
Enter
Sleep 500ms
Show

# --- The actual demo ---

Type "financat --lista"
Enter
Sleep 3s

Type "financat --gjendja"
Enter
Sleep 3s

Type "financat --raporti --muaji 07-2026"
Enter
Sleep 3s

Type "financat --buxhetet"
Enter
Sleep 3s

Type "financat --lista --nga 01-07-2026 --deri 05-07-2026"
Enter
Sleep 3s

Type "financat --gjuha en --gjendja"
Enter
Sleep 3s
