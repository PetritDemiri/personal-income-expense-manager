# Personal Finance Manager

[![CI](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A command-line personal income and expense manager, with an Albanian interface and an English option. No runtime dependencies — standard library only.

<!-- Record with `vhs demo.tape` and commit the result, then uncomment: -->
<!-- ![Demo](demo.gif) -->

## Features

- **Transactions** — add, edit in place, and delete income and expense entries
- **Categories and subcategories** — pick from suggestions or type your own; anything you've used before is suggested automatically, sorted in Albanian alphabetical order (digraphs included) with the catch-all always last
- **Accounts** — optional cash, bank, and card accounts with opening balances, per-account and combined totals, and transfers between them
- **Budgets** — monthly spending limits per category, with a warning at the moment you overspend
- **Monthly reports** — totals, per-category breakdown, and month-over-month comparison
- **Date filtering** — a single date or an inclusive range, with totals for the filtered set
- **Search** — match on description, category, or subcategory
- **CSV export** — write transactions to a spreadsheet-ready file, with any filter applied
- **Recurring transactions** — weekly, monthly, or yearly, generated automatically when due
- **Colored output** — income green, expenses red, with automatic fallback for terminals that don't support it
- **Two languages** — Albanian by default, English via `--gjuha en`; stored data is identical either way
- **Command-line flags** — Albanian primary, English aliases, with the interactive menu as the default
- **Exact money** — `Decimal` throughout, so totals never drift from floating-point rounding
- **SQLite storage** — transactional writes, indexed date queries, and automatic schema migrations; CSV remains available via `--csv`
- **Crash-safe saves** — a save that touches more than one table lands completely or not at all

## Install

```bash
git clone https://github.com/PetritDemiri/personal-income-expense-manager.git
cd REPO
pip install -e .
```

This provides a `financat` command. To run without installing:

```bash
python3 -m personal_finance
# or, unchanged from earlier versions:
python3 personal_finance_manager.py
```

## Usage

Running with no flags opens the interactive menu:

```bash
financat
```

| Option | Albanian | English |
|---|---|---|
| 1 | Shtoni Te Ardhurat | Add income |
| 2 | Shtoni Shpenzimet | Add an expense |
| 3 | Shiko Te Gjitha Transaksionet | View all transactions |
| 4 | Shiko Gjendjen Aktuale | View current balance |
| 5 | Ndrysho nje Transaksion | Edit a transaction |
| 6 | Fshi nje Transaksion | Delete a transaction |
| 7 | Filtro sipas Dates | Filter by date |
| 8 | Kerko Transaksione | Search transactions |
| 9 | Raporti Mujor | Monthly report |
| 10 | Buxhetet | Budgets |
| 11 | Transaksionet e Perseritura | Recurring transactions |
| 12 | Dil nga programi | Exit |

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
| `--llogarite` | `--accounts` | Show per-account balances |
| `--shto-llogari` | `--add-account` | Add an account: `EMRI LLOJI GJENDJA` |
| `--transfero` | `--transfer` | Transfer between accounts: `NGA TEK`, with `--shuma` |
| `--cakto-pa-llogari` | `--assign-unassigned` | Assign account-less records to an account |
| `--cakto-buxhet` | `--set-budget` | Set a monthly budget: `KATEGORIA SHUMA` |
| `--shto-te-ardhura` | `--add-income` | Add an income transaction |
| `--shto-shpenzime` | `--add-expense` | Add an expense transaction |
| `--perserit` | `--recurring` | Generate any due recurring transactions |
| `--perseritjet` | `--list-recurring` | List recurring rules |
| `--kerko` | `--search` | Search descriptions and categories |
| `--eksporto` | `--export` | Export transactions to a CSV file |
| `--ndares` | `--delimiter` | Column delimiter for export (default `,`) |
| `--pershkrimi` | `--description` | Description for a new transaction |
| `--shuma` | `--amount` | Amount for a new transaction |
| `--data` | `--date` | Date (`dd-mm-yyyy`) |
| `--kategoria` | `--category` | Category for a new transaction |
| `--llogaria` | `--account` | Account for a new transaction, or filter by account |
| `--nenkategoria` | `--subcategory` | Subcategory for a new transaction (optional) |
| `--nga` | `--from` | Filter start date (inclusive) |
| `--deri` | `--to` | Filter end date (inclusive) |
| `--muaji` | `--month` | Month for the report (`mm-yyyy`) |
| `--gjuha` | `--language` | Interface language: `sq` (default) or `en` |
| `--pa-ngjyra` | `--no-color` | Disable colored output |
| `--csv` | — | Use CSV files instead of the database |
| `--baza` | `--database` | Path to the database file |

`--data` works by context: with `--lista` it filters to a single date; with `--shto-*` it sets the new transaction's date. Any field omitted when adding is prompted for interactively.

```bash
financat --lista --nga 01-08-2026 --deri 31-08-2026
financat --shto-shpenzime --pershkrimi "Qera" --shuma 300 --kategoria Qera
financat --shto-shpenzime --pershkrimi "Buke" --shuma 1.20 --kategoria Ushqim --nenkategoria Dyqan
financat --cakto-buxhet Ushqim 200
financat --raporti --muaji 07-2026
financat --kerko dyqani
financat --gjuha en --balance
```

## How it works

### Categories and subcategories

Every transaction has a category; a subcategory is optional. Suggestions come from a built-in list plus anything you've used before, and the catch-all (`Te tjera`) is always kept at the end of the list no matter how many categories you add of your own.

Everything else is sorted in **Albanian alphabetical order**, so a category you type takes its natural place in the list rather than landing wherever you happened to add it. The ordering follows the full 36-letter alphabet, including its nine digraphs:

```
a b c ç d dh e ë f g gj h i j k l ll m n nj o p q r rr s sh t th u v x xh y z zh
```

Each digraph is a letter in its own right, so every word beginning with S comes before every word beginning with Sh — `Sende`, `Sy`, then `Shendetesi`. Accented letters sort in place too: `Çaji` after `Cak`, `Ëmbëlsira` between `Etje` and `Fatura`. Sorting by Unicode code point, which is what most languages do by default, gets both of these wrong: it interleaves the S and Sh words and pushes every accented word past Z.

Runs of digits compare as numbers, so `Muaji 9` comes before `Muaji 10`. Latin letters absent from Albanian are placed where a reader would expect rather than at the end — only `w` is missing, and it sits between `v` and `x` — so English category names sort correctly as well.

Subcategories appear as a table column only when something actually uses them, so the listing stays narrow if you don't need them. Summaries and reports nest subcategory totals under their category, and search matches on subcategories too.

When adding, press Enter at the subcategory prompt to skip it. When editing, Enter keeps the current value and a lone `-` clears it. Changing a transaction's category asks for the subcategory fresh, since the old one no longer applies.

### Accounts

Accounts are optional and off until you create one. With none defined the program behaves exactly as before: no account prompt, no account column, one combined balance.

An account is somewhere money sits — cash, a bank account, a card — and carries an **opening balance**, because an account that already held €500 when you started tracking does not have a balance of zero. Card accounts can open negative.

Money moved between your own accounts is a **transfer**, not an expense. Recording an ATM withdrawal as an expense would make your combined total drop by money you still have; recording nothing would leave the bank too high and the cash too low. A transfer is a transaction type of its own, shown in cyan rather than green or red, and counted as neither income nor spending. Filtering by either account shows it, since it touches both.

Deleting an account leaves its transactions behind as unassigned — the spending still happened. Renaming one repoints every transaction and recurring rule that referenced it, in a single database transaction.

Transactions recorded before you created any account show up as an unnumbered `-` row: they are real money, just not tied to anywhere. `--cakto-pa-llogari EMRI` moves all of them onto one account in a single step, recurring rules included, so future occurrences land there too. Balances are unaffected — the money was already counted.

### Budgets

A budget is a monthly limit for one expense category, and it covers every subcategory beneath it — a `Ushqim` budget counts `Dyqan` and `Restorant` spending together. Adding an expense that pushes a category to 80% of its limit prints a warning; going over prints how far over. The budget view shows spent, limit, remaining, and a usage bar, worst first.

### Recurring transactions

Rules live in `recurring.csv` and support `javore` (weekly), `mujore` (monthly), and `vjetore` (yearly). Due occurrences generate automatically at start-up, or on demand via the menu or `--perserit`.

Each rule records the last date it generated, so an occurrence is never created twice. Every occurrence is computed from the rule's start date rather than from the previous one — so a rule anchored on the 31st fires 31 January, 28 February, then **31** March. A short month never shifts the schedule permanently.

### CSV export

`--eksporto SKEDARI` writes the selected transactions to a CSV file. Every listing filter applies, so the same flags that narrow a listing narrow an export:

```bash
financat --eksporto gushti.csv --nga 01-08-2026 --deri 31-08-2026
financat --eksporto ushqim.csv --kerko Ushqim
financat --eksporto banka.csv --llogaria Banka
```

The file is written for a spreadsheet rather than for this program. Column headers follow the interface language; amounts are plain decimals with no currency symbol so they parse as numbers; empty fields are blank cells rather than the labels shown on screen. It is written as UTF-8 with a byte order mark, without which Excel mangles every `ë` and `ç`. Use `--ndares ";"` if your spreadsheet expects semicolons, as locales that use a comma for decimals generally do.

Export is one-directional. It is not a storage backend and never reads.

### Colors

Income is green, expenses red, headers cyan, warnings yellow. Colors switch off automatically when output is piped or redirected, when `NO_COLOR` is set, or when the terminal reports no support — and can be disabled explicitly with `--pa-ngjyra`.

## Project layout

```
personal_finance/
    config.py      Settings and canonical values
    i18n.py        Message catalogs (sq, en)
    dates.py       Parsing, formatting, month arithmetic
    models.py      Transaction, RecurringRule, Budget
    storage.py     Storage interface + atomic CSV backend
    recurring.py   Recurrence scheduling
    reports.py     Totals, filtering, monthly reports
    budgets.py     Budget status calculations
    collation.py   Albanian alphabetical ordering
    accounts.py    Per-account balances and transfers
    colors.py      ANSI handling and terminal detection
    display.py     Table and summary rendering
    app.py         Service layer tying it together
    ui.py          Interactive prompts and menus
    cli.py         argparse entry point
tests/             pytest suite
```

Two design points worth knowing:

**Storage is an interface.** Everything above `storage.py` talks to a `Storage` object and never touches a file. Swapping CSV for SQLite means writing one class — the UI, reports, and CLI don't change.

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

The tape runs against a temporary data directory, so your real data never appears in the recording. Commit the resulting `demo.gif` and uncomment the image line near the top of this file.

## Data storage

Data lives in a SQLite database, `finance.db`, in the working directory (override the directory with `FINANCE_DATA_DIR`, or the file itself with `--baza`).

Money is stored as an integer number of cents rather than a float, so amounts stay exact. Dates are stored ISO-formatted so they sort and index properly, and are converted back to `dd-mm-yyyy` for display. The schema carries a version number, and migrations run automatically on open — adding a column later is a numbered migration step, not a rewrite.

### Why a database

Two separate CSV files cannot be written atomically. Generating recurring transactions writes both the transactions and the updated rules; a crash between those two writes left the transactions on disk while the rules still believed nothing had been generated, so the next run created them all a second time. In the database both tables commit together or neither does.

### CSV mode

Passing `--csv` uses the original three-file layout instead:

| File | Columns |
|---|---|
| `transactions.csv` | `lloji`, `pershkrimi`, `shuma`, `data`, `kategoria`, `nenkategoria`, `llogaria`, `llogaria_dest` |
| `recurring.csv` | `lloji`, `pershkrimi`, `shuma`, `kategoria`, `nenkategoria`, `frekuenca`, `data_fillimit`, `data_e_fundit` |
| `budgets.csv` | `kategoria`, `shuma` |
| `accounts.csv` | `emri`, `lloji`, `gjendja_fillestare` |

All three are gitignored — they hold personal financial data. Corrupted rows are skipped individually with a warning rather than discarding the rest of the file.

### Migration from earlier versions

On first run, if a database does not exist yet and CSV files do, their contents are imported automatically and announced. **The CSV files are left untouched**, so the move is reversible — `--csv` goes straight back to them. The import only ever runs against a brand-new, empty database, so it cannot run twice or overwrite anything.

Older CSV files load with no manual conversion:

- **Four-column files** (before categories) load fine and are shown as `Pa kategori`.
- **Files without `nenkategoria`** (before subcategories) load fine with no subcategory set.
- **English type values** (`income` / `expense`) are translated to `Te Ardhura` / `Shpenzime` on load, as are lowercase Albanian variants.
- **`budgets.csv`** is new and created on demand; nothing breaks if it doesn't exist.
- **Databases at schema version 1** are migrated to version 2 automatically on open, adding the accounts table and the account columns. Existing transactions become unassigned, which is what they are.

Files are rewritten in the current format the next time they're saved.

## License

MIT — see [LICENSE](LICENSE).
