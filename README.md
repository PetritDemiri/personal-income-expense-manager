# Personal Finance Manager

[![CI](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A command-line personal income and expense manager, with an Albanian interface and an English option. Data lives in SQLite. No runtime dependencies — standard library only.

![Demo](demo.gif)

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
| 10 | Grafiket | Charts |
| 11 | Kategorite | Categories |
| 12 | Buxhetet | Budgets |
| 13 | Llogarite | Accounts |
| 14 | Transfero mes Llogarive | Transfer Between Accounts |
| 15 | Transaksionet e Perseritura | Recurring Transactions |
| 16 | Eksporto ne CSV | Export to CSV |
| 17 | Rregullat e Kategorive | Category Rules |
| 18 | Perdoruesit | Users |
| 19 | Importo nga nje skedar | Import from a file |
| 20 | Historiku i Ndryshimeve | Change History |
| 21 | Dil nga programi | Exit |

Dates use `dd-mm-yyyy`. When editing, each prompt shows the current value in brackets — press Enter to keep it.

### Command-line flags

Albanian flags are primary; English aliases work for all of them.

| Flag | Alias | Description |
|---|---|---|
| `--ndihma` | `-h`, `--help` | Show help and exit |
| `--lista` | `--list` | List transactions (optionally filtered) |
| `--gjendja` | `--balance` | Show the financial summary |
| `--raporti` | `--report` | Monthly report |
| `--grafiku` | `--chart` | Show charts; with 3, 6 or 12, the month-by-month one |
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
| `--historia` | `--history` | Show the change history, optionally for one transaction |
| `--importo` | `--import` | Import transactions from a file, with a preview |
| `--pershkrimi` | `--description` | Description for a new transaction |
| `--shuma` | `--amount` | Amount for a new transaction |
| `--data` | `--date` | Date (`dd-mm-yyyy`) |
| `--kategoria` | `--category` | Category for a new transaction |
| `--nenkategoria` | `--subcategory` | Subcategory (optional) |
| `--llogaria` | `--account` | Account for a new transaction, or filter by account |
| `--nga` | `--from` | Filter start date (inclusive) |
| `--deri` | `--to` | Filter end date (inclusive) |
| `--muaji` | `--month` | Month for the report (`mm-yyyy`) |
| `--perdoruesi` | `--user` | Which user to work as; defaults to the first |
| `--baza` | `--database` | Path to the database file |
| `--gjuha` | `--language` | Interface language: `sq` (default) or `en` |
| `--ndares` | `--delimiter` | Column delimiter for export (default `,`) |
| `--detaje` | `--details` | Show when each row was recorded and last changed |
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

### Users

One database can hold several people's finances, kept entirely separate. Every account, category, transaction, budget and rule belongs to exactly one person, and no query crosses between them.

Anyone who never creates a second user sees no change at all: a database always has one, everything belongs to them, and the interface never mentions it. `--perdoruesi EMRI` switches, and menu option 17 manages them.

Two people can both have an account called `Banka` and a category called `Ushqim`, which is why the uniqueness constraints are per-user rather than global.

**Passwords are stored but never asked for on the command line.** Whoever can run the program can also open the database file directly, so a prompt there would add friction without adding protection — the file's own permissions are the boundary. The hash exists so an account is ready for the web interface, where a password is the only thing between a stranger and someone's money.

They are hashed with PBKDF2-HMAC-SHA256, a random salt per password, and the iteration count stored alongside so it can be raised later without invalidating existing passwords. Argon2 would be the better algorithm and is what this would use in production; it needs a third-party package, and this project has had no runtime dependency since version 1.

Deleting a user deletes everything they own. There is no softer option: the data means nothing without them, and leaving it orphaned would be worse.

### Accounts

Accounts are optional and off until you create one. With none defined the program behaves as it always has: no account prompt, no account column, one combined balance.

An account carries an **opening balance**, because an account that already held €500 when you started tracking does not have a balance of zero. Card accounts can open negative.

Money moved between your own accounts is a **transfer**, not an expense. Recording an ATM withdrawal as spending would make your combined total drop by money you still have. A transfer is a transaction type of its own, shown in cyan, and counted as neither income nor spending.

### Categories and subcategories

Both are stored records, managed from menu option 10 — view, add, rename, and delete, for categories and subcategories alike. A name typed for the first time while adding a transaction is still created automatically, so entry never stalls on defining things up front.

Renaming is one row. Transactions reference a category by id, so the rename does not touch them. Deleting a category leaves its transactions uncategorised and takes its subcategories and any budget with it; the menu says how many transactions will be affected and asks before doing it.

Suggestions are sorted in **Albanian alphabetical order**, following the full 36-letter alphabet including its nine digraphs:

```
a b c ç d dh e ë f g gj h i j k l ll m n nj o p q r rr s sh t th u v x xh y z zh
```

Each digraph is a letter in its own right, so every word beginning with S comes before every word beginning with Sh — `Sende`, `Sy`, then `Shendetesi`. Sorting by Unicode code point, which is what most languages do by default, interleaves them and pushes every accented word past Z.

### Category rules

A rule is a piece of text and the category to apply when a description contains it. Menu option 16 manages them.

```
STEAMGAMES    ->  Argëtim / Lojëra
APPLE.COM     ->  Argëtim
Mirëmbajtje   ->  Tarifa bankare
```

Those are the sort of strings a bank statement actually contains — a merchant name as the card network abbreviates it, and the wording a bank uses for its own fees.

Matching is by substring, case-insensitive, folded the same way category names are — so a rule written `Mirëmbajtje` matches `MIRËMBAJTJE`. Not regular expressions: a wrong pattern here simply does nothing, while a wrong expression matches things nobody intended and is hard to spot in a preview.

**When two rules match, the longest pattern wins.** So `STEAM` and `STEAMGAMES.CO` can both exist, with the specific one beating the general one, and there is no order to maintain by hand.

Rules apply during the **import preview**, filling in the category on any row the file did not already categorise. Every row is still shown and can still be changed before anything is written. Transfers are left alone — moved money has no category.

When adding a transaction by hand, a matching rule is shown as a suggestion but **never filled in**. Pre-filling would let a rule written weeks ago decide the category on an unread Enter, and a single entry has no preview to catch that.

Before a rule is saved, the program says how many existing transactions it would match. A pattern matching three hundred rows is worth knowing about beforehand.

Deleting a category deletes its rules with it, since a rule pointing at nothing would stop working without saying so.

### Input rules

Input is validated strictly, because a value that is quietly accepted and quietly wrong is worse than a rejection.

**Amounts** are plain digits with an optional decimal point. Scientific notation, Python's underscore separators, and digits from other scripts are all rejected — `Decimal` accepts them, but nobody types them on purpose.

**Dates** must be exactly `dd-mm-yyyy`, and must be real: 31 April, 29 February in a common year, month 13 and day 00 are all refused.

**Yes and no** are exact lowercase, in the interface language only — `po`/`jo` in Albanian, `yes`/`no` in English. The input is compared exactly as typed, neither lowercased nor stripped, so `PO` and `" po "` are both refused.

**Cancelling** a prompt takes a whole word in the interface language — `anulo` in Albanian, `cancel` in English — compared exactly as typed. Every prompt that offers it names the word.

**Category and subcategory names** are letters with single spaces between words: `Ushqim`, `Te tjera`, `Paga baze`. No digits, no punctuation. Leading or trailing spaces, runs of spaces, and whitespace-only input are rejected rather than trimmed — a name the program quietly trimmed would not be the name you entered, and two names differing only by a space would look identical in a list. Pressing Enter still means "no category".

### Recurring transactions

Rules support `javore` (weekly), `mujore` (monthly), and `vjetore` (yearly). Due occurrences generate automatically at start-up, or on demand.

Every occurrence is computed from the rule's start date rather than from the previous one, so a rule anchored on the 31st fires 31 January, 28 February, then **31** March. A short month never shifts the schedule permanently.

The transactions and the rule updates commit in a single database transaction, so a crash part-way through leaves nothing behind and the next run produces no duplicates.

### Importing

`--importo SKEDARI` reads a CSV and shows what it contains before anything is written. Menu option 16 does the same.

The file's columns are matched against known header names in both languages; anything unrecognised is asked about rather than guessed at. The account is asked once at the start, since a statement comes from one account.

Number and date formats are worked out from the whole column rather than from one value: `1.234` alone cannot say whether the separator is a decimal point or a thousands mark, while a column also containing `12,50` settles it. The same goes for dates — one `01/02/2026` cannot say which half is the month, but a column containing `15/02/2026` can.

**Nothing is written until you approve it.** The preview shows every parsed row with the amount and date *as the program read them*, not as the file wrote them, because a misread decimal separator and a swapped day and month are silent errors and seeing `€1.23` where `€1,234.56` was meant is how they get caught. From the preview you can deselect rows, set a category on any of them, and then import.

Rows that already exist are flagged as duplicates and deselected — shown rather than skipped, so re-importing an overlapping range is visible instead of quietly doubling your spending. Rows with an unreadable date or amount are flagged too, and cannot be selected.

The import runs as one database transaction. A partial import cannot be told apart from a complete one, and re-running it would double whatever landed.

### Bank statements

A statement from TEB Sh.A. is recognised and read directly, in the HTML the bank emails. No conversion step, and no dependency — `html.parser` is standard library.

Three things about that file would each break a reasonable parser. It is UTF-16 little-endian, so read as UTF-8 it yields no rows rather than an error. It contains six tables, two of them pages of deposit-insurance boilerplate, so the transactions are found by matching the header row rather than by position. And the totals row has one more cell than the header.

**The statement is checked against its own arithmetic before anything is imported.** Every row carries the running balance, so applying each movement to the opening balance must reproduce the balance printed beside it — and the debit total, credit total and row count must match the ones the bank printed. A statement that fails any of these has been misread, and is refused rather than written. The rows that disagree are named.

Cash deposits are recognised and imported as transfers rather than income, with the statement's account on the receiving side. Money moved from a pocket into a bank has not been earned, and putting the account on the wrong side would take the money out of the account the statement says it went into. The other side is left unassigned, which honestly says the cash came from somewhere not yet recorded.

Account and card numbers are stripped from descriptions on the way in, along with masking asterisks, times of day, and trailing date stamps. What is left is what identifies the purchase; the rest would otherwise be stored forever and copied out through every export.

### CSV export

`--eksporto SKEDARI` writes the selected transactions to a CSV file. Every listing filter applies.

A bare filename goes to your Documents folder rather than the current directory; anything with a directory in it is left alone. The full path is printed after the export. Finding Documents is not simply `~/Documents` — Windows relocates it and OneDrive commonly redirects it, so the path comes from the shell's registry record; Linux localizes the name, so it comes from the XDG user-dirs configuration.

The file is written as UTF-8 with a byte order mark, without which Excel mangles every `ë` and `ç`. Amounts are plain decimals with no currency symbol. Use `--ndares ";"` if your spreadsheet expects semicolons.

Export is one-directional. Reading a file back in is a separate feature, described under [Importing](#importing).

### Charts

Bar charts drawn with block characters — no plotting library, and nothing to install. Menu option 10, or `--grafiku`.

Spending and income by category for the current month, and every account balance. `--grafiku 3`, `--grafiku 6` or `--grafiku 12` draws income against spending month by month over that span.

**Bars are scaled against the largest value in their own chart**, so the biggest always fills the width. Scaling against a fixed amount would leave most of the terminal empty whenever the largest expense is small, which is most months. The consequence is that bars compare within a chart and never between two — which is the right trade, since a chart is read on its own.

In the month-by-month chart both series share one scale, so a month with more income than spending is visibly so rather than merely numerically so. A month with nothing in it is still drawn: a gap in the data is itself worth seeing.

Beside each category bar is its share of the total, which is a different question from how long the bar is. A negative account balance keeps its sign — a card in debt is a real state, and hiding it would misreport it.

### Change history

Every create, update and delete on a transaction, account, category, subcategory, recurring rule or budget is recorded: what changed, from what, to what, and when. Menu option 16 shows recent changes or the history of one transaction; `--historia` does the same from the command line, and `--historia 3` narrows it to the third transaction.

The record is written by database triggers rather than by the application. The writes are spread across two modules and two of them are raw SQL, so a missed site would leave a silent gap in a record whose whole value is being complete — and a trigger cannot be forgotten.

The whole row is stored either side of a change and the difference worked out at display time. That keeps the trigger simple and survives a schema change, at the cost of some redundancy the log can easily afford.

One trigger per table per action, and the update trigger also advances `updated_at`. A separate timestamp trigger beside it recorded two entries for every edit — the change, then the timestamp the change caused.

The log is append-only and never pruned. Nothing in the program writes to it directly or deletes from it.

### Timestamps

Every row records when it was written and when it last changed. `--detaje` adds both to the listing; they are hidden otherwise, since two more columns on every row would crowd out the description.

`updated_at` is maintained by the same trigger that records the change. A column DEFAULT fires only on INSERT, so without it the column would record the creation time forever and quietly claim a row had never changed.

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
    importing.py   Reading a file into candidates, with duplicate detection
    statements.py  Bank statements, and checking them against their own totals
    charts.py      Aggregation for the bar charts
    passwords.py   Password hashing
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

Then import it into version 3 with `--importo`, which shows every row for review before writing any of it.

## License

MIT — see [LICENSE](LICENSE).
