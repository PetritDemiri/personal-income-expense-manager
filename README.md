# Personal Finance Manager

[![CI](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/PetritDemiri/personal-income-expense-manager/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A command-line personal income and expense manager, with an Albanian interface and an English option. Data lives in SQLite, in a folder of its own inside Documents. No runtime dependencies — standard library only.

![Demo](demo.gif)

The first run, where an empty database hands out the credentials for its administrator rather than letting whoever opens it own the data:

![First run](demo-setup.gif)

## Features

- **Transactions** — add income and expense entries one or several at a time, edit them in place, and delete them
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
- **Checks itself** — the first time it is opened, the program runs its own tests on screen and says how they went

## Install

```bash
git clone https://github.com/PetritDemiri/personal-income-expense-manager.git
cd personal-income-expense-manager
pip install -e .
```

This provides a `financat` command. To run without installing:

```bash
python3 -m personal_finance
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
| 21 | Mbyll sesionin | Sign out |

Dates use `dd-mm-yyyy`. When editing, each prompt shows the current value in brackets — press Enter to keep it.

Options 1 and 2 first ask how many to add — see [Adding several at once](#adding-several-at-once).

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
| `--hyr` | `--login` | Sign in and start a session |
| `--dil` | `--logout` | Sign out |
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

Everything lives in one SQLite database, `finance.db`, created on first run in `Documents\Financat\Te dhenat` — see [Where things are kept](#where-things-are-kept). Choose another folder with `FINANCE_DATA_DIR`, or the file itself with `--baza`.

Money is stored as an integer count of cents rather than a float, so amounts stay exact. Dates are stored ISO-formatted so they sort and range-query correctly, and are converted to `dd-mm-yyyy` for display. Every named thing carries a normalised copy of its name for uniqueness, because SQLite's own case-insensitive collation folds only A–Z and would accept `Ë` and `ë` as different letters.

Foreign keys are enforced. Deleting an account or a category does not delete what referenced it — the spending still happened, only the label is gone — so those become `NULL`. A subcategory has no meaning without its parent, and a budget is a limit on a category, so both cascade.

Two constraints are deliberately absent: there is no maximum amount, since any ceiling is arbitrary and would not catch a digit too many; and there is no check on an account's kind or a rule's frequency, since those lists are likely to grow while income and expense are not.

### Where things are kept

Everything the program writes for itself lives in one folder inside Documents, each kind in a folder of its own:

```
Documents\Financat\
    Te dhenat\    finance.db, and the file that keeps a session signed in
    Testet\       testet.txt — when the first-launch tests ran, and how they went
    Gabimet\      gabimet.txt — written only if the program crashes
```

Before 3.10.0 the database sat in whichever folder the program was started from, which for a double-clicked program or a shortcut depends on how it was opened — so the data could seem to vanish. Documents is found the same way as for exports: from the shell's own record on Windows, which follows the folder into OneDrive, and from XDG on Linux. The folder names are fixed rather than translated, so changing the interface language never leaves the data behind.

Files you are meant to pick up — exports, the first-run credentials, a password-reset code — go to Documents itself, where they are easy to find.

| Variable | What it moves |
|---|---|
| `FINANCE_HOME` | the whole of `Documents\Financat` |
| `FINANCE_DATA_DIR` | only the database |
| `FINANCE_EXPORT_DIR` | exports and the files you are meant to pick up — never the database |
| `FINANCE_SKIP_TESTS` | switches the first-launch tests off |

**Upgrading from 3.9 or earlier.** The first time 3.10.0 runs from a folder that holds an older `finance.db`, it copies it to `Te dhenat` and says so. It is copied, never moved: the original is left exactly as it was, so nothing can be lost if the copy goes wrong — delete it yourself once you are happy. If it cannot be copied, it is used where it is. Naming the folder with `FINANCE_DATA_DIR`, or the file with `--baza`, skips all of this.

### Users

One database can hold several people's finances, kept entirely separate. Every account, category, transaction, budget and rule belongs to exactly one person, and no query crosses between them.

Anyone who never creates a second user sees no change at all: a database always has one, everything belongs to them, and the interface never mentions it. `--perdoruesi EMRI` switches, and menu option 18 manages them.

Two people can both have an account called `Banka` and a category called `Ushqim`, which is why the uniqueness constraints are per-user rather than global.

Passwords are hashed with PBKDF2-HMAC-SHA256, a random salt per password, and the iteration count stored alongside so it can be raised later without invalidating existing passwords. Argon2 would be the better algorithm and is what this would use in production; it needs a third-party package, and this project has had no runtime dependency since version 1.

Deleting a user deletes everything they own. There is no softer option: the data means nothing without them, and leaving it orphaned would be worse.

### Signing in

A user with no password is never asked for one, so a single-person installation is unchanged. Set one and the program asks on the first command, then issues a **session lasting twelve hours** — so a script running inside that window is never prompted. `--hyr` signs in explicitly and `--dil` signs out.

A running session skips the sign-in screen — it means you already said who you are, so being asked again inside the twelve hours would be asking twice. Claiming the generated administrator signs you in for the same reason.

**The program loops between the sign-in screen and the menu.** Signing out is the last entry on the main menu and returns you to the screen rather than ending the program, so somebody else can sign in without restarting it. Leaving is offered at the screen, which is the one place where nobody's data is on show — two decisions rather than one.

Where there is a single user with no password there is no screen to return to, so that same entry simply leaves, and says so.

A new password must be at least 8 characters with at least one capital letter and one digit. The rule applies when a password is set or changed, never retroactively, so an upgrade cannot lock anyone out of their own data.

Session tokens are stored hashed, so the database never holds one that could be presented as a login, and the token file is owner-only where the platform supports it.

**What this protects against, stated plainly.** On a shared machine it keeps one person from casually reading another's finances. It is *not* protection against someone holding `finance.db`, who can open it in any SQLite browser regardless — the file's own permissions are that boundary, and full-disk encryption such as BitLocker or FileVault is what covers a stolen machine. The database is not encrypted.

#### Changing and resetting

Changing your own password requires the current one; without that check anyone at the keyboard could take over an account they are already looking at.

A forgotten password is reset with a one-time code, written to a text file in your Documents folder. The code expires in **five minutes**, allows **three attempts**, and works once — a fourth wrong attempt cancels the reset entirely, and requesting a new code invalidates the old.

The code is typed into boxes that fill as you go, the way a verification code is entered on a phone:

```
Kodi:  [X][C][Q] [2][E][S] [B][3][Z]
```

Nine characters, no separator to type — the grouping is there to be read. It submits itself once the last box is filled; backspace corrects, Escape cancels. Where there is no terminal to draw into — a script, or a piped command — it falls back to reading a line, and the same code is accepted.

Codes are drawn from an alphabet without `O`, `0`, `I`, `1` or `L`, since they are read off a screen and typed by hand, and they are **case-sensitive**.

Anyone who can run the program can also read that file, so on one machine this is a deliberate, time-limited, recorded procedure rather than a barrier. The expiry and the attempt limit are what make it correct once the code is delivered somewhere else, which is what the web interface will do.

Changing or resetting a password ends every session that user had, since a login granted under the old one should not survive it.

An administrator can also reset someone else's forgotten password, for the case where a person is locked out and cannot work the self-service flow. Setting someone's password from the users menu is typed out of sight, twice, and held to the same rules as any other new password; Enter on its own removes it. **Changes to user accounts are recorded in the change history** — a rename, the role being granted or removed, and the moment a password changed. The password hash itself is never recorded: an append-only log outlives the password it would hold. So an administrator resetting an account cannot be prevented, but neither can it be hidden — the account's owner sees that it happened and when.

The log records whose account changed, not who changed it. SQLite triggers cannot see which user the program is acting as; the web version, which has a request behind every change, will be able to record that.

### The first launch

The first time a person opens the program, it checks itself before anything else: it runs its own test suite on screen, says how it went, and waits for Enter. That takes one to three minutes, and happens once — it writes down that it has run in `Documents\Financat\Testet\testet.txt`, with the date, the version and how many tests passed, failed or were skipped. Delete that file to run them again.

They run only where they exist — a copy of the source with pytest installed — and only for a person at a terminal: a script, a piped command or any run with flags never waits on them. `FINANCE_SKIP_TESTS=1` switches them off.

They run in a process of their own rather than inside the program. pytest takes over the standard streams while it works and, on Windows, does not hand the originals back — inside the program, the password typed at the first-run setup afterwards was shown as it was typed.

### An unclaimed database

A database with nobody in it belongs to nobody. Running the program with no options starts the first-time setup; running it **with** a flag refuses, and says to open it with no options instead.

That matters because the alternative is worse than it sounds: a flag that quietly created an owner would mean one `--lista` claimed an empty database with no password on it, and the generated credentials would never be handed out, because by then users existed.

**A first-run code lives only while the program that showed it is open.** Leaving in any way — finishing, cancelling, Ctrl+C, a crash, closing the window — discards the code and deletes `administratori.txt`, and the next launch writes a new one. A code that outlived the program could leave a stale file, or a copy still open in an editor, showing a code that no longer works. Whatever a run killed outright leaves behind is cleared on the next launch. A run with flags leaves it all alone, since someone may be part-way through the setup in another window.

A setup abandoned after the right code was typed still counts as unfinished until a name and password have been chosen — before 3.10.0 it did not, and the next run walked straight in.

The file says, in Albanian and English, that the password is typed in capitals: the boxes accept only capitals and digits, so a lowercase letter does nothing at all.

### When something goes wrong

A double-clicked window disappears the moment the program ends, taking the reason with it. So when the program ends in failure — three wrong passwords, a cancelled or failed setup, a crash — it waits for Enter first. Leaving on purpose never waits, and neither does anything run by a script.

A crash is written to `Documents\Financat\Gabimet\gabimet.txt`: when, which version, on what Python and system, and the traceback. Entries are added, never replaced. A script still sees the error raised, as before.

On Windows the window is named after the program while it runs, and given its old title back afterwards.

### Accounts

Accounts are optional and off until you create one. With none defined the program behaves as it always has: no account prompt, no account column, one combined balance.

An account carries an **opening balance**, because an account that already held €500 when you started tracking does not have a balance of zero. Card accounts can open negative.

Money moved between your own accounts is a **transfer**, not an expense. Recording an ATM withdrawal as spending would make your combined total drop by money you still have. A transfer is a transaction type of its own, shown in cyan, and counted as neither income nor spending.

### Categories and subcategories

Both are stored records, managed from menu option 11 — view, add, rename, and delete, for categories and subcategories alike. A name typed for the first time while adding a transaction is still created automatically, so entry never stalls on defining things up front.

Renaming is one row. Transactions reference a category by id, so the rename does not touch them. Deleting a category leaves its transactions uncategorised and takes its subcategories and any budget with it; the menu says how many transactions will be affected and asks before doing it.

Suggestions are sorted in **Albanian alphabetical order**, following the full 36-letter alphabet including its nine digraphs:

```
a b c ç d dh e ë f g gj h i j k l ll m n nj o p q r rr s sh t th u v x xh y z zh
```

Each digraph is a letter in its own right, so every word beginning with S comes before every word beginning with Sh — `Sende`, `Sy`, then `Shendetesi`. Sorting by Unicode code point, which is what most languages do by default, interleaves them and pushes every accented word past Z.

### Category rules

A rule is a piece of text and the category to apply when a description contains it. Menu option 17 manages them.

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

### Adding several at once

Adding income or expenses starts by asking how many:

```
Duke shtuar Te Ardhura...
  (Shkruani 'anulo' per t'u kthyer)
  (Shtypni Enter nese nuk e dini sa)
Sa te ardhura doni te shtoni? 2

Te Ardhura 1 nga 2
Vendosni pershkrimin: Paga e tetorit
...
```

Each one is then asked for exactly as a single one is, under a heading that says which it is. **From the second on, the date, category, subcategory and account of the one before are offered in brackets**, so Enter keeps them — several entered together are usually from the same day, the same shop, the same account. The description and the amount are always asked afresh. A subcategory is offered only under the same category, since it means nothing under another. A category carried over is only a default, so a rule matching the new description is still suggested beside it.

Pressing Enter instead of a number means you don't know yet: after each one the program asks `Te shtoni edhe nje? (po/jo)`. Typing `1` is exactly what adding always was.

**Several are shown as a list before anything is saved:**

```
Te ardhurat qe do te shtohen:
--------------------------------------------------------
# Data       Lloji      Pershkrimi     Kategoria   Shuma
--------------------------------------------------------
1 14-10-2026 Te Ardhura Paga e tetorit Paga      €650.00
2 14-10-2026 Te Ardhura Bonus          Paga       €80.00
--------------------------------------------------------

Komandat:
  ndrysho 2   ndrysho rreshtin 2
  fshi 2      hiq rreshtin 2
  ruaj        ruaj te gjitha
  anulo       dil pa ruajtur asgje
```

`ndrysho` asks a row's questions again with its values in brackets; `fshi` takes rows out, and accepts several the way rows are chosen anywhere else. As at the import preview, the commands work in either language. **Then they are saved together — every one of them, or none**, in one database transaction: a half-saved batch would leave you unable to tell what had landed, and entering it again would double whatever had. A budget the batch takes near or over its limit is warned about once, not once per row.

### Asking questions

Every task that asks several questions — adding or editing a transaction, an account, a transfer, a budget, a rule, a recurring transaction — asks them one at a time. **Cancelling at any question steps back to the one before**, keeping the answers already given; cancelling at the first abandons the task. A task six questions long should not throw away five correct answers to fix the sixth. When editing, going back offers the answer just given, so looking does not undo it. When adding several, stepping back from the first question of one goes to the last question of the one before.

Every prompt states what it accepts — typing your own value, pressing Enter to skip, or cancelling — so nothing has to be remembered from one stage to the next. Cancelling is stated once when a task starts.

Rows are chosen the same way wherever they are chosen — one number, a list, a range, or any mixture:

```
5            one row
1, 2, 3      several
5-13         a range
1, 3, 5-9    mixed
```

A range written backwards is read forwards. Several transactions can be deleted at once this way, and the same notation selects rows in the import preview. The positions are resolved to rows before anything is removed: deleting one at a time would shift every row below the first deletion up, and the second number would then name a different transaction than the one on screen. One number that does not exist refuses the whole entry, since a typo in a list of rows to delete should stop the deletion rather than quietly remove a different set. The table of what was deleted keeps the numbers that were on screen — renumbering from one would leave you unable to tell which rows had gone.

### Input rules

Input is validated strictly, because a value that is quietly accepted and quietly wrong is worse than a rejection.

**Amounts** are plain digits with an optional decimal point. Scientific notation, Python's underscore separators, and digits from other scripts are all rejected — `Decimal` accepts them, but nobody types them on purpose. An account's opening balance follows the same rule, with a leading minus allowed, since a card usually starts out owing money.

**Dates** must be exactly `dd-mm-yyyy`, and must be real: 31 April, 29 February in a common year, month 13 and day 00 are all refused.

**Numbers** chosen at a menu, a list or a row are the digits 0 to 9 and nothing else. `²` or `①` — a stray AltGr away on some keyboards — is refused like any other wrong answer; it used to end the program.

**Yes and no** are exact lowercase, in the interface language only — `po`/`jo` in Albanian, `yes`/`no` in English. The input is compared exactly as typed, neither lowercased nor stripped, so `PO` and `" po "` are both refused.

**Cancelling** a prompt takes a whole word in the interface language — `anulo` in Albanian, `cancel` in English — compared exactly as typed. Every prompt that offers it names the word.

**Category and subcategory names** are letters with single spaces between words: `Ushqim`, `Te tjera`, `Paga baze`. No digits, no punctuation. Leading or trailing spaces, runs of spaces, and whitespace-only input are rejected rather than trimmed — a name the program quietly trimmed would not be the name you entered, and two names differing only by a space would look identical in a list. Pressing Enter still means "no category".

### Recurring transactions

Rules support `javore` (weekly), `mujore` (monthly), and `vjetore` (yearly). Due occurrences generate automatically at start-up, or on demand.

Every occurrence is computed from the rule's start date rather than from the previous one, so a rule anchored on the 31st fires 31 January, 28 February, then **31** March. A short month never shifts the schedule permanently.

The transactions and the rule updates commit in a single database transaction, so a crash part-way through leaves nothing behind and the next run produces no duplicates.

### Importing

`--importo SKEDARI` reads a CSV and shows what it contains before anything is written. Menu option 19 does the same.

The file's columns are matched against known header names in both languages; anything unrecognised is asked about rather than guessed at. The account is asked once at the start, since a statement comes from one account.

A type column is used when the file has one — `Lloji` or `Type`, reading `Te Ardhura`, `Shpenzime` and their English equivalents. That matters most for the program's own export, which writes every amount positive with the type beside it: reading only the sign would turn every expense back into income.

Number and date formats are worked out from the whole column rather than from one value: `1.234` alone cannot say whether the separator is a decimal point or a thousands mark, while a column also containing `12,50` settles it. The same goes for dates — one `01/02/2026` cannot say which half is the month, but a column containing `15/02/2026` can.

**Nothing is written until you approve it.** The preview shows every parsed row with the amount and date *as the program read them*, not as the file wrote them, because a misread decimal separator and a swapped day and month are silent errors and seeing `€1.23` where `€1,234.56` was meant is how they get caught. From the preview you can deselect rows, set a category on any of them, and then import.

Rows that already exist are flagged as duplicates and deselected — shown rather than skipped, so re-importing an overlapping range is visible instead of quietly doubling your spending. Rows with an unreadable date or amount are flagged too, and cannot be selected.

The import runs as one database transaction. A partial import cannot be told apart from a complete one, and re-running it would double whatever landed.

### Finding a file to import

A file is searched for by name in the current folder, then **Downloads, Documents and Desktop** — named as they are on the machine rather than translated, since telling someone to use "Dokumente" sends them looking for a folder Windows calls "Documents". Downloads comes first because that is where a bank statement arrives. A full path is always used as given.

The extension need not be typed: a bare name matches every file of that name, so nobody has to remember whether the bank sent HTML or CSV. Where several match, each is offered with its format and the folder it came from:

```
U gjeten disa skedare me kete emer:
  1. for-database.csv  (ne Downloads)
  2. for-database.htm  (ne Downloads)
```

When a file cannot be read, the reason is given in words — the file was not found and here is where it was looked for, or it cannot be read, or it is a folder. The operating system's own message is an errno in English whatever language was chosen, and tells nobody anything they can act on.

### Bank statements

A statement from TEB Sh.A. is recognised and read directly, in the HTML the bank emails. No conversion step, and no dependency — `html.parser` is standard library.

Three things about that file would each break a reasonable parser. It is UTF-16 little-endian, so read as UTF-8 it yields no rows rather than an error. It contains six tables, two of them pages of deposit-insurance boilerplate, so the transactions are found by matching the header row rather than by position. And the totals row has one more cell than the header.

**The statement is checked against its own arithmetic before anything is imported.** Every row carries the running balance, so applying each movement to the opening balance must reproduce the balance printed beside it — and the debit total, credit total and row count must match the ones the bank printed. A statement that fails any of these has been misread, and is refused rather than written. The rows that disagree are named.

Cash deposits are recognised and imported as transfers rather than income, with the statement's account on the receiving side. Money moved from a pocket into a bank has not been earned, and putting the account on the wrong side would take the money out of the account the statement says it went into. The other side is left unassigned, which honestly says the cash came from somewhere not yet recorded.

Account and card numbers are stripped from descriptions on the way in, along with masking asterisks, times of day, and trailing date stamps. What is left is what identifies the purchase; the rest would otherwise be stored forever and copied out through every export.

### CSV export

`--eksporto SKEDARI` writes the selected transactions to a CSV file. Every listing filter applies.

A bare filename goes to your Documents folder rather than the current directory; anything with a directory in it is left alone. Set `FINANCE_EXPORT_DIR` to send bare filenames somewhere else. The full path is printed after the export. Finding Documents is not simply `~/Documents` — Windows relocates it and OneDrive commonly redirects it, so the path comes from the shell's registry record; Linux localizes the name, so it comes from the XDG user-dirs configuration.

The file is written as UTF-8 with a byte order mark, without which Excel mangles every `ë` and `ç`. Amounts are plain decimals with no currency symbol. Use `--ndares ";"` if your spreadsheet expects semicolons.

Export is one-directional. Reading a file back in is a separate feature, described under [Importing](#importing).

### Colours

Income is green, expenses red, transfers cyan, and a budget turns yellow as it approaches its limit and red once past it.

Colour is decided once at start-up, in this order:

1. `--pa-ngjyra` turns it off outright
2. `NO_COLOR` set to anything turns it off — the [no-color.org](https://no-color.org) convention
3. `FORCE_COLOR` set to anything turns it on
4. Otherwise, on only when writing to a terminal, so a redirect to a file or a pipe into another command gets plain text rather than escape codes
5. `TERM=dumb` turns it off

On Windows, ANSI support is switched on through the console API at start-up; if that call fails the program falls back to plain text rather than printing escape codes at you.

### Charts

Bar charts drawn with block characters — no plotting library, and nothing to install. Menu option 10, or `--grafiku`.

Spending and income by category for the current month, and every account balance. `--grafiku 3`, `--grafiku 6` or `--grafiku 12` draws income against spending month by month over that span.

**Bars are scaled against the largest value in their own chart**, so the biggest always fills the width. Scaling against a fixed amount would leave most of the terminal empty whenever the largest expense is small, which is most months. The consequence is that bars compare within a chart and never between two — which is the right trade, since a chart is read on its own.

In the month-by-month chart both series share one scale, so a month with more income than spending is visibly so rather than merely numerically so. A month with nothing in it is still drawn: a gap in the data is itself worth seeing.

Beside each category bar is its share of the total, which is a different question from how long the bar is. A negative account balance keeps its sign — a card in debt is a real state, and hiding it would misreport it.

### Change history

Every create, update and delete on a transaction, account, category, subcategory, recurring rule or budget is recorded: what changed, from what, to what, and when. Menu option 20 shows recent changes or the history of one transaction; `--historia` does the same from the command line, and `--historia 3` narrows it to the third transaction.

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
    passwords.py   Password hashing and one-time codes
    auth.py        Signing in, sessions, and password resets
    codeentry.py   Typing a one-time code into boxes
    selftest.py    The tests the first launch runs
    console.py     The window: its title, crashes, and being closed
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

The suite gives every test folders of its own and switches the first-launch tests off, so it never reads or writes a real `Documents\Financat` — or copies a real `finance.db` from the working copy it runs in.

### Recording the demo GIFs

```bash
vhs demo.tape          # requires https://github.com/charmbracelet/vhs
vhs demo-setup.tape
```

Both run against a temporary folder — named with `FINANCE_DATA_DIR`, `FINANCE_HOME` and `FINANCE_EXPORT_DIR` — so real data never appears in a recording. Naming the data folder also stops the program copying a `finance.db` it finds in the project folder. Run them from the project folder: the second runs `demo_setup.py`.

`demo-setup.tape` records the first run. A recording types fixed keystrokes and the generated password is different every time, and a code lives only while the program that showed it is open, so it cannot be arranged beforehand. Instead `financat` is defined, off camera, to run `demo_setup.py`, which runs the program itself with a known password. Nothing else about how it behaves changes — it writes the file, checks the password, counts the three attempts and expires the code exactly as it always does. The first-launch tests are switched off for it. The two password fields near the end show nothing as they are typed, which is what setting a password looks like anywhere.

## Upgrading from 3.9

The database moves to `Documents\Financat\Te dhenat`. The first run of 3.10.0 from the folder that holds your `finance.db` copies it there and says so; the original is left untouched, to delete yourself once you are happy. See [Where things are kept](#where-things-are-kept).

## Upgrading from version 2

Version 3 starts from an empty database. There is no automatic migration: the CSV backend and its file formats are gone, and so is the code that read them.

To carry data across, export it from version 2.4.1 first:

```bash
financat --eksporto transaksionet.csv
```

Then import it into version 3 with `--importo`, which shows every row for review before writing any of it.

## License

MIT — see [LICENSE](LICENSE).
