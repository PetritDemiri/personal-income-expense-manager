# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Eighteen versions are recorded below. Seventeen of them were released; 2.0.0 was a
development phase whose work shipped as part of 2.1.0, and it is documented
here because it is a distinct stage in the project's history. Commit hashes are
given so each entry can be traced back to the code.

## [3.8.0] — 2026-09-01

### Added

- Bar charts, drawn with block characters and no plotting library. Menu option
  10 or `--grafiku`: spending and income by category for the current month,
  every account balance, and income against spending month by month over three,
  six or twelve months.

### Changed

- Bars are scaled against the largest value in their own chart, so the biggest
  always fills the width. A fixed scale would leave most of a terminal empty
  whenever the largest expense is small, which is most months. Bars therefore
  compare within a chart and never between two.
- Both series in the month-by-month chart share one scale, so a month with more
  income than spending is visibly so rather than merely numerically so.
- The minimum Python version is 3.9 rather than 3.8. 3.8 was claimed but never
  tested — CI has run 3.9 and above throughout — and it reached end of life in
  October 2024.

### Documentation

- The README's sections were ordered by when each was written rather than by
  how anyone reads them. Reordered: where data lives, who owns it, how it is
  organised, how it gets in, how it comes out, what is recorded about it.
- Four modules added to the project layout that had never been listed there:
  `importing.py`, `statements.py`, `charts.py` and `passwords.py`.
- The demo tape draws the charts, is taller to fit them, and pauses for five
  seconds on every screen rather than three.
- Two passages still described reading a CSV as planned rather than present,
  including the upgrade instructions, which told anyone coming from version 2
  to re-enter their data by hand. `--importo` has done that since 3.4.0.

### Notes

- A month with nothing in it is still drawn on the monthly chart. A gap in the
  data is itself worth seeing.
- A negative account balance keeps its sign. A card in debt is a real state and
  hiding it would misreport it.
- Bars are drawn with a three-quarter block rather than a full one. A full
  block fills the whole character cell, so stacked rows run together into a
  solid mass - terminals have no line spacing to separate them.
- 908 tests, up from 861.

## [3.7.0] — 2026-09-01

Every row now has an owner, so version 4 can be a new interface rather than a
new schema.

### Added

- Users. One database can hold several people's finances, kept entirely
  separate: every account, category, transaction, budget and rule belongs to
  exactly one person and no query crosses between them.
- `--perdoruesi` to choose which user to work as, and menu option 17 to add,
  rename, delete, and set passwords.
- Password storage, hashed with PBKDF2-HMAC-SHA256, a random salt per password,
  and the iteration count kept alongside so it can be raised later without
  invalidating existing passwords.
- The change history records which user made each change.
- A migration that checks itself: row counts and money totals are compared
  before and after, and anything missing rolls the whole upgrade back.

### Changed

- Name uniqueness is per-user rather than global, so two people can both have
  an account called `Banka` and a category called `Ushqim`.

### Notes

- The command line never asks for a password. Whoever can run the program can
  open the database file directly, so a prompt would add friction without
  adding protection; the hash is for the web interface, where it is the only
  thing between a stranger and someone's money.
- Argon2 would be the better hashing algorithm. It needs a third-party package,
  and this project has had no runtime dependency since version 1.
- Anyone who never creates a second user sees no change: a database always has
  one, everything belongs to them, and the interface does not mention it.
- Schema version 7. Four tables are rebuilt because a UNIQUE constraint cannot
  be altered in SQLite; three gain a column in place. Foreign keys are disabled
  for the duration, since dropping a rebuilt table would otherwise cascade into
  everything referencing it — which it did, on the first attempt, and the
  verification caught it.
- 861 tests, up from 821.

## [3.6.0] — 2026-08-31

### Added

- Category rules: a piece of text and the category to apply when a description
  contains it, managed from menu option 16.
- Rules applied during the import preview, filling in the category on rows the
  file did not already categorise. Every row is still shown and can still be
  changed before anything is written, and transfers are left alone.
- A suggestion, not a decision, when adding a transaction by hand: a matching
  rule is shown but never filled in. Pre-filling would let a rule written weeks
  ago choose the category on an unread Enter, and a single entry has no preview
  to catch that.
- A count of how many existing transactions a pattern would match, shown before
  the rule is saved. A pattern matching three hundred rows is worth knowing
  about beforehand.

### Notes

