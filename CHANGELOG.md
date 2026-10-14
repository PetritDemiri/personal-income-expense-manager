# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Twenty-four versions are recorded below. Twenty-three of them were released;
2.0.0 was a development phase whose work shipped as part of 2.1.0, and it is
documented here because it is a distinct stage in the project's history. Commit
hashes are given so each entry can be traced back to the code.

## [3.11.1] — 2026-10-14

Four faults found while checking the program before making the repository
public. None could lose data.

### Fixed

- Setting another user's password from the users menu showed it on screen as
  it was typed, and took it whatever it was - "1" would do. It is now typed
  out of sight, twice, and held to the rules, like every other new password.
  Enter on its own still removes it.
- A digit that is not 0 to 9 - `²`, `①`, a stray AltGr+2 - ended the program
  at the main menu and at the sign-in screen, before anyone had signed in, and
  at most other places a number is typed: the users menu, a category,
  subcategory or account by number, an account type, a frequency, the months
  of a chart, rows, the import's columns and files, and `--grafiku`. The check
  accepted them as digits and the conversion then refused them. Only 0 to 9
  are digits now; anything else is refused like any other wrong answer. A
  category with such a character in its name - possible through a flag or an
  import - crashed every list of categories as it was sorted; it now sorts
  like any other name.
- Editing a transaction said "transaction #5" after row 3 was picked - the
  number the database keeps, which differs from the row as soon as anything
  has been deleted. It names the row now, and so does the history of one
  transaction, on the menu and with `--historia`. The full history still
  shows the kept number: a deleted transaction has no row any more.
- Typing `anulo` when adding an account made an account called "anulo", and
  when changing one renamed it. Both screens now step back one question at a
  time, like the others.

### Notes

- 1469 tests, up from 1411.

## [3.11.0] — 2026-10-14

Adding several income or expense entries in one go - and the cancel word,
which crashed the program on most of the screens that ask more than one
question.

### Added

- Adding income or expenses starts by asking how many. Each is then asked for
  exactly as a single one is, under a heading that says which it is - "Te
  Ardhura 2 nga 3". From the second on, the date, category, subcategory and
  account of the one before are offered in brackets, so Enter keeps them; the
  description and the amount are always asked afresh. A subcategory is offered
  only under the same category, and a rule matching the new description is
  still suggested beside a carried category, which is only a default.
- Pressing Enter instead of a number means not knowing yet: after each one the
  program asks whether there is another. Typing 1 is exactly what adding
  always was - no heading and no list.
- Several are shown as a list before anything is saved. `ndrysho 2` asks a
  row's questions again with its values in brackets, `fshi 2` takes rows out -
  several at once, the way rows are chosen anywhere else - `ruaj` saves and
  `anulo` leaves without saving anything. The commands work in either
  language, as at the import preview.
- They are saved together, in one database transaction: every one of them or
  none. A budget the batch takes near or over its limit is warned about once,
  not once per row.

### Changed

- Cancelling steps back one question across entries too: from the first
  question of one to the last question of the one before, with its heading
  shown again so it is clear which one an answer belongs to. From the first
  question of the first, it goes back to how many.
- Editing a transaction, adding a transfer, a rule, a budget and a recurring
  transaction ask their questions the way adding does: cancelling steps back
  one question, and is said once when the task starts. When editing, going
  back offers the answer just given, so looking does not undo it.

### Fixed

- Typing `anulo` crashed the program when editing a transaction, adding a
  transfer, assigning transactions to an account, adding a rule, a budget or a
  recurring transaction, after `k 3` at the import preview, and at the
  import's question of which account. Since 3.9.0 the shared questions answer
  the cancel word with a step back rather than a value; only adding income and
  expenses understood it, and every other screen passed it on as if it were an
  answer. Each now steps back, or cancels where the question is the only one.
- An import that failed part-way kept every row written before the first new
  category it created - and the category - instead of nothing: creating the
  category committed everything written so far. Writes inside a database
  transaction now leave the committing to it, so an import is all or nothing
  as it always promised. A single transaction with a new category is written
  the same way, so a failure leaves no category behind either.

### Notes

- 1411 tests, up from 1270.

## [3.10.0] — 2026-10-13

What a test build for the program's first user who is not also its author
showed was worth having, brought into the program itself - and a hole found
while doing it.

### Added

- The first time a person opens the program it runs its own tests on screen,
  which takes one to three minutes, says how it went, and waits for Enter. It
  writes down that it has run in `Documents\Financat\Testet\testet.txt` - the
  date, the version, and how many passed, failed or were skipped - and never
  runs them again; deleting the file brings them back. They run only where
  they exist, in a copy of the source with pytest installed, and only for a
  person at a terminal: a script, a pipe or any run with flags never waits on
  them. `FINANCE_SKIP_TESTS` switches them off.
