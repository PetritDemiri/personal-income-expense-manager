# Personal Finance Manager

A command-line app for tracking personal income and expenses, with transactions saved to local CSV files. The interface is in Albanian.

## Features

- Add income and expense transactions with description, amount, date, and category
- Categorize every transaction — pick from suggested categories or type your own
- Edit any transaction in place, field by field
- Delete a transaction by its number
- View totals broken down per category
- Filter transactions by a single date or an inclusive date range, with totals for the filtered set
- Recurring transactions (weekly, monthly, yearly) generated automatically when they come due
- Color-coded output — income in green, expenses in red — with automatic fallback for terminals that don't support it
- Command-line flags for scripting, with the interactive menu as the default
- Amounts use `Decimal` for accurate totals (no floating-point rounding drift)

## Requirements

- Python 3.6+
- No external dependencies — standard library only

## Getting started

Clone the repository, then run:

```bash
python3 personal_finance_manager.py
```

## Interactive menu

| Option | Albanian | English |
|---|---|---|
| 1 | Shtoni Te Ardhurat | Add income |
| 2 | Shtoni Shpenzimet | Add an expense |
| 3 | Shiko Te Gjitha Transaksionet | View all transactions |
| 4 | Shiko Gjendjen Aktuale | View current balance |
| 5 | Ndrysho nje Transaksion | Edit a transaction |
| 6 | Fshi nje Transaksion | Delete a transaction |
| 7 | Filtro sipas Dates | Filter by date |
| 8 | Transaksionet e Perseritura | Manage recurring transactions |
| 9 | Dil nga programi | Exit |

Enter a number 1-9 and follow the prompts. Dates default to today, or you can enter a custom date in `dd-mm-yyyy` format.

### Editing

When editing, each prompt shows the current value in brackets. Press Enter to keep it and move on, so a single field can be corrected without retyping the rest. Input is validated exactly as it is when adding a transaction.

### Categories

Adding a transaction offers a numbered list of suggested categories for that type — `Paga`, `Bonus`, `Dhurate` and so on for income; `Ushqim`, `Qera`, `Transport` and so on for expenses. Pick a number, or type any category you like. Categories already used in your data are added to the suggestions automatically. Transactions with no category are shown as `Pa kategori`.

### Date filtering

Option 7 filters by a single date or between two dates (both bounds inclusive). Either way, the matching transactions are shown along with their own income, expense, and balance totals. Numbers in a filtered view still refer to positions in the full list, so they can be used directly to edit or delete.

### Recurring transactions

Recurring rules are stored separately in `recurring.csv` and support `javore` (weekly), `mujore` (monthly), and `vjetore` (yearly) frequencies. Due occurrences are generated automatically when the program starts, or on demand from menu option 8 or the `--perserit` flag.

Each rule records the last date it generated, so an occurrence is never created twice no matter how often the program runs. Every occurrence is calculated from the rule's start date rather than from the previous occurrence, so a rule anchored on the 31st fires on 31 January, 28 February, then 31 March again — a short month never shifts the schedule permanently.

## Command-line flags

Running with no flags opens the interactive menu. Albanian flags are primary; English aliases are accepted for all of them.

| Flag | Alias | Description |
|---|---|---|
| `--ndihma` | `-h`, `--help` | Show help and exit |
| `--lista` | `--list` | List transactions (optionally filtered) |
| `--gjendja` | `--balance` | Show the financial summary |
| `--shto-te-ardhura` | `--add-income` | Add an income transaction |
| `--shto-shpenzime` | `--add-expense` | Add an expense transaction |
| `--perserit` | `--recurring` | Generate any due recurring transactions |
| `--pershkrimi` | `--description` | Description for a new transaction |
| `--shuma` | `--amount` | Amount for a new transaction |
| `--data` | `--date` | Date (`dd-mm-yyyy`) |
| `--kategoria` | `--category` | Category for a new transaction |
| `--nga` | `--from` | Filter start date (inclusive) |
| `--deri` | `--to` | Filter end date (inclusive) |
| `--pa-ngjyra` | `--no-color` | Disable colored output |

`--data` works by context: with `--lista` it filters to a single date, and with `--shto-te-ardhura` or `--shto-shpenzime` it sets the date of the new transaction.

Any field left out when adding a transaction is prompted for interactively, so flags can be used to fill in as much or as little as you like.

### Examples

```bash
# List everything
python3 personal_finance_manager.py --lista

# List one day, and a range
python3 personal_finance_manager.py --lista --data 05-08-2026
python3 personal_finance_manager.py --lista --nga 01-08-2026 --deri 31-08-2026

# Add an expense without entering the menu
python3 personal_finance_manager.py --shto-shpenzime --pershkrimi "Qera" --shuma 300 --kategoria Qera

# Show the balance with no colors
python3 personal_finance_manager.py --gjendja --pa-ngjyra
```

## Colors

Output is color-coded for readability: income in green, expenses in red, headers in cyan, and warnings in yellow. Colors are disabled automatically when output is piped or redirected to a file, when the `NO_COLOR` environment variable is set, or when the terminal reports no color support. They can also be turned off explicitly with `--pa-ngjyra`.

## Data storage

Two CSV files are created in the working directory:

**`transactions.csv`** — one row per transaction, with columns `lloji` (type), `pershkrimi` (description), `shuma` (amount), `data` (date), and `kategoria` (category).

**`recurring.csv`** — one row per recurring rule, with columns `lloji`, `pershkrimi`, `shuma`, `kategoria`, `frekuenca` (frequency), `data_fillimit` (start date), and `data_e_fundit` (last generated date).

Both files are created automatically on first use and are excluded from version control (see `.gitignore`), since they hold personal financial data.

Corrupted rows are skipped individually with a warning rather than discarding the rest of the file.

### Migration from earlier versions

The `kategoria` column was added as the fifth column of `transactions.csv`, so files written by earlier versions load without any manual conversion — existing rows are read normally and shown as `Pa kategori`. The file is rewritten in the new format the next time it is saved.

`recurring.csv` is new and is created on demand; nothing breaks if it doesn't exist.

## License

Licensed under the MIT License — see [LICENSE](LICENSE) for details.