- Matching is by substring, case-insensitive, folded the same way category
  names are. Not regular expressions: a wrong pattern does nothing, while a
  wrong expression matches things nobody intended and is hard to spot.
- Where two rules match, the longest pattern wins, so a general and a specific
  rule coexist without an order to maintain.
- A category taken from the imported file is never overwritten by a rule. What
  the import itself said is better evidence than a pattern written weeks ago.
- Deleting a category deletes its rules; a rule pointing at nothing would stop
  working without announcing it. Deleting a subcategory only detaches it.
- Schema version 6. The migration adds one table and its triggers and rebuilds
  nothing, so a database in daily use upgrades in place.
- 821 tests, up from 775.

## [3.5.0] — 2026-08-31

### Added

- Reading bank statements from TEB Sh.A. directly, in the HTML the bank emails.
  No conversion step and no dependency: `html.parser` is standard library.
- Checking a statement against its own arithmetic before importing. Every row
  carries a running balance, so applying each movement to the opening balance
  must reproduce the balance printed beside it, and the debit total, credit
  total and row count must match those the bank printed. A statement failing
  any of these is refused rather than written, and the rows that disagree are
  named.
- Recognition of the statement's own shape: UTF-16 little-endian encoding, six
  tables of which two are legal boilerplate, an opening-balance row carrying
  neither a debit nor a credit, and a totals row one cell wider than the
  header. Each of those would break a parser that assumed otherwise, and the
  UTF-16 one silently — read as UTF-8 the file yields no rows rather than an
  error.
- Stripping of account and card numbers, masking asterisks, times of day and
  trailing date stamps from imported descriptions. What is left identifies the
  purchase; the rest would be stored forever and copied out through every
  export.

### Fixed

- Cash deposits were imported with the statement's account on the paying side,
  which takes money out of the very account the statement says it went into.
  Caught by the balance check on real data: the account came back 100 short of
  the closing balance the bank printed.

### Notes

- Deposits import as transfers with the other side unassigned, which says
  honestly that the cash came from somewhere the program does not track yet.
- The test fixture is a statement with the real structure and formats but
  invented data. Nothing real is in the repository.
- 775 tests, up from 731.

## [3.4.0] — 2026-08-30

### Added

- Importing transactions from a CSV file, via `--importo` or menu option 16.
- Column matching against known header names in both languages, asking about
  anything unrecognised rather than guessing.
- Number and date formats worked out from the whole column rather than from one
  value. `1.234` alone cannot say whether the separator is a decimal point or a
  thousands mark; a column also containing `12,50` settles it. One `01/02/2026`
  cannot say which half is the month; a column containing `15/02/2026` can.
- A preview showing every parsed row before anything is written, with the
  amount and date as the program read them rather than as the file wrote them.
  Rows can be deselected and given a category from there.
- Duplicate detection on date, amount and a normalised description. Matches are
  flagged and deselected rather than skipped, so re-importing an overlapping
  range is visible instead of quietly doubling the spending.
- Recognition of cash deposits, which are a transfer rather than income —
  counting them as income would inflate earnings while leaving the cash account
  too high.
- Support for separate debit and credit columns, with or without their own
  minus sign, as bank statements write them.
- Encoding detection covering UTF-8, UTF-8 with a byte order mark, UTF-16 and
  the common single-byte encodings. A UTF-16 file read as UTF-8 yields no rows
  rather than an error, which is the worst kind of failure.

### Notes

- The import runs as one database transaction. A partial import cannot be told
  apart from a complete one, and re-running it would double whatever landed.
- Nothing reaches the database until the preview is approved, from either the
  menu or the flag.
- 731 tests, up from 650.

## [3.3.0] — 2026-08-28

Completes the scope set out for 3.0.0.

### Added

- A change history. Every create, update and delete on a transaction, account,
  category, subcategory, recurring rule or budget is recorded: what changed,
  from what, to what, and when.
- Menu option 16 and a `--historia` flag, both showing recent changes or the
  history of one transaction.
- The history reads in the interface language rather than in database column
  names: `occurred_on` shows as `Data`, `amount_cents` as `Shuma`. Money is
  shown in euros rather than the raw cents the database holds, dates in
  `dd-mm-yyyy`, and a changed category or account as its name rather than its
  id — falling back to the id only when the row it pointed at has since been
  deleted.

### Changed