- A crash is written to `Documents\Financat\Gabimet\gabimet.txt` - when, which
  version, on what Python and system, and the traceback - and the window says
  where. Entries are added, never replaced. A script still sees the error
  raised.
- The window stays open after the program ends in failure - three wrong
  passwords, a cancelled or failed setup, a crash - until Enter is pressed. A
  double-clicked window otherwise disappears with the reason still on it.
  Leaving on purpose never waits, and neither does a script.
- On Windows the window is named after the program while it runs, and given
  its old title back afterwards.
- `FINANCE_HOME` moves the whole of `Documents\Financat`, which is what the
  tests and the demo recordings use to stay away from real folders.

### Changed

- Everything the program writes for itself lives in `Documents\Financat`, each
  kind in a folder of its own: the database in `Te dhenat`, the test record in
  `Testet`, the error log in `Gabimet`. Before, the database sat in whichever
  folder the program was started from, which for a double-clicked program or a
  shortcut depends on how it was opened, so the data could seem to vanish.
  `FINANCE_DATA_DIR` and `--baza` still choose another place. Exports, the
  first-run credentials and a reset code still go to Documents itself, since
  they are meant to be found; `FINANCE_EXPORT_DIR` moves those and never the
  database.
- The first time 3.10.0 runs from a folder that holds an older `finance.db`,
  it copies it to the new place and says so. Copied, never moved: the original
  is left exactly as it was, so nothing can be lost if the copy goes wrong.
  SQLite's own backup is used, since a plain copy would leave behind changes
  still in the write-ahead log. If it cannot be copied it is used where it is.
- A first-run code lives only while the program that showed it is open.
  Leaving in any way - finishing, cancelling, Ctrl+C, a crash, closing the
  window - discards the code and deletes `administratori.txt`, and the next
  launch writes a new one. A code used to last until it expired, so closing
  and reopening could leave a stale file, or a copy still open in Notepad,
  showing a code that no longer worked. Whatever a run killed outright leaves
  is cleared on the next launch. A run with flags leaves it all alone, since
  someone may be part-way through the setup in another window.
- `administratori.txt` says, in Albanian and English, that the password is
  typed in capitals. The boxes accept only capitals and digits, so a lowercase
  letter does nothing at all, which looks as if the program has frozen.

### Removed

- The note on the users screen and at the password prompt saying the command
  line never asks for a password, and that passwords are for the web
  interface. Untrue since 3.9.0 added signing in. The same claim is gone from
  the README, a docstring and a schema comment.

### Fixed

- A setup abandoned after the right code was typed - the window closed, or the
  name prompt cancelled - left an administrator with no password that no
  longer counted as unfinished, so every later run, flags included, walked
  straight in as it. It now counts as unfinished until a name and password are
  chosen: a run with flags is refused, and the next launch starts the setup
  again. Anyone who already walked in that way and used the program keeps the
  account and everything in it; only the stale code goes.
- Three wrong passwords at the sign-in screen ended the program with success,
  indistinguishable from leaving on purpose. It is now a failure, which is
  what keeps the window open to read it.
- The generated setup password had no digit about one time in thirty-six, so
  it broke the password rules it is meant to satisfy and a test failed at
  random - with seven CI jobs a push, roughly one push in six went red for
  nothing. It is now drawn again until it has one, which keeps every valid
  password equally likely.
- A run with flags refused on an unclaimed database left it open.
- The README's menu option numbers for categories, rules, import, history and
  users were out of date, and it still offered `personal_finance_manager.py`,
  removed in 3.9.1.

### Notes

- The first-launch tests run in a process of their own. Run inside the
  program, pytest took over the standard streams and on Windows never handed
  them back, after which the password typed at the first-run setup was shown
  as it was typed.
- The test suite gives every test folders of its own and switches the
  first-launch tests off, so it can never read or write a real
  `Documents\Financat`, or copy a real `finance.db` from the working copy it
  runs in.
- `.gitignore` now covers the session file, the one-time code files and the
  program's other files, which an older version could leave in the project
  folder - a session file is a working login.
- 1270 tests, up from 1148.

## [3.9.1] — 2026-09-13

Two things found while recording the first run, neither of which any test
would have shown: they only appear when the flow is walked as a person.

### Fixed

- Claiming the generated administrator did not sign you in. Having held the
  generated password and chosen a new one, the program asked "who are you?"
  immediately afterwards — a third proof of something already shown twice.
