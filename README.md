# Personal Finance Manager

[![CI](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A command-line personal income and expense manager, with an Albanian interface and an English option. Data lives in SQLite. No runtime dependencies — standard library only.

<!-- Record with `vhs demo.tape` and commit the result, then uncomment: -->
<!-- ![Demo](demo.gif) -->

## Features

- **Transactions** — add, edit in place, and delete income and expense entries
- **Categories and subcategories** — stored as real records with foreign keys, created on first use, sorted in Albanian alphabetical order with the catch-all last
- **Accounts** — optional cash, bank, and card accounts with opening balances, per-account and combined totals, and transfers between them
- **Budgets** — monthly spending limits per category, warning at the moment you overspend
- **Monthly reports** — totals, per-category breakdown, and month-over-month comparison
- **Date filtering and search** — pushed into SQL rather than looped over in Python
- **Recurring transactions** — weekly, monthly, or yearly, generated atomically when due
- **CSV export** — write transactions to a spreadsheet-ready file, with any filter applied
- **Colored output** — income green, expenses red, transfers cyan, with automatic fallback
- **Two languages** — Albanian by default, English via `--gjuha en`; stored data is identical either way
- **Exact money** — integer cents in the database, `Decimal` in the program, never a float

## Install

```bash
git clone https://github.com/PetritDemiri/personal-income-expense-manager.git
cd personal-income-expense-manager
pip install -e .
```

This provides a `financat` command. To run without installing:

```bash
python3 -m personal_finance
# or, unchanged since version 1:
python3 personal_finance_manager.py
```

## Usage

Running with no flags opens the interactive menu:

| Option | Albanian | English |
|---|---|---|
| 1 | Shtoni Te Ardhurat | Add Income |
| 2 | Shtoni Shpenzimet | Add an Expense |
| 3 | Shiko Te Gjitha Transaksionet | View All Transactions |
| 4 | Shiko Gjendjen Aktuale | View Current Balance |
| 5 | Ndrysho nje Transaksion | Edit a Transaction |
| 6 | Fshi nje Transaksion | Delete a Transaction |
| 7 | Filtro sipas Dates | Filter by Date |
| 8 | Kerko Transaksione | Search Transactions |
| 9 | Raporti Mujor | Monthly Report |
| 10 | Kategorite | Categories |
| 11 | Buxhetet | Budgets |
| 12 | Llogarite | Accounts |
| 13 | Transfero mes Llogarive | Transfer Between Accounts |
| 14 | Transaksionet e Perseritura | Recurring Transactions |
| 15 | Eksporto ne CSV | Export to CSV |
| 16 | Dil nga programi | Exit |

Dates use `dd-mm-yyyy`. When editing, each prompt shows the current value in brackets — press Enter to keep it.

### Command-line flags

Albanian flags are primary; English aliases work for all of them.

| Flag | Alias | Description |
|---|---|---|
| `--ndihma` | `-h`, `--help` | Show help and exit |
| `--lista` | `--list` | List transactions (optionally filtered) |
| `--gjendja` | `--balance` | Show the financial summary |
| `--raporti` | `--report` | Monthly report |
| `--buxhetet` | `--budgets` | Show budgets |
| `--cakto-buxhet` | `--set-budget` | Set a monthly budget: `KATEGORIA SHUMA` |
| `--llogarite` | `--accounts` | Show per-account balances |
| `--shto-llogari` | `--add-account` | Add an account: `EMRI LLOJI GJENDJA` |
| `--transfero` | `--transfer` | Transfer between accounts: `NGA TEK`, with `--shuma` |
| `--cakto-pa-llogari` | `--assign-unassigned` | Assign account-less records to an account |
| `--shto-te-ardhura` | `--add-income` | Add an income transaction |
| `--shto-shpenzime` | `--add-expense` | Add an expense transaction |
| `--perserit` | `--recurring` | Generate any due recurring transactions |
| `--perseritjet` | `--list-recurring` | List recurring rules |
| `--kerko` | `--search` | Search descriptions, categories, and subcategories |
| `--eksporto` | `--export` | Export transactions to a CSV file |
| `--pershkrimi` | `--description` | Description for a new transaction |
| `--shuma` | `--amount` | Amount for a new transaction |
| `--data` | `--date` | Date (`dd-mm-yyyy`) |
| `--kategoria` | `--category` | Category for a new transaction |
| `--nenkategoria` | `--subcategory` | Subcategory (optional) |
| `--llogaria` | `--account` | Account for a new transaction, or filter by account |
| `--nga` | `--from` | Filter start date (inclusive) |
| `--deri` | `--to` | Filter end date (inclusive) |
| `--muaji` | `--month` | Month for the report (`mm-yyyy`) |
| `--baza` | `--database` | Path to the database file |
| `--gjuha` | `--language` | Interface language: `sq` (default) or `en` |
| `--ndares` | `--delimiter` | Column delimiter for export (default `,`) |
| `--pa-ngjyra` | `--no-color` | Disable colored output |

`--data` works by context: with `--lista` it filters to a single date; with `--shto-*` it sets the new transaction's date. Any field omitted when adding is prompted for interactively.

```bash
financat --lista --nga 01-08-2026 --deri 31-08-2026
financat --shto-shpenzime --pershkrimi "Qera" --shuma 300 --kategoria Qera
financat --shto-llogari "Banka" Banke 850
financat --transfero Banka Kesh --shuma 200
financat --eksporto transaksionet.csv
financat --gjuha en --balance
```

## How it works

### Storage

Everything lives in one SQLite database, `finance.db`, created on first run. Override the directory with `FINANCE_DATA_DIR` or the file itself with `--baza`.

Money is stored as an integer count of cents rather than a float, so amounts stay exact. Dates are stored ISO-formatted so they sort and range-query correctly, and are converted to `dd-mm-yyyy` for display. Every named thing carries a normalised copy of its name for uniqueness, because SQLite's own case-insensitive collation folds only A–Z and would accept `Ë` and `ë` as different letters.

Foreign keys are enforced. Deleting an account or a category does not delete what referenced it — the spending still happened, only the label is gone — so those become `NULL`. A subcategory has no meaning without its parent, and a budget is a limit on a category, so both cascade.

Two constraints are deliberately absent: there is no maximum amount, since any ceiling is arbitrary and would not catch a digit too many; and there is no check on an account's kind or a rule's frequency, since those lists are likely to grow while income and expense are not.

### Categories and subcategories

Both are stored records, managed from menu option 10 — view, add, rename, and delete, for categories and subcategories alike. A name typed for the first time while adding a transaction is still created automatically, so entry never stalls on defining things up front.

Renaming is one row. Transactions reference a category by id, so the rename does not touch them. Deleting a category leaves its transactions uncategorised and takes its subcategories and any budget with it; the menu says how many transactions will be affected and asks before doing it.

Suggestions are sorted in **Albanian alphabetical order**, following the full 36-letter alphabet including its nine digraphs:

```
a b c ç d dh e ë f g gj h i j k l ll m n nj o p q r rr s sh t th u v x xh y z zh
```

Each digraph is a letter in its own right, so every word beginning with S comes before every word beginning with Sh — `Sende`, `Sy`, then `Shendetesi`. Sorting by Unicode code point, which is what most languages do by default, interleaves them and pushes every accented word past Z.

### Input rules

Input is validated strictly, because a value that is quietly accepted and quietly wrong is worse than a rejection.

**Amounts** are plain digits with an optional decimal point. Scientific notation, Python's underscore separators, and digits from other scripts are all rejected — `Decimal` accepts them, but nobody types them on purpose.

**Dates** must be exactly `dd-mm-yyyy`, and must be real: 31 April, 29 February in a common year, month 13 and day 00 are all refused.

**Yes and no** are exact lowercase, in the interface language only — `po`/`jo` in Albanian, `yes`/`no` in English. The input is compared exactly as typed, neither lowercased nor stripped, so `PO` and `" po "` are both refused.

**Cancelling** a prompt takes a whole word in the interface language — `anulo` in Albanian, `cancel` in English — compared exactly as typed. Every prompt that offers it names the word.

**Category and subcategory names** are letters with single spaces between words: `Ushqim`, `Te tjera`, `Paga baze`. No digits, no punctuation. Leading or trailing spaces, runs of spaces, and whitespace-only input are rejected rather than trimmed — a name the program quietly trimmed would not be the name you entered, and two names differing only by a space would look identical in a list. Pressing Enter still means "no category".

### Accounts

Accounts are optional and off until you create one. With none defined the program behaves as it always has: no account prompt, no account column, one combined balance.

An account carries an **opening balance**, because an account that already held €500 when you started tracking does not have a balance of zero. Card accounts can open negative.

Money moved between your own accounts is a **transfer**, not an expense. Recording an ATM withdrawal as spending would make your combined total drop by money you still have. A transfer is a transaction type of its own, shown in cyan, and counted as neither income nor spending.

### Recurring transactions

Rules support `javore` (weekly), `mujore` (monthly), and `vjetore` (yearly). Due occurrences generate automatically at start-up, or on demand.

Every occurrence is computed from the rule's start date rather than from the previous one, so a rule anchored on the 31st fires 31 January, 28 February, then **31** March. A short month never shifts the schedule permanently.

The transactions and the rule updates commit in a single database transaction, so a crash part-way through leaves nothing behind and the next run produces no duplicates.

### CSV export

`--eksporto SKEDARI` writes the selected transactions to a CSV file. Every listing filter applies.

A bare filename goes to your Documents folder rather than the current directory; anything with a directory in it is left alone. The full path is printed after the export. Finding Documents is not simply `~/Documents` — Windows relocates it and OneDrive commonly redirects it, so the path comes from the shell's registry record; Linux localizes the name, so it comes from the XDG user-dirs configuration.

The file is written as UTF-8 with a byte order mark, without which Excel mangles every `ë` and `ç`. Amounts are plain decimals with no currency symbol. Use `--ndares ";"` if your spreadsheet expects semicolons.

Export is one-directional. Reading a CSV is a separate feature, planned rather than present.

## Project layout

```
personal_finance/
    schema.py      The database schema, written out in full
    database.py    Row-level operations and SQL queries
    models.py      Account, Category, Transaction, and friends
    config.py      Settings and file locations
    i18n.py        Message catalogs (sq, en)
    collation.py   Albanian alphabetical ordering
    dates.py       Parsing, formatting, month arithmetic
    locations.py   Finding the user's Documents folder
    accounts.py    Per-account balances and transfers
    budgets.py     Budget status calculations
    recurring.py   Recurrence scheduling
    reports.py     Totals, filtering, monthly reports
    colors.py      ANSI handling and terminal detection
    display.py     Table and summary rendering
    export.py      CSV export
    app.py         Service layer tying it together
    ui.py          Interactive prompts and menus
    cli.py         argparse entry point
tests/             pytest suite
```

Two design points worth knowing:

**Reads return views, writes take models.** A view carries both the ids the database stores and the names a reader wants, resolved by the same join the query needs anyway. Reports and the display work on views; nothing above the database layer resolves an id by hand.

**Display is separate from data.** Stored transaction types stay Albanian regardless of interface language; only labels are translated. Switching language never rewrites your data.

## Development

```bash
pip install -e ".[dev]"

pytest                                              # run the tests
pytest --cov=personal_finance --cov-report=term-missing
ruff check . && ruff format --check .               # lint and format
```

Tests and lint run on every push via GitHub Actions, across Linux, macOS, and Windows.

### Recording the demo GIF

```bash
vhs demo.tape    # requires https://github.com/charmbracelet/vhs
```

The tape runs against a temporary data directory, so your real data never appears in the recording.

## Upgrading from version 2

Version 3 starts from an empty database. There is no automatic migration: the CSV backend and its file formats are gone, and so is the code that read them.

To carry data across, export it from version 2.4.1 first:

```bash
financat --eksporto transaksionet.csv
```

Keep that file. Reading a CSV back in is a planned feature; until it arrives, the export is a record you can read and re-enter.

## License

MIT — see [LICENSE](LICENSE).