- The audit trigger also advances `updated_at`, replacing the separate
  timestamp triggers from 3.2.0. Measured during design, two triggers on one
  UPDATE recorded two entries for every edit — the change, then the timestamp
  the change caused. A trigger cannot re-fire itself while `recursive_triggers`
  is off, which is SQLite's default, so one trigger records exactly one entry.

### Notes

- Written by database triggers rather than by the application. The writes are
  spread across two modules and two of them are raw SQL, so a missed site would
  leave a silent gap in a record whose whole value is being complete.
- The whole row is stored either side of a change, and the difference is worked
  out at display time. Simpler in the trigger, survives a schema change, and
  the redundancy is affordable.
- `created_at` and `updated_at` are excluded from the record, so an entry shows
  the change rather than the change plus the timestamp it caused.
- The log is append-only and never pruned. Nothing in the program writes to it
  directly or deletes from it.
- Schema version 5. The migration drops the timestamp triggers and adds the
  audit triggers; no table is rebuilt, so a database in daily use upgrades in
  place. Changes made before the upgrade have no history, and none is invented.
- 650 tests, up from 601.

## [3.2.0] — 2026-08-27

### Added

- `created_at` and `updated_at` are now maintained on every table and exposed
  on the transaction view.
- A `--detaje` flag adding when each row was recorded and last changed to the
  listing. Off by default: two more columns on every row would crowd out the
  description, and it is rarely the question being asked.
- A migration runner. Version 3 started from an empty database and had no
  upgrade path; there is real data now, so one was needed. A fresh file still
  gets the whole schema at once and skips every step.

### Changed

- `updated_at` is maintained by database triggers rather than by the
  application. A column DEFAULT fires only on INSERT, so the column previously
  recorded the creation time forever and quietly claimed a row had never
  changed. Doing it in code would have meant remembering it at each of eight
  write sites, two of them raw SQL in the service layer that knows nothing
  about timestamps.

### Notes

- Schema version 4. The migration is purely additive — it creates triggers and
  rebuilds no table — so a database in daily use upgrades in place.
- 601 tests, up from 580.

## [3.1.0] — 2026-08-23

### Added

- A Categories menu: view, add, rename, and delete, for categories and
  subcategories alike. Renaming is a single row, since transactions reference a
  category by id. Deleting reports how many transactions will be affected and
  asks before proceeding.

### Changed

- Category and subcategory names must be letters, with single spaces between
  words: `Ushqim`, `Te tjera`, `Paga baze`. No digits and no punctuation.
  Albanian letters count as letters. Leading or trailing spaces, runs of
  spaces, and whitespace-only input are rejected as typed rather than trimmed
  into acceptability — a name the program silently trimmed would not be the
  name the user thought they entered, and two names differing only by a space
  would look identical in a list. Pressing Enter still means "no category".
- Amounts must be plain digits with an optional decimal point. Scientific
  notation, Python's underscore separators, and digits from other scripts are
  rejected; `Decimal` accepts all three, but nobody types them on purpose.
- Dates must be exactly `dd-mm-yyyy`. The shape is checked before the calendar,
  so `1-1-2026` is refused along with `31-04-2026` and `29-02-2026`.
- Yes and no are exact lowercase and only in the interface language: `po`/`jo`
  in Albanian, `yes`/`no` in English. The input is compared exactly as typed —
  neither lowercased nor stripped — so `PO`, `Po` and `" po "` are all refused.
  The `y` and `n` shortcuts are gone, and neither language accepts the other's
  words.

- Cancelling a prompt takes a whole word in the interface language — `anulo` in
  Albanian, `cancel` in English — compared exactly as typed. It was the single
  letter `a`, which collided with `a` as a legitimate category name: the
  category could be created but never chosen for deletion, because the prompt
  read the choice as a cancellation. Every prompt that offers cancelling now
  names the word.

### Fixed

- A category or subcategory typed as spaces was stripped to nothing, read as
  "no category", and reported as a success. It is now rejected.
- A category named `a` could be created but not deleted or renamed, because the
  single-letter cancel key shadowed it at every prompt that listed it.

### Removed

- The built-in category and subcategory suggestion tables. Categories became
  stored records in 3.0.0 and are read from the database; the tables had been
  dead since.

### Notes

- 580 tests, up from 479.

## [3.0.0] — 2026-08-19

A rewrite of the storage layer. The application is SQLite-only, the schema is
written from scratch rather than migrated into shape, and Python identifiers are
English while stored values and the interface stay Albanian.

**This release starts from an empty database.** There is no migration from
version 2, by choice: the CSV backend and its file formats are gone, and so is
the code that read them. Export from 2.4.1 before upgrading if you want a record
of what was there.