- A running session did not skip the sign-in screen. It saved the password but
  still asked who you were, which is half a session. Signing out still ends it
  and returns to the screen, which is how somebody else takes a turn.

### Documentation

- `demo-setup.tape`, a recording of the first run: the credentials file, the
  boxes filling as the code is typed, and the account being claimed. A
  recording types fixed keystrokes and the generated password is different
  every time, so `demo_setup.py` arranges a known one first. Nothing about how
  the program behaves changes — it checks the password, counts the three
  attempts and expires the code exactly as it always does.

### Notes

- 1148 tests, up from 1141.

## [3.9.0] — 2026-09-02

Signing in, so the mechanism the web interface will need is built and proven
against the command line first.

### Added

- A sign-in screen that asks who you are rather than assuming. Picking a user
  and then demanding that user's password left a second person unable to reach
  their own data at all — only to fail at guessing someone else's.
- Administrators. Everything else in the program was already scoped to its
  owner; managing other people is the one thing that reaches across them, so
  it is the one thing with a role. An ordinary user sees only their own
  password and the way out; adding, renaming, deleting, resetting another's
  password and granting the role are an administrator's.
- A generated administrator for an empty database, called `admin`, with the
  password written to a file rather than the screen. It expires in five
  minutes, allows three attempts, and the account cannot be used for anything
  until the
  generated password has been replaced. This is the shape a deployed web
  version needs, where nobody is at a console when a database is first
  created.
- Changes to user accounts are recorded in the change history: a rename, the
  role being granted or removed, and the moment a password changed. The hash
  itself is never recorded — an append-only log outlives the password it would
  hold — so an administrator resetting an account cannot be hidden from the
  account's owner even though it cannot be prevented.
- The program loops between the sign-in screen and the menu. Signing out is
  the last entry on the main menu and returns to the screen rather than ending
  the program, so somebody else can sign in without restarting it; leaving is
  offered at the screen, which is the one place where nobody's data is on show.
  Where a single user has no password there is no screen to return to, so the
  same entry simply leaves and says so.
- Registration from the sign-in screen. From inside the program you are
  already signed in as somebody, and adding an account for a different person
  is an administrator's job.
- A password prompt for users who have set one, with a session lasting twelve
  hours so the program stays scriptable. `--hyr` and `--dil` sign in and out.
- Password requirements on new passwords: at least 8 characters, one capital
  letter and one digit. Applied when a password is set or changed, never
  retroactively — a rule introduced later must not lock anyone out of their own
  data.
- Changing a password, requiring the current one. Without that check anyone at
  the keyboard could take over an account they are already looking at.
- Resetting a forgotten password with a one-time code written to a file in the
  Documents folder. It expires in five minutes, allows three attempts, and
  works once; a fourth wrong attempt cancels the reset, and requesting a new
  code invalidates the old.
- A code is typed into boxes that fill as you go, the way a verification code
  is entered on a phone. Nine characters with no separator to type; it submits
  itself once the last box is filled, backspace corrects, and Escape cancels.
  Where there is no terminal to draw into — a script, or a piped command — it
  falls back to reading a line and accepts the same code.
- Codes are drawn from an alphabet without `O`, `0`, `I`, `1` or `L`, since
  they are read off a screen and typed by hand and a misread character costs
  one of only three attempts. They are case-sensitive; the grouping shown in
  the file is a display concern and is discarded if typed. The code must be
  entered exactly as shown, dashes included.

### Changed

- A successful sign-in rehashes the password when the stored iteration count is
  below the current one. `needs_rehash` was written in 3.7.0 and until now
  nothing had ever called it, which is the argument for building the login
  here rather than discovering it was wrong from a browser.
- Changing or resetting a password ends every session that user had.
- Adding or editing a transaction asks one question at a time and lets you
  step back. Cancelling at any question returns to the one before rather than
  throwing the lot away; cancelling at the first abandons the task. Six
  questions in, losing five correct answers to fix the sixth is its own kind
  of rudeness.
- Every prompt now states what it accepts, in the same shape. They had
  drifted: one mentioned typing your own value, another mentioned skipping, a
  third said nothing, so the reader had to remember which stage allowed what.
  Cancelling is stated once when a task starts rather than before every
  question.
- Rows are chosen the same way wherever they are chosen — one number, a list,
  a range, and any mixture: `5`, `1, 2, 3`, `5-13`, `1, 3, 5-9`. A range
  written backwards is read forwards. Used both for deleting transactions and
  for selecting rows in the import preview, which previously took a single
  number only.