### Added

- A schema module holding the whole database definition in one place, with
  foreign keys, CHECK constraints, timestamp columns, and an audit table.
- A database layer with row-level operations. Adding a transaction inserts one
  row; previously every write replaced an entire table, because that is all a
  text file can do.
- Filtering, searching, and aggregation in SQL, against indexes, rather than in
  a Python loop over everything held in memory.
- Categories and subcategories as real records with foreign keys. A name typed
  for the first time is still created automatically, so entry does not stall on
  defining things up front.
- A transaction view carrying both the ids the database stores and the names a
  reader wants, resolved by the join the query needs anyway.
- An `atomic()` context manager, so anything touching more than one table
  commits completely or not at all.
- CHECK constraints the database enforces regardless of what the application
  believes: a transaction kind must be one of the three, a description cannot be
  blank, an amount cannot be negative, a transfer cannot point at its own
  account, and a date must be ISO-shaped.

### Changed

- Every reference is a foreign key rather than a name. Renaming an account is
  now one row, where it previously meant rewriting every transaction and rule
  that named it.
- Absence is NULL. The `Pa kategori` sentinel and the empty-string account are
  gone from storage; they exist only as display labels.
- The service layer holds no cached list of transactions. A cached list can
  drift from what is stored, and keeping it in step is why every write used to
  rewrite the whole table.
- Deleting an account or category leaves its transactions in place, now enforced
  by `ON DELETE SET NULL` rather than by application code remembering to do it.
  Subcategories and budgets cascade, having no meaning without their parent.

### Removed

- The CSV storage backend, `--csv`, and the dual-backend test fixture.
- The legacy CSV reader. Version 2 data does not carry over.

### Fixed

- Six defects found while rewriting, none of them caught by the existing tests:
  filter clauses unqualified against a three-table join; a mechanical rename
  that missed one of two near-identical lines; a message called with the wrong
  placeholder name; a "nothing to nest" check comparing against the old
  empty-string sentinel; single-row reads returning a model where every other
  read returned a view; and a test helper whose reformatting made a scripted
  edit silently no-op.

### Notes

- 479 tests, down from 583. The suites covering the CSV backend, the
  dual-backend parity, and the sentinel-string behaviour were deleted because
  none of those things exist any more.
- Timestamps and the audit log have their tables in this release but are
  populated in 3.1.0 and 3.2.0.

## [2.4.1] — 2026-08-19

Patch release.

### Changed

- An export given as a bare filename is written to the user's Documents folder
  rather than the current directory. An export is a document, not part of the
  project, and it was landing in the project root.
- A path containing a directory is always honoured, so `./out.csv` and absolute
  paths behave exactly as before and scripts are unaffected.
- The full resolved path is printed after an export, rather than echoing back
  what was typed.

### Added

- A locations module that finds the Documents folder properly. `~/Documents` is
  wrong on two of the three supported platforms: Windows relocates the folder
  and OneDrive commonly redirects it, so the path is read from the shell's own
  registry record, and Linux localizes the name, so it comes from the XDG
  user-dirs configuration. Both fall back to the home directory and then to the
  current directory.
- `FINANCE_EXPORT_DIR` for sending bare filenames somewhere other than
  Documents.
- `*.csv` to `.gitignore`. Exports can be named anything, so the list of four
  known data filenames was not enough to stop financial data reaching a commit.

### Fixed

- The tests that simulate the Linux and macOS folder lookups set only `HOME`.
  Windows resolves `~` from `USERPROFILE` and ignores `HOME` entirely, so on
  Windows those tests read the real user's folders instead of the temporary one
  and failed. They now set both. The production code was unaffected; this was a
  portability defect in the suite, found by running it on Windows.

## [2.4.0] — 2026-08-19

### Added

- CSV export via `--eksporto` or the menu, writing the selected transactions to
  a spreadsheet-ready file. Every listing filter applies, so the flags that
  narrow a listing narrow an export.
- `--ndares` for choosing the column delimiter, since locales that use a comma
  for decimals expect a semicolon and getting it wrong puts the whole row in
  one cell.

### Notes on the exported file

- Written as UTF-8 with a byte order mark. Without it Excel assumes the system
  code page and mangles every accented character.
- Column headers and type labels follow the interface language; stored values
  are written unchanged.
- Amounts are plain decimals with no currency symbol, so a spreadsheet reads
  them as numbers. They stay positive with the type in its own column: a signed
  column would sum neatly but would misrepresent transfers, which are neither
  income nor spending.
- Empty fields are blank cells rather than the placeholder labels shown on
  screen, including the stored category sentinel.
- Written atomically, so a failed export cannot replace a good one.

## [2.3.2] — 2026-08-19

Patch release.

### Changed

- An empty category, subcategory, or account now displays as a readable label —
  `Pa kategori`, `Pa nenkategori`, `Pa llogari` — rather than a bare dash, which
  read as a formatting artefact rather than as "this field is empty".
- All three labels follow the interface language. The stored category
  placeholder is Albanian text held in the database, so it is translated at
  display time; an English session previously showed it raw beside translated
  labels.

### Removed

- The `NO_SUBCATEGORY_DISPLAY` and `NO_ACCOUNT_DISPLAY` constants. A string that
  needs translating does not belong in configuration. `CLEAR_MARKER` remains, as
  it is a keystroke at the edit prompt rather than a label.

## [2.3.1] — 2026-08-19

Patch release. Fixes a bug shipped in 2.3.0.

### Fixed

- The interactive menu never asked which account a new transaction or
  recurring rule belonged to, so everything added through it was left
  unassigned even when accounts existed. Both the income and expense options
  run through the same function, so both were affected. The command-line paths
  and the editing flow were unaffected, which is why the gap was not obvious.

### Added

- Tests driving the interactive add and recurring flows. The command-line paths
  were covered and the menu paths were not, which is how an edit that silently
  failed to apply reached a release.

## [2.3.0] — 2026-08-19

Commit `6696be7`. Accounts and transfers.

### Added

- Accounts: cash, bank, and card, each with an opening balance, since an
  account that already held money when tracking began does not start at zero.
  Card accounts may open negative.
- Transfers between accounts, as a third transaction type. Money moved between
  your own accounts is neither income nor an expense: recording an ATM
  withdrawal as spending would drop the combined balance by money still held,
  and recording nothing would leave one account too high and the other too low.
- Per-account and combined balances, with an unassigned row for transactions
  that belong to no account.
- Bulk assignment of account-less transactions and recurring rules to a chosen
  account, so records from before accounts existed can be tidied in one step.
- Accounts submenu, plus `--llogarite`, `--shto-llogari`, `--transfero`,
  `--cakto-pa-llogari`, and `--llogaria` for setting or filtering by account.
- Schema migration 2: an accounts table and the account columns. The first use
  of the migration machinery added in 2.2.0, and a numbered step rather than a
  rewrite.

### Changed

- Accounts are entirely optional. With none defined there is no account prompt,
  no account column, and one combined balance, exactly as before.
- Transfers are shown in cyan rather than green or red, being neither money
  gained nor money lost.
- Renaming an account repoints every transaction and recurring rule that
  referenced it, in one transaction. Deleting one leaves its transactions
  behind as unassigned; the spending still happened.

### Fixed

- `calculate_totals` fell through an `else` branch, which would have counted
  every transfer as spending. Now branches explicitly on each type.
- A missing opening-balance column was read as the string `"None"` rather than
  as zero.
- The unassigned row was numbered like a real account, so it looked selectable,
  and editing or deleting with no accounts defined returned in silence — which
  read as the menu ignoring the choice.
- Two command-line errors used menu wording: an unknown account type told the
  user to press 1 or 2, and an unknown account name was reported as an invalid
  number.
- The list of action flags had drifted from the parser twice, letting start-up
  notices print in scripted output. Now one constant, with a test that keeps it
  honest.
- CSV test fixtures defaulted to the working directory for accounts, leaking
  state between tests.

## [2.2.0] — 2026-08-15

Commit `bb042f3`. SQLite storage and Albanian collation.

### Added

- SQLite backend implementing the existing storage interface, with schema
  versioning through the `user_version` pragma and migrations that run on open.
- Automatic one-time import of existing CSV data on first run. The CSV files
  are left in place, so the move is reversible with `--csv`.
- Full Albanian collation for category and subcategory suggestions, covering
  the 36-letter alphabet including its nine digraphs — dh, gj, ll, nj, rr, sh,
  th, xh, zh — each ranked as a letter in its own right.
- `--csv` and `--baza` flags for choosing the backend and database path.

### Changed

- Money is stored as integer cents rather than a float, keeping amounts exact.
- Dates are stored ISO-formatted internally so they sort and index properly,
  and converted back to `dd-mm-yyyy` for display.