- Several rows selected together move together: if any is off they all go on,
  otherwise they all go off. Flipping each one separately would leave a mixed
  selection looking untouched.
- The import preview lists its commands one per line with what each does,
  grouped into choosing rows and everything else, rather than a single line
  mixing two styles of explanation, with a blank line between the table, the
  count, the commands and the prompt so a long screen can be read. The same
  spacing on the delete screen, between the table, the guide, the question and
  the result, and on the sign-in, sign-out and goodbye screens. What the user
  typed stays attached to what it produced. The four ways of naming rows are
  shown as four examples, since the syntax alone does not say which form is
  which.
- Several transactions can be deleted at once, written as `1, 2, 3`. Positions
  are resolved to rows before anything is removed, since deleting one at a
  time would shift every row below the first deletion up and the second number
  would name a different transaction than the one on screen. One bad number
  refuses the whole entry. Deleting several shows a table of what
  went, keeping the numbers that were on screen rather than renumbering from
  one — which would leave the reader unable to tell which rows had gone, the
  only reason to print the table at all. Deleting one keeps the single line it
  always had.
- A file to import is searched for by name in the current folder, then
  Downloads, Documents and Desktop, rather than being opened relative to
  whichever folder the program happened to be started from. Downloads is tried
  before the rest, since a bank statement arrives there and nowhere else. The
  prompt says where to put the file.
- The extension need not be typed. A bare name matches every file of that
  name, so nobody has to remember whether the bank sent HTML or CSV; where
  more than one matches, each is offered with its format and the folder it
  came from, and the choice is the user's rather than a guess.
- Exporting adds `.csv` when it is missing. Typing the extension is
  remembering a detail the program knows already, and forgetting it produced a
  file the computer could not open.

### Removed

- `personal_finance_manager.py`, the original single-file program. It has been
  superseded since 2.0.0, reads a storage format that no longer exists, and sat
  in the root named after the project, where anyone browsing would take it for
  the current program. The code is kept in the `v1.0.0` tag.


### Fixed

- Importing ignored a type column, so it read the sign of the amount instead.
  The program's own export writes every amount positive with the type beside
  it, which meant exporting and importing — a round trip — quietly turned
  every expense into earnings. A stated type is now used when the file has
  one, in either language, and the sign only when it does not.
- The folders to put a file in were named in the interface language, sending
  someone to look for a folder called "Dokumente" that Windows calls
  "Documents". They are named as they actually are on the machine.
- A failed import printed the operating system's own message — an errno, in
  English whatever language was chosen — which told nobody anything they could
  act on. A missing file now names itself and the folders that were searched,
  and an unreadable one says so.
- Description, amount and date could not be cancelled at all, so a task begun
  by mistake had to be completed.
- Any flag on an empty database invented an administrator with no password on
  it, and the generated-credentials flow then never ran because users existed.
  A single `--lista` claimed a database silently, and whoever opened it
  afterwards walked straight in. A database nobody has claimed is now refused,
  with a line saying to open the program with no options to set it up — the
  setup is interactive by nature, since a generated password has to be read
  from a file and typed back.
- A first-time setup that was begun and abandoned left a user with no password
  on it, which the ordinary path read as a single-user installation that never
  wanted one — and let the next person straight in. A pending setup now counts
  as an empty database and must be completed.
- Building the audit triggers used the current table list, which meant a
  migration replaying an older step tried to create a trigger on a table — or
  a column — that was still several versions away. The same mistake as the
  index one below, found in a second place; both now check what actually
  exists.
- Migration 7 created every index it found in the schema, but the schema always
  describes the current version — so once migration 8 added two tables, an
  upgrade from version 6 tried to index a table several steps away. It now
  skips indexes whose table does not exist yet.

### Notes

- Session tokens and reset codes are stored hashed, so the database holds
  nothing presentable as a login.
- What this protects against: on a shared machine, one person casually reading
  another's finances. Not someone holding the database file, who can open it in
  any SQLite browser. The database is not encrypted; full-disk encryption is
  what covers a stolen machine, and the operating system does it better than
  this program could.
- Schema version 10. The migrations add four tables and three columns and
  rebuild nothing. Everyone who already existed becomes an administrator: they had
  every power a program without roles offered, and taking it away on upgrade
  would lock people out of their own accounts.
- 1141 tests, up from 911.

## [3.8.1] — 2026-09-01

### Fixed

- Rows in the budget table ran two characters past the rules above and below
  them. The width of the usage column was a hardcoded 16 while the bar and
  percentage take 18; it is measured now rather than guessed at. Every other
  table was checked and lines up.

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