- Suggestion lists are sorted alphabetically with the catch-all category pinned
  last, rather than appending newly used categories to the end.
- Runs of digits compare as numbers, so `Muaji 9` precedes `Muaji 10`.

### Fixed

- Generating recurring transactions wrote the transactions and the updated
  rules as two separate saves. A crash between them left the transactions on
  disk while the rules still recorded nothing as generated, so the next run
  created every occurrence a second time. Both now commit together or neither
  does.
- Subcategory amounts in the category breakdown were positioned from each
  category's own longest name, so they landed left of the category amounts in
  one section and right of them in the next.
- Piping output into a command such as `head` printed a traceback instead of
  exiting quietly.
- The one-time CSV import announcement was suppressed in flag mode.

## [2.1.0] — 2026-08-15

Commit `78a3fa3`. Subcategories, on top of the 2.0.0 restructure below. Both
shipped in this single commit.

### Added

- Optional subcategories, shown in listings, summaries, reports, search, and
  recurring rules. The column appears only once something uses one, so a user
  who does not need them sees no change.
- Suggested subcategories per category, learned from what has already been
  used.

### Changed

- Column widths in the category breakdown are measured across the whole block
  rather than per category.

### Fixed

- Categories typed by the user were appended after the catch-all category,
  leaving the suggestion list ending on a specific category rather than on
  `Te tjera`.
- The delete confirmation did not name the category or subcategory.
- Two-word type labels were mangled by `.capitalize()`, turning `Te Ardhura`
  into `Te ardhura`.

## [2.0.0] — 2026-08-15

Not released separately. This work was completed first and shipped as part of
2.1.0 in commit `78a3fa3`; the version number was superseded before the first
push. It is recorded here because the restructure is a distinct phase in the
project, and the largest single change it has had.

### Added

- Split from a single script into a `personal_finance` package of thirteen
  modules, with a storage interface that the UI, reports, and CLI never look
  behind — the seam that made the later SQLite migration a contained change.
- A pytest suite and GitHub Actions CI running on Linux, macOS, and Windows
  across three Python versions, plus a ruff lint and format job.
- Atomic saves: written to a temporary file, flushed, then moved over the
  original, so an interrupted save cannot truncate the data file.
- Monthly budgets per category, warning at 80% of the limit and again once
  exceeded.
- Monthly reports with a category breakdown and month-over-month comparison.
- Search across description and category.
- An English interface via `--gjuha en`. Stored values stay Albanian, so
  switching language never rewrites data.
- `pyproject.toml` with a `financat` console entry point.

### Changed

- `personal_finance_manager.py` remains as a shim, so the original command
  still works.
- Listings are sorted chronologically, so generated recurring transactions no
  longer appear in rule order.
- A corrupted row is skipped individually with a warning instead of discarding
  the rest of the file.

## [1.0.0] — 2026-08-07

Commit `1db6af5`. The complete single-file application, before the restructure.
One Python file, one CSV.

### Added

- Categories per transaction, chosen from suggestions or typed freely.
- Editing a transaction in place, field by field, with Enter keeping the
  current value.
- Date filtering for a single day or an inclusive range, with totals for the
  filtered set.
- Recurring transactions — weekly, monthly, yearly — generated when due, each
  occurrence computed from the rule's start date so a short month cannot shift
  the schedule permanently.
- ANSI colour output, with automatic fallback where the terminal does not
  support it.
- Albanian command-line flags with English aliases, keeping the interactive
  menu as the default.

### Earlier development

The commits leading to this release, all in the single-file era:

- `eaeea7a` (2026-08-07) — strict `po`/`jo` validation on the date prompt.
- `c53eb94` (2026-08-07) — `calculate_balance` compared the transaction type
  against a lowercase string while the stored value was capitalised, so income
  was never counted and every transaction totalled as an expense.
- `0cfc988` (2026-08-01) — transaction types localised to Albanian.
- `9659038` (2026-08-01) — obsolete key-rename compatibility shim removed.
- `ade6d0a` (2026-08-01) — initial commit.

Two bugs from this period are worth recording, because they are why the test
suite exists. The balance calculation compared the transaction type against a
string that was never stored, so income was silently counted as zero; the same
class of mismatch recurred twice more in different forms, once across languages
and once across capitalisation. Separately, viewing transactions raised
`KeyError` from a one-letter difference between the key written and the key
read.
