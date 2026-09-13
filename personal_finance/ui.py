"""Nderfaqja interaktive / Interactive interface.

Everything that reads from stdin lives here. The prompt helpers are shared
between adding and editing so both paths validate input identically.

Rows are numbered 1..N on screen and mapped back to database ids internally.
The two must not be conflated: ids develop gaps as things are deleted, and a
menu that showed them would look broken.
"""

import getpass
import os
import re
from decimal import Decimal, InvalidOperation

from .accounts import balances_for, count_unassigned, find_account
from .budgets import all_statuses
from .charts import SPANS, account_bars, category_bars, monthly_bars
from .codeentry import prompt_code
from .colors import BOLD, CYAN, DIM, GREEN, RED, YELLOW, paint, type_color
from .config import CLEAR_MARKER
from .dates import (
    current_date_str,
    format_date,
    format_month,
    month_of,
    parse_date,
    parse_month,
    previous_month,
    today,
)
from .display import (
    category_path,
    money,
    print_account_chart,
    print_accounts,
    print_budget_warning,
    print_budgets,
    print_candidates,
    print_category_chart,
    print_history,
    print_monthly_chart,
    print_monthly_report,
    print_recurring,
    print_summary,
    print_transactions,
)
from .i18n import affirmatives, cancels, frequency_label, negatives, t, type_label
from .models import ACCOUNT_KINDS, parse_amount, valid_name
from .passwords import CODE_ALPHABET, CODE_LENGTH
from .recurring import FREQUENCIES
from .reports import calculate_totals, month_report, sort_by_date
from .schema import EXPENSE, INCOME, TRANSFER

# The cancel word is language-dependent and lives in the message catalog; see
# i18n.cancels(). Every check below compares the input exactly as typed - not
# lowercased, not stripped - so " anulo " and "ANULO" are refused.


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------


def numbered(transactions, subset=None):
    """Pair transactions with their 1-based position in the full list.

    The number shown is a position, never a database id. A number seen in a
    filtered view still refers to the same row in the full list, so it can be
    used directly to edit or delete.
    """
    positions = {item.id: index for index, item in enumerate(transactions, start=1)}
    items = subset if subset is not None else transactions
    return [(positions.get(item.id, 0), item) for item in items]


def pick(app, message):
    """Show the transactions and ask for one by number. Returns a view or None."""
    rows = app.transactions()
    print_transactions(numbered(rows))
    if not rows:
        return None
    typed = input(message)
    if typed in cancels():
        print(t("cancelled"))
        return None
    try:
        position = int(typed)
        if position < 1 or position > len(rows):
            raise ValueError
    except ValueError:
        print(paint(t("invalid_number"), RED))
        return None
    return rows[position - 1]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


class _Back:
    """Returned by a prompt when the user asked to go back rather than answer.

    A sentinel rather than None, because None already means something at
    several prompts - no subcategory, no account - and the two must not be
    confused. Compared with `is`, never by truthiness.
    """

    def __repr__(self):
        return "BACK"


BACK = _Back()


def hint(*keys):
    """Print the options a prompt offers, in the same shape every time.

    They had drifted: one prompt mentioned typing your own value, another
    mentioned skipping, a third said nothing. Every prompt now states what it
    accepts, so the reader never has to remember which stage allows what.
    """
    for key in keys:
        print(paint(f"  {t(key)}", DIM))


def run_stages(stages):
    """Ask a sequence of questions, letting the user step back through them.

    Returns the answers, or None if they stepped back past the first question
    - which is what cancelling a whole task means. Going back one step at a
    time matters here because these tasks are several questions long, and
    losing four correct answers to fix the fifth is its own kind of rudeness.
    """
    hint("hint_cancel")
    values = {}
    index = 0
    while index < len(stages):
        name, ask = stages[index]
        answer = ask(values)
        if answer is BACK:
            index -= 1
            if index < 0:
                return None
            continue
        values[name] = answer
        index += 1
    return values


def prompt_description(current=None):
    while True:
        if current is None:
            value = input(t("ask_description"))
        else:
            value = input(t("ask_description_keep", current=current))
            if not value.strip():
                return current
        if value in cancels():
            return BACK
        if value.strip():
            return value.strip()
        print(paint(t("empty_description"), RED))


def prompt_amount(current=None):
    while True:
        if current is None:
            raw = input(t("ask_amount"))
        else:
            raw = input(t("ask_amount_keep", current=f"{current:.2f}"))
            if not raw.strip():
                return current
        if raw in cancels():
            return BACK
        amount = parse_amount(raw)
        if amount is None:
            print(paint(t("invalid_amount"), RED))
            continue
        return amount


def prompt_date(current=None):
    """Ask for a date, offering today as a shortcut when adding."""
    if current is None:
        hint("hint_today")
        while True:
            # Compared exactly as typed - not lowercased, not stripped. Both
            # would quietly accept something the user did not write: "PO", or
            # " po " with spaces around it.
            choice = input(t("ask_today"))
            if choice in cancels():
                return BACK
            if choice in affirmatives():
                return current_date_str()
            if choice in negatives():
                break
            print(paint(t("yes_no_only"), RED))

    while True:
        if current is None:
            raw = input(t("ask_date"))
        else:
            raw = input(t("ask_date_keep", current=current))
            if not raw.strip():
                return current
        if raw in cancels():
            return BACK
        if parse_date(raw.strip()) is not None:
            return raw.strip()
        print(paint(t("invalid_date"), RED))


def prompt_kind(current=None):
    while True:
        print(f"  1. {type_label(INCOME)}")
        print(f"  2. {type_label(EXPENSE)}")
        if current is None:
            raw = input(t("choose_type")).strip()
        else:
            raw = input(t("type_prompt_keep", current=type_label(current))).strip()
            if not raw:
                return current
        if raw == "1":
            return INCOME
        if raw == "2":
            return EXPENSE
        print(paint(t("invalid_type"), RED))


def prompt_category(app, kind, current=None, description=None):
    """Ask for a category, offering the ones already defined.

    A name typed here that does not exist yet is created when the transaction
    is saved, so entry never stalls on defining a category first.

    When a rule matches the description it is shown as a suggestion rather
    than filled in. Pre-filling would let a rule written weeks ago decide the
    category on an unread Enter; during an import the preview catches that,
    but a single entry has no preview to catch it.
    """
    if description and current is None:
        rule = app.rule_for(description)
        if rule is not None:
            shown = rule.category + (f" / {rule.subcategory}" if rule.subcategory else "")
            print(paint(t("rule_suggestion", category=shown), DIM))

    options = app.category_names(kind)
    if options:
        print(f"\n{t('suggested_categories')}")
        for index, name in enumerate(options, start=1):
            print(f"  {index}. {name}")
    hint("hint_own_category")

    while True:
        # Validated exactly as typed. Stripping first would silently accept
        # " Ushqim ", and the stored name would not be the one entered.
        typed = (
            input(t("ask_category"))
            if current is None
            else input(t("ask_category_keep", current=current))
        )

        if typed in cancels():
            return BACK
        if not typed:
            return None if current is None else current
        if current is not None and typed == CLEAR_MARKER:
            return None

        if typed.isdigit():
            index = int(typed)
            if 1 <= index <= len(options):
                return options[index - 1]
            print(paint(t("invalid_category_number"), RED))
            continue
        if not valid_name(typed):
            print(paint(t("invalid_name"), RED))
            continue
        return typed


def prompt_subcategory(app, kind, category, current=None):
    """Ask for an optional subcategory.

    Enter means "none" when adding. When editing, Enter keeps the current
    value and a lone dash clears it, since Enter cannot mean both.
    """
    if not category:
        return None

    options = app.subcategory_names(category, kind)
    if options:
        print(f"\n{t('suggested_subcategories')}")
        for index, name in enumerate(options, start=1):
            print(f"  {index}. {name}")
    hints = ["hint_own_subcategory"]
    if current is None:
        hints.append("hint_skip_subcategory")
    hint(*hints)

    while True:
        typed = (
            input(t("ask_subcategory"))
            if current is None
            else input(t("ask_subcategory_keep", current=current or t("no_subcategory")))
        )

        if typed in cancels():
            return BACK
        if not typed:
            return None if current is None else current
        if current is not None and typed == CLEAR_MARKER:
            return None

        if typed.isdigit():
            index = int(typed)
            if 1 <= index <= len(options):
                return options[index - 1]
            print(paint(t("invalid_subcategory_number"), RED))
            continue
        if not valid_name(typed):
            print(paint(t("invalid_name"), RED))
            continue
        return typed


def prompt_account(app, current=None, message_key="ask_account", allow_skip=True):
    """Ask which account something belongs to. Returns an id, or None."""
    accounts = app.accounts()
    print(f"\n{t('accounts_title')}")
    for index, account in enumerate(accounts, start=1):
        print(f"  {index}. {account.name}")
    if allow_skip and current is None:
        hint("hint_skip_account")

    current_name = None
    if current is not None:
        match = [a for a in accounts if a.id == current]
        current_name = match[0].name if match else None

    while True:
        if current is None:
            raw = input(t(message_key)).strip()
            if raw in cancels():
                return BACK
            if not raw and allow_skip:
                return None
        else:
            raw = input(
                t("ask_account_keep", current=current_name or t("no_account_display"))
            ).strip()
            if raw in cancels():
                return BACK
            if not raw:
                return current
            if raw == CLEAR_MARKER and allow_skip:
                return None

        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(accounts):
                return accounts[index - 1].id
            print(paint(t("invalid_account_number"), RED))
            continue

        matched = find_account(accounts, raw)
        if matched is not None:
            return matched.id
        print(paint(t("invalid_account_number"), RED))


def prompt_account_kind(current=None):
    print(f"\n{t('field_type')}:")
    for index, name in enumerate(ACCOUNT_KINDS, start=1):
        print(f"  {index}. {name}")
    while True:
        raw = input(t("ask_account_type", count=len(ACCOUNT_KINDS))).strip()
        if not raw and current is not None:
            return current
        if raw.isdigit() and 1 <= int(raw) <= len(ACCOUNT_KINDS):
            return ACCOUNT_KINDS[int(raw) - 1]
        print(paint(t("invalid_type"), RED))


def prompt_opening_balance(current=None):
    """Ask for an opening balance, which may legitimately be negative."""
    while True:
        if current is None:
            raw = input(t("ask_opening")).strip()
            if not raw:
                return Decimal("0.00")
        else:
            raw = input(t("ask_opening_keep", current=f"{current:.2f}")).strip()
            if not raw:
                return current
        try:
            value = Decimal(raw)
            if not value.is_finite():
                raise InvalidOperation
            return value
        except InvalidOperation:
            print(paint(t("invalid_opening"), RED))


def prompt_index(count, message):
    """Ask for a 1-based number in range. Returns a 0-based index or None."""
    typed = input(message)
    if typed in cancels():
        print(t("cancelled"))
        return None
    try:
        number = int(typed)
        if number < 1 or number > count:
            raise ValueError
    except ValueError:
        print(paint(t("invalid_number"), RED))
        return None
    return number - 1


def prompt_menu_choice(low, high):
    return input(t("choose", range=f"{low}-{high}")).strip()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def show_transactions(app):
    print_transactions(numbered(app.transactions()))


def show_balance(app):
    rows = app.transactions()
    print_summary(rows, calculate_totals(rows))
    if app.has_accounts():
        print_accounts(balances_for(app.accounts(), rows))


def add_transaction(app, kind):
    """Ask for a transaction one question at a time, and write it.

    Cancelling at any question steps back to the one before rather than
    throwing the lot away; cancelling at the first abandons the whole thing.
    Six questions in, losing five correct answers to fix the sixth would be
    its own kind of rudeness.
    """
    print(paint(f"\n{t('adding', type=type_label(kind))}", BOLD))

    stages = [
        ("description", lambda _v: prompt_description()),
        ("amount", lambda _v: prompt_amount()),
        ("occurred_on", lambda _v: prompt_date()),
        (
            "category",
            lambda v: prompt_category(app, kind, description=v["description"]),
        ),
        ("subcategory", lambda v: prompt_subcategory(app, kind, v["category"])),
    ]
    if app.has_accounts():
        stages.append(("account_id", lambda _v: prompt_account(app)))

    answers = run_stages(stages)
    if answers is None:
        print(t("cancelled"))
        return

    transaction = app.add_transaction(
        kind,
        answers["description"],
        answers["amount"],
        answers["occurred_on"],
        answers["category"],
        answers["subcategory"],
        answers.get("account_id"),
    )
    print(paint(t("added", type=type_label(kind)), BOLD))
    print_budget_warning(app.budget_warning(transaction))


def edit_transaction(app):
    chosen = pick(app, t("ask_number_edit"))
    if chosen is None:
        return

    print(paint(f"\n{t('editing', number=chosen.id)}", BOLD))
    print(paint(t("press_enter_keep"), DIM))

    print(f"\n{t('field_type')}:")
    kind = prompt_kind(current=chosen.kind)
    description = prompt_description(current=chosen.description)
    amount = prompt_amount(current=chosen.amount)
    occurred_on = prompt_date(current=chosen.occurred_on)
    category = prompt_category(app, kind, current=chosen.category)
    # Asked fresh when the category changed, since the old subcategory belonged
    # to the old category and means nothing under the new one.
    current_sub = chosen.subcategory if category == chosen.category else None
    subcategory = prompt_subcategory(app, kind, category, current=current_sub)

    changes = {
        "kind": kind,
        "description": description,
        "amount": amount,
        "occurred_on": occurred_on,
        "category": category,
        "subcategory": subcategory,
    }
    if app.has_accounts():
        changes["account_id"] = prompt_account(app, current=chosen.account_id)

    app.update_transaction(chosen.id, **changes)
    print(paint(t("edited"), BOLD))


ROW_EXAMPLE_KEYS = ("rows_single", "rows_several", "rows_range", "rows_mixed")


def print_rows_guide(indent=""):
    """How to name rows, shown the same way everywhere rows are named.

    Four examples rather than one line of syntax: "1, 3, 5-9" shows what can
    be typed without saying which part is a list and which is a range. The
    indent lets the same four lines sit inside a longer list of commands.
    """
    print(paint(f"{indent}{t('rows_guide')}", DIM))
    for key in ROW_EXAMPLE_KEYS:
        print(paint(f"{indent}{t(key)}", DIM))


def parse_positions(typed, count):
    """The row numbers in what was typed, in order, without repeats.

    Understands one number, a list, a range, and any mixture: "5", "1, 2, 3",
    "5-13", "1, 3, 5-9". A range written backwards is read forwards, since
    "13-5" can only have meant one thing.

    Returns None if any part is not a row that exists. Rejecting the whole
    entry rather than the good parts of it is deliberate: a typo in a list of
    rows should stop the task, not quietly act on a different set from the one
    that was meant.
    """
    positions = []

    def add(number):
        if number not in positions:
            positions.append(number)

    for part in re.split(r"[,\s]+", (typed or "").strip()):
        if not part:
            continue

        bounds = part.split("-")
        if len(bounds) == 2 and all(b.strip().isdigit() for b in bounds):
            first, last = (int(b) for b in bounds)
            if first > last:
                first, last = last, first
            if first < 1 or last > count:
                return None
            for number in range(first, last + 1):
                add(number)
            continue

        if not part.isdigit():
            return None
        number = int(part)
        if number < 1 or number > count:
            return None
        add(number)

    return positions or None


def delete_transaction(app):
    """Delete one transaction or several.

    Positions are resolved to ids before anything is removed. Deleting by
    position one at a time would shift every row below the first deletion up,
    and the second number would then name a different transaction than the
    one on screen.
    """
    rows = app.transactions()
    print_transactions(numbered(rows))
    if not rows:
        return

    print()
    print_rows_guide()
    hint("hint_cancel_task")

    print()
    typed = input(t("ask_numbers_delete"))
    if typed in cancels():
        print(t("cancelled"))
        return

    positions = parse_positions(typed, len(rows))
    if positions is None:
        print(paint(t("no_valid_numbers"), RED))
        return

    chosen = [rows[position - 1] for position in positions]
    if len(chosen) > 1:
        answer = input(t("confirm_delete_several", count=len(chosen))).strip()
        if answer not in affirmatives():
            print(t("cancelled"))
            return

    # Kept from before the deletion, so the table below can show the numbers
    # that were on screen rather than renumbering from one.
    listed = numbered(rows, sorted(chosen, key=lambda view: rows.index(view)))

    removed = [app.delete_transaction(view.id) for view in chosen]
    print()
    if len(removed) == 1:
        one = removed[0]
        print(
            paint(
                t(
                    "deleted",
                    date=one.occurred_on,
                    type=type_label(one.kind),
                    description=one.description,
                    category=category_path(one),
                ),
                BOLD,
            )
        )
        return

    print(paint(t("deleted_several", count=len(removed)), BOLD))
    print_transactions(listed, title=t("deleted_title"))


# ---------------------------------------------------------------------------
# Filtering and search
# ---------------------------------------------------------------------------


def show_filtered(app, start, end, title):
    matches = app.transactions(start=start, end=end)
    print_transactions(numbered(app.transactions(), matches), title)
    if matches:
        print_summary(matches, calculate_totals(matches), t("filter_totals"))


def filter_single_date(app):
    while True:
        raw = input(t("filter_date"))
        if raw in cancels():
            print(t("cancelled"))
            return
        target = parse_date(raw)
        if target is None:
            print(paint(t("invalid_date"), RED))
            continue
        show_filtered(app, target, target, t("transactions_on", date=format_date(target)))
        return


def filter_date_range(app):
    while True:
        raw = input(t("filter_start"))
        if raw in cancels():
            print(t("cancelled"))
            return
        start = parse_date(raw)
        if start is None:
            print(paint(t("invalid_date"), RED))
            continue
        break

    while True:
        raw = input(t("filter_end"))
        if raw in cancels():
            print(t("cancelled"))
            return
        end = parse_date(raw)
        if end is None:
            print(paint(t("invalid_date"), RED))
            continue
        if end < start:
            print(paint(t("end_before_start"), RED))
            continue
        break

    show_filtered(
        app,
        start,
        end,
        t("transactions_between", start=format_date(start), end=format_date(end)),
    )


def search_transactions(app):
    term = input(t("ask_search")).strip()
    matches = app.transactions(search=term) if term else []
    print_transactions(
        numbered(app.transactions(), matches),
        t("transactions_matching", term=term),
    )
    if matches:
        print_summary(matches, calculate_totals(matches), t("filter_totals"))


def filter_menu(app):
    print(paint(f"\n{t('filter_menu_title')}", BOLD, CYAN))
    print(f"1. {t('filter_single')}")
    print(f"2. {t('filter_range')}")
    print(f"3. {t('back')}")

    choice = prompt_menu_choice(1, 3)
    if choice == "1":
        filter_single_date(app)
    elif choice == "2":
        filter_date_range(app)
    elif choice == "3":
        return
    else:
        print(paint(t("invalid_choice", low=1, high=3), RED))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_to_csv(app):
    """Ask for a file name and an optional date range, then write the file."""
    import os

    from .export import export_transactions
    from .locations import resolve_export_path

    rows = app.transactions()
    if not rows:
        print(paint(t("export_empty"), YELLOW))
        return

    print(paint(f"\n{t('export_title')}", BOLD, CYAN))
    hint("hint_cancel_task")
    path = input(t("ask_export_path")).strip()
    if not path or path in cancels():
        print(t("cancelled"))
        return

    # Resolved before the check, so the prompt names the file that would
    # actually be replaced rather than the name that was typed.
    target = resolve_export_path(path)
    if os.path.exists(target):
        answer = input(t("export_overwrite", path=target)).strip()
        if answer.lower() not in affirmatives():
            print(t("cancelled"))
            return

    answer = input(t("ask_export_filter")).strip()
    if answer in cancels():
        print(t("cancelled"))
        return
    if answer.lower() in affirmatives():
        while True:
            raw = input(t("filter_start"))
            if raw in cancels():
                print(t("cancelled"))
                return
            start = parse_date(raw)
            if start is None:
                print(paint(t("invalid_date"), RED))
                continue
            break
        while True:
            raw = input(t("filter_end"))
            if raw in cancels():
                print(t("cancelled"))
                return
            end = parse_date(raw)
            if end is None:
                print(paint(t("invalid_date"), RED))
                continue
            if end < start:
                print(paint(t("end_before_start"), RED))
                continue
            break
        rows = app.transactions(start=start, end=end)

    try:
        count, written_to = export_transactions(path, sort_by_date(rows))
    except Exception as error:
        print(paint(t("export_failed", error=error), RED))
        return
    print(paint(t("exported", count=count, path=written_to), BOLD))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def show_month_report(app, year, month):
    print_monthly_report(month_report(app.transactions(), year, month))


def report_menu(app):
    year, month = month_of(today())
    print(paint(f"\n{t('menu_report')}:", BOLD, CYAN))
    print(f"1. {t('report_menu_this')}")
    print(f"2. {t('report_menu_last')}")
    print(f"3. {t('report_menu_choose')}")
    print(f"4. {t('back')}")

    choice = prompt_menu_choice(1, 4)
    if choice == "1":
        show_month_report(app, year, month)
    elif choice == "2":
        earlier_year, earlier_month = previous_month(year, month)
        show_month_report(app, earlier_year, earlier_month)
    elif choice == "3":
        parsed = parse_month(input(t("ask_month")).strip())
        if parsed is None:
            print(paint(t("invalid_month"), RED))
            return
        show_month_report(app, parsed[0], parsed[1])
    elif choice == "4":
        return
    else:
        print(paint(t("invalid_choice", low=1, high=4), RED))


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def show_accounts(app):
    print_accounts(balances_for(app.accounts(), app.transactions()))


def add_account(app):
    print(paint(f"\n{t('adding_account')}", BOLD))
    while True:
        name = input(t("ask_account_name")).strip()
        if not name:
            print(paint(t("empty_description"), RED))
            continue
        if app.account_by_name(name) is not None:
            print(paint(t("account_exists"), RED))
            continue
        break

    kind = prompt_account_kind()
    opening = prompt_opening_balance()
    app.add_account(name, kind, opening)
    print(paint(t("account_added", name=name), BOLD))


def edit_account(app):
    show_accounts(app)
    accounts = app.accounts()
    if not accounts:
        print(paint(t("no_accounts_to_change"), YELLOW))
        return
    index = prompt_index(len(accounts), t("ask_number_account"))
    if index is None:
        return

    account = accounts[index]
    print(paint(t("press_enter_keep"), DIM))

    while True:
        name = input(t("ask_account_name_keep", current=account.name)).strip()
        if not name:
            name = account.name
            break
        existing = app.account_by_name(name)
        if existing is not None and existing.id != account.id:
            print(paint(t("account_exists"), RED))
            continue
        break

    kind = prompt_account_kind(current=account.kind)
    opening = prompt_opening_balance(current=account.opening)
    app.update_account(account.id, name=name, kind=kind, opening=opening)
    print(paint(t("account_updated"), BOLD))


def delete_account(app):
    show_accounts(app)
    accounts = app.accounts()
    if not accounts:
        print(paint(t("no_accounts_to_delete"), YELLOW))
        return
    index = prompt_index(len(accounts), t("ask_number_account"))
    if index is None:
        return
    removed, affected = app.delete_account(accounts[index].id)
    print(paint(t("account_deleted", name=removed.name, count=affected), YELLOW))


def assign_unassigned_transactions(app):
    """Move every account-less transaction onto a chosen account."""
    if not app.has_accounts():
        print(paint(t("no_accounts_to_change"), YELLOW))
        return

    pending = count_unassigned(app.transactions(), app.recurring_rules())
    if not pending:
        print(paint(t("nothing_unassigned"), YELLOW))
        return

    target_id = prompt_account(app, allow_skip=False)
    if target_id is None:
        return
    target = [a for a in app.accounts() if a.id == target_id][0]

    answer = input(t("assign_confirm", count=pending, name=target.name)).strip().lower()
    if answer not in affirmatives():
        print(t("cancelled"))
        return

    assigned = app.assign_unassigned_to(target_id)
    print(paint(t("assigned", count=assigned, name=target.name), BOLD))


def add_transfer(app):
    """Record a movement between two of the user's own accounts."""
    accounts = app.accounts()
    if len(accounts) < 2:
        print(paint(t("transfer_needs_two"), YELLOW))
        return

    print(paint(f"\n{t('adding_transfer')}", BOLD))
    source_id = prompt_account(app, allow_skip=False)
    if source_id is None:
        return

    while True:
        destination_id = prompt_account(app, message_key="ask_destination", allow_skip=False)
        if destination_id is None:
            return
        if destination_id == source_id:
            print(paint(t("same_account"), RED))
            continue
        break

    description = prompt_description()
    amount = prompt_amount()
    occurred_on = prompt_date()

    app.add_transaction(
        TRANSFER,
        description,
        amount,
        occurred_on,
        account_id=source_id,
        to_account_id=destination_id,
    )
    print(paint(t("transfer_added"), BOLD))


def account_menu(app):
    while True:
        print(paint(f"\n{t('menu_accounts')}:", BOLD, CYAN))
        print(f"1. {t('account_menu_view')}")
        print(f"2. {t('account_menu_add')}")
        print(f"3. {t('account_menu_edit')}")
        print(f"4. {t('account_menu_delete')}")
        print(f"5. {t('account_menu_assign')}")
        print(f"6. {t('back')}")

        choice = prompt_menu_choice(1, 6)
        if choice == "1":
            show_accounts(app)
        elif choice == "2":
            add_account(app)
        elif choice == "3":
            edit_account(app)
        elif choice == "4":
            delete_account(app)
        elif choice == "5":
            assign_unassigned_transactions(app)
        elif choice == "6":
            return
        else:
            print(paint(t("invalid_choice", low=1, high=6), RED))


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def prompt_span():
    """Ask over how many months to draw. None if cancelled."""
    spans = ", ".join(str(s) for s in SPANS)
    while True:
        raw = input(t("ask_span", spans=spans))
        if raw in cancels():
            print(t("cancelled"))
            return None
        if raw.isdigit() and int(raw) in SPANS:
            return int(raw)
        print(paint(t("invalid_span", spans=spans), RED))


def show_category_chart(app, kind):
    year, month = month_of(today())
    bars = category_bars(app.transactions(), kind, year, month)
    key = "chart_categories_title" if kind == EXPENSE else "chart_income_title"
    print_category_chart(bars, t(key, month=format_month(year, month)), type_color(kind))


def show_monthly_chart(app, span=None):
    span = span or prompt_span()
    if span is None:
        return
    _months, income, expenses = monthly_bars(app.transactions(), today(), span)
    print_monthly_chart(income, expenses, t("chart_months_title", span=span))


def show_account_chart(app):
    bars = account_bars(balances_for(app.accounts(), app.transactions()))
    print_account_chart(bars, t("chart_accounts_title"))


def charts_menu(app):
    while True:
        print(paint(f"\n{t('menu_charts')}:", BOLD, CYAN))
        print(f"1. {t('chart_menu_categories')}")
        print(f"2. {t('chart_menu_income')}")
        print(f"3. {t('chart_menu_months')}")
        print(f"4. {t('chart_menu_accounts')}")
        print(f"5. {t('back')}")

        choice = prompt_menu_choice(1, 5)
        if choice == "1":
            show_category_chart(app, EXPENSE)
        elif choice == "2":
            show_category_chart(app, INCOME)
        elif choice == "3":
            show_monthly_chart(app)
        elif choice == "4":
            show_account_chart(app)
        elif choice == "5":
            return
        else:
            print(paint(t("invalid_choice", low=1, high=5), RED))


# ---------------------------------------------------------------------------
# The first run, and choosing who you are
# ---------------------------------------------------------------------------


def run_first_setup(app):
    """Generate an administrator for an empty database and hand it over.

    The credentials go to a file rather than the screen so they are not left
    in the terminal's scrollback, and they are useless once claimed. If they
    expire or the attempts run out, the account is discarded and the next run
    generates fresh ones - safe, because there is nothing in the database yet
    to lock anyone out of.
    """
    from .auth import SETUP_ATTEMPTS, SETUP_MINUTES, ResetOutcome
    from .passwords import CODE_ALPHABET, SETUP_LENGTH

    print(paint(f"\n{t('setup_title')}", BOLD, CYAN))
    print(t("setup_intro"))

    user_id, name = app.pending_admin()
    if user_id is None:
        name, _password, path = app.create_admin()
        user_id, _ = app.pending_admin()
    else:
        from .auth import setup_file_path
        from .locations import documents_directory

        path = setup_file_path(documents_directory())

    print()
    print(paint(t("setup_written", path=path), BOLD, CYAN))
    print()
    print(paint(t("setup_name", name=name), BOLD))
    print()
    print(paint(t("setup_expires", minutes=SETUP_MINUTES, attempts=SETUP_ATTEMPTS), DIM))
    print()

    while True:
        typed = prompt_code(t("ask_setup_password"), SETUP_LENGTH, allowed=CODE_ALPHABET)
        if typed is None:
            print(t("cancelled"))
            return False
        outcome, left = app.check_setup_password(typed)
        if outcome == ResetOutcome.OK:
            break
        if outcome == ResetOutcome.WRONG:
            print(paint(t("setup_wrong", count=left), RED))
            continue
        key = "setup_expired" if outcome == ResetOutcome.EXPIRED else "setup_exhausted"
        print(paint(t(key), RED))
        return False

    print(paint(f"\n{t('setup_claim')}", BOLD))
    print()
    chosen = prompt_name("ask_new_user_name")
    if chosen is None:
        return False
    password = prompt_new_password()
    if password is None:
        return False

    app.complete_setup(user_id, chosen, password, path)
    print()
    print(paint(t("setup_done", name=chosen), BOLD, GREEN))
    return True


def register_user(app):
    """Let someone create their own account from the sign-in screen.

    Registration lives here rather than in the menu, because from inside the
    program you are already signed in as somebody, and adding an account for
    a different person is an administrator's job.
    """
    name = prompt_name("ask_new_user_name")
    if name is None:
        return None
    if app.user_exists(name):
        print(paint(t("user_exists"), RED))
        return None

    password = prompt_new_password()
    if password is None:
        return None

    user_id = app.add_user(name, password)
    print(paint(t("user_created", name=name), BOLD))
    return user_id


def choose_user(app):
    """Ask who is using the program. Returns a user id, or None to stop."""
    while True:
        users = app.users()
        print(paint(f"\n{t('who_are_you')}", BOLD, CYAN))
        for index, user in enumerate(users, start=1):
            role = t("role_admin") if user.is_admin else t("role_user")
            print(f"  {index}. {user.name}  {paint('(' + role + ')', DIM)}")
        print(f"  {len(users) + 1}. {t('user_new')}")
        # Leaving the program lives here rather than in the main menu, so
        # signing out and shutting down are two decisions rather than one.
        print(f"  {len(users) + 2}. {t('exit_program')}")

        print()
        raw = input(t("ask_who", count=len(users) + 2))
        if raw in cancels():
            return None
        if not raw.isdigit():
            print(paint(t("invalid_number"), RED))
            continue

        choice = int(raw)
        if choice == len(users) + 2:
            return None
        if choice == len(users) + 1:
            created = register_user(app)
            if created is not None:
                return created
            continue
        if 1 <= choice <= len(users):
            return users[choice - 1].id
        print(paint(t("invalid_number"), RED))


def sign_in_as(app, user_id):
    """Ask for a password, offering the forgotten-password path.

    The reset lives at the password prompt, which is the only place it makes
    sense: it is offered to someone who cannot get in, not to someone who is
    already inside.
    """
    user = next((u for u in app.users() if u.id == user_id), None)
    if user is None:
        return False
    if not user.has_password:
        app.use_user(user_id)
        return True

    forgot = t("forgot_password")
    for remaining in (2, 1, 0):
        if remaining == 2:
            print()
        typed = getpass.getpass(t("ask_password_or_forgot", name=user.name, forgot=forgot))
        if typed == forgot:
            return reset_own_password(app, user)
        if app.sign_in(typed, user_id=user_id):
            from .auth import SESSION_HOURS

            print(paint(t("login_ok", hours=SESSION_HOURS), BOLD, GREEN))
            return True
        if remaining:
            print(paint(t("login_failed", count=remaining), RED))
    print(paint(t("login_refused"), RED))
    return False


def reset_own_password(app, user):
    """The forgotten-password path, reached from the sign-in prompt."""
    from .auth import RESET_ATTEMPTS, RESET_MINUTES, ResetOutcome
    from .passwords import CODE_ALPHABET, CODE_LENGTH

    print(paint(f"\n{t('reset_intro')}", BOLD))
    print(paint(t("reset_note"), DIM))
    _code, path = app.begin_reset(user.id)
    print(paint(t("reset_written", path=path), BOLD, CYAN))
    print(paint(t("reset_expires", minutes=RESET_MINUTES, attempts=RESET_ATTEMPTS), DIM))

    while True:
        typed = prompt_code(t("ask_reset_code"), CODE_LENGTH, allowed=CODE_ALPHABET)
        if typed is None:
            print(t("cancelled"))
            return False
        outcome, left = app.check_reset_code(user.id, typed)
        if outcome == ResetOutcome.OK:
            break
        if outcome == ResetOutcome.WRONG:
            print(paint(t("reset_wrong", count=left), RED))
            continue
        key = {
            ResetOutcome.EXPIRED: "reset_expired",
            ResetOutcome.EXHAUSTED: "reset_exhausted",
            ResetOutcome.NONE: "reset_none",
        }[outcome]
        print(paint(t(key), RED))
        return False

    password = prompt_new_password()
    if password is None:
        return False
    app.finish_reset(user.id, password, path)
    print(paint(t("reset_done", name=user.name), BOLD))
    return app.sign_in(password, user_id=user.id)


def start_session(app):
    """Everything before the main menu. False means do not continue.

    A single user with no password is let straight through, so the promise
    that a one-person installation sees no change is kept.
    """
    if app.needs_setup():
        return run_first_setup(app)

    users = app.users()
    signed_in = app.signed_in_user()
    if signed_in is not None:
        app.use_user(signed_in)
        return True

    if len(users) == 1 and not users[0].has_password:
        app.use_user(users[0].id)
        return True

    chosen = choose_user(app)
    if chosen is None:
        return False
    return sign_in_as(app, chosen)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def prompt_new_password(label="ask_password_new"):
    """Ask for a new password twice, enforcing the rules. None if cancelled."""
    from .passwords import MIN_LENGTH, password_problems

    while True:
        first = getpass.getpass(t(label))
        if first in cancels():
            print(t("cancelled"))
            return None
        problems = password_problems(first)
        if problems:
            rules = ", ".join(t(key, count=MIN_LENGTH) for key in problems)
            print(paint(t("password_rules", rules=rules), RED))
            continue
        again = getpass.getpass(t("ask_password_again"))
        if again != first:
            print(paint(t("password_mismatch"), RED))
            continue
        return first


def sign_in(app):
    """Ask for the password, up to three times. True when signed in."""
    from .auth import SESSION_HOURS

    user = app.current_user()
    for remaining in (2, 1, 0):
        password = getpass.getpass(t("ask_login_password", name=user.name))
        if app.sign_in(password):
            print(paint(t("login_ok", hours=SESSION_HOURS), BOLD, GREEN))
            return True
        if remaining:
            print(paint(t("login_failed", count=remaining), RED))
    print(paint(t("login_refused"), RED))
    return False


def change_own_password(app):
    user = app.current_user()
    current = ""
    if user.has_password:
        current = getpass.getpass(t("ask_password_current"))
        if current in cancels():
            print(t("cancelled"))
            return
    new_password = prompt_new_password()
    if new_password is None:
        return
    if not app.change_password(current, new_password):
        print(paint(t("password_wrong_current"), RED))
        return
    print(paint(t("password_changed"), BOLD))


def reset_password(app):
    """Write a one-time code, then take a new password once it is entered."""
    from .auth import RESET_ATTEMPTS, RESET_MINUTES, ResetOutcome

    user = pick_user(app)
    if user is None:
        return

    print(paint(f"\n{t('reset_intro')}", BOLD))
    print(paint(t("reset_note"), DIM))
    code, path = app.begin_reset(user.id)
    print(paint(t("reset_written", path=path), BOLD, CYAN))
    print(paint(t("reset_expires", minutes=RESET_MINUTES, attempts=RESET_ATTEMPTS), DIM))

    while True:
        typed = prompt_code(t("ask_reset_code"), CODE_LENGTH, allowed=CODE_ALPHABET)
        if typed is None or typed in cancels():
            print(t("cancelled"))
            return
        outcome, left = app.check_reset_code(user.id, typed)
        if outcome == ResetOutcome.OK:
            break
        if outcome == ResetOutcome.WRONG:
            print(paint(t("reset_wrong", count=left), RED))
            continue
        key = {
            ResetOutcome.EXPIRED: "reset_expired",
            ResetOutcome.EXHAUSTED: "reset_exhausted",
            ResetOutcome.NONE: "reset_none",
        }[outcome]
        print(paint(t(key), RED))
        return

    new_password = prompt_new_password()
    if new_password is None:
        return
    app.finish_reset(user.id, new_password, path)
    print(paint(t("reset_done", name=user.name), BOLD))


def show_users(app):
    """Every user, their role, and whether each has a password set.

    An ordinary user sees only themselves. Listing the household is an
    administrator's business.
    """
    users = app.users() if app.is_admin else [app.current_user()]
    current = app.user_id

    names = [u.name for u in users]
    roles = [t("role_admin") if u.is_admin else t("role_user") for u in users]
    w_name = max([len(t("field_name"))] + [len(v) for v in names])
    w_role = max([len(t("field_role"))] + [len(v) for v in roles])
    w_pass = max(len(t("field_password")), len(t("user_has_password")))
    total = 4 + w_name + 2 + w_role + 2 + w_pass + 4

    print(paint(f"\n{t('users_title')}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{'#':<4}{t('field_name'):<{w_name}}  {t('field_role'):<{w_role}}  "
            f"{t('field_password'):<{w_pass}}",
            BOLD,
        )
    )
    print("-" * total)
    for index, user in enumerate(users, start=1):
        marker = " *" if user.id == current else ""
        has = t("user_has_password") if user.has_password else t("user_no_password")
        role = t("role_admin") if user.is_admin else t("role_user")
        print(f"{index:<4}{user.name:<{w_name}}  {role:<{w_role}}  {has:<{w_pass}}{marker}")
    print("-" * total)
    print(paint(t("password_note"), DIM))


def add_user(app):
    name = prompt_name("ask_user_name")
    if name is None:
        return
    if app.user_exists(name):
        print(paint(t("user_exists"), RED))
        return
    app.add_user(name)
    print(paint(t("user_added", name=name), BOLD))


def pick_user(app):
    show_users(app)
    users = app.users()
    index = prompt_index(len(users), t("ask_number_user"))
    return users[index] if index is not None else None


def rename_user(app):
    user = pick_user(app)
    if user is None:
        return
    name = prompt_name("ask_rename", current=user.name)
    if name is None:
        return
    existing = [u for u in app.users() if u.key == name.casefold() and u.id != user.id]
    if existing:
        print(paint(t("user_exists"), RED))
        return
    app.rename_user(user.id, name)
    print(paint(t("user_renamed", name=name), BOLD))


def set_user_password(app):
    """Set or clear a password, for the web interface to use later."""
    user = pick_user(app)
    if user is None:
        return
    print(paint(t("password_note"), DIM))
    password = input(t("ask_password"))
    if password in cancels():
        print(t("cancelled"))
        return
    app.set_password(user.id, password or None)
    key = "user_password_set" if password else "user_password_cleared"
    print(paint(t(key, name=user.name), BOLD))


def delete_user(app):
    users = app.users()
    if len(users) < 2:
        print(paint(t("user_delete_last"), YELLOW))
        return
    user = pick_user(app)
    if user is None:
        return
    if user.id == app.user_id:
        print(paint(t("user_delete_current"), RED))
        return

    answer = input(t("user_confirm_delete", name=user.name)).strip()
    if answer not in affirmatives():
        print(t("cancelled"))
        return
    app.delete_user(user.id)
    print(paint(t("user_deleted", name=user.name), YELLOW))


def sign_out_and_exit(app):
    """End the session. Returns True when it was actually ended.

    The caller returns to the sign-in screen, which is where the data stops
    being visible - signing out without going back would leave someone
    looking at what they had just signed out of.
    """
    if not app.current_user().has_password:
        print(paint(t("no_session"), YELLOW))
        return False

    print()
    answer = input(t("sign_out_confirm")).strip()
    if answer not in affirmatives():
        print(t("cancelled"))
        return False

    app.sign_out()
    print(paint(t("logged_out"), BOLD))
    return True


def change_role(app):
    """Promote or demote a user. Administrators only."""
    user = pick_user(app)
    if user is None:
        return
    if user.is_admin and app.admin_count() <= 1:
        print(paint(t("cannot_remove_last_admin"), RED))
        return
    app.set_admin(user.id, not user.is_admin)
    role = t("role_user") if user.is_admin else t("role_admin")
    print(paint(t("role_changed", name=user.name, role=role), BOLD))


def users_menu(app):
    """The users submenu.

    An ordinary user sees only their own password: everything else here
    reaches across people, which is what the role governs.
    """
    while True:
        admin = app.is_admin
        print(paint(f"\n{t('menu_users')}:", BOLD, CYAN))
        entries = [
            ("user_menu_view", show_users),
            ("user_menu_change_password", change_own_password),
        ]
        if admin:
            entries += [
                ("user_menu_add", add_user),
                ("user_menu_rename", rename_user),
                ("user_menu_password", set_user_password),
                ("user_menu_reset_password", reset_password),
                ("user_menu_role", change_role),
                ("user_menu_delete", delete_user),
            ]
        for index, (key, _) in enumerate(entries, start=1):
            print(f"{index}. {t(key)}")
        back = len(entries) + 1
        print(f"{back}. {t('back')}")
        if not admin:
            print(paint(t("admin_only_note"), DIM))

        choice = prompt_menu_choice(1, back)
        if choice == str(back):
            return
        if choice.isdigit() and 1 <= int(choice) <= len(entries):
            entries[int(choice) - 1][1](app)
        else:
            print(paint(t("invalid_choice", low=1, high=back), RED))


# ---------------------------------------------------------------------------
# Category rules
# ---------------------------------------------------------------------------


def show_rules(app):
    """Every rule, most specific first."""
    rules = app.category_rules()
    if not rules:
        print(paint(f"\n{t('no_rules')}", YELLOW))
        return

    patterns = [r.pattern for r in rules]
    targets = [f"{r.category}" + (f" / {r.subcategory}" if r.subcategory else "") for r in rules]
    w_pattern = max([len(t("field_rule_pattern"))] + [len(v) for v in patterns])
    w_target = max([len(t("field_category"))] + [len(v) for v in targets])
    total = 4 + w_pattern + 4 + w_target

    print(paint(f"\n{t('rules_title')}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{'#':<4}{t('field_rule_pattern'):<{w_pattern}}    {t('field_category'):<{w_target}}",
            BOLD,
        )
    )
    print("-" * total)
    for index in range(1, len(rules) + 1):
        print(f"{index:<4}{patterns[index - 1]:<{w_pattern}} -> {targets[index - 1]}")
    print("-" * total)


def add_rule(app):
    """Create a rule, saying first how much of the existing data it touches."""
    print(paint(f"\n{t('rule_menu_add')}", BOLD, CYAN))
    pattern = input(t("ask_rule_pattern"))
    if not pattern or pattern in cancels():
        print(t("cancelled"))
        return
    pattern = pattern.strip()
    if not pattern:
        print(paint(t("empty_description"), RED))
        return
    if app.rule_exists(pattern):
        print(paint(t("rule_exists"), RED))
        return

    # Said before the rule is saved: a pattern matching three hundred rows is
    # something to learn beforehand.
    count = app.count_matching(pattern)
    if count:
        print(paint(t("rule_would_match", count=count), DIM))
    else:
        print(paint(t("rule_matches_nothing"), YELLOW))

    kind = prompt_category_kind()
    category = prompt_category(app, kind)
    if not category:
        print(paint(t("budget_no_category"), RED))
        return
    subcategory = prompt_subcategory(app, kind, category)

    answer = input(t("rule_confirm")).strip()
    if answer not in affirmatives():
        print(t("cancelled"))
        return

    app.add_category_rule(pattern, category, kind, subcategory)
    print(paint(t("rule_added", pattern=pattern, category=category), BOLD))


def delete_rule(app):
    show_rules(app)
    rules = app.category_rules()
    if not rules:
        return
    index = prompt_index(len(rules), t("ask_number_rule"))
    if index is None:
        return
    removed = app.delete_category_rule(rules[index].id)
    print(paint(t("rule_deleted", pattern=removed.pattern), YELLOW))


def rules_menu(app):
    while True:
        print(paint(f"\n{t('menu_rules')}:", BOLD, CYAN))
        print(f"1. {t('rule_menu_view')}")
        print(f"2. {t('rule_menu_add')}")
        print(f"3. {t('rule_menu_delete')}")
        print(f"4. {t('back')}")

        choice = prompt_menu_choice(1, 4)
        if choice == "1":
            show_rules(app)
        elif choice == "2":
            add_rule(app)
        elif choice == "3":
            delete_rule(app)
        elif choice == "4":
            return
        else:
            print(paint(t("invalid_choice", low=1, high=4), RED))


# ---------------------------------------------------------------------------
# Importing
# ---------------------------------------------------------------------------

# Words typed at the preview, in either language, so the loop reads naturally
# whichever the interface is set to.
SELECT_ALL_WORDS = ("te gjitha", "all")
SELECT_NONE_WORDS = ("asnje", "none")
CONFIRM_WORDS = ("importo", "import")
CATEGORY_PREFIXES = ("k ", "c ")


def ask_import_columns(header, mapping):
    """Ask which column holds anything that was not recognised."""
    print(paint(f"\n{t('import_columns_found', columns=', '.join(sorted(mapping)))}", DIM))
    print()
    for index, name in enumerate(header, start=1):
        print(f"  {index}. {name}")

    for role in ("date", "amount", "description"):
        if role in mapping:
            continue
        if role == "amount" and ("debit" in mapping or "credit" in mapping):
            continue
        while True:
            raw = input(t("import_which_column", role=role)).strip()
            if raw == "0":
                break
            if raw.isdigit() and 1 <= int(raw) <= len(header):
                mapping[role] = int(raw) - 1
                break
            print(paint(t("invalid_number"), RED))
    return mapping


def preview_loop(app, candidates, separator, date_label):
    """Show the parsed rows and let them be adjusted before anything is written.

    Returns True to import, False to cancel. Nothing touches the database until
    this returns True.
    """
    while True:
        print_candidates(candidates, separator, date_label)
        print()
        print(paint(t("import_commands"), DIM))
        print_rows_guide(indent="  ")
        print(paint(t("import_cmd_rest"), DIM))
        for key in (
            "import_cmd_all",
            "import_cmd_none",
            "import_cmd_category",
            "import_cmd_import",
            "import_cmd_cancel",
        ):
            print(paint(t(key), DIM))

        print()
        choice = input(t("import_choose")).strip()

        if choice in cancels():
            return False
        if choice in CONFIRM_WORDS:
            if not any(c.will_import for c in candidates):
                print(paint(t("import_none_selected"), YELLOW))
                continue
            return True
        if choice.casefold() in SELECT_ALL_WORDS:
            for candidate in candidates:
                if candidate.importable:
                    candidate.selected = True
            continue
        if choice.casefold() in SELECT_NONE_WORDS:
            for candidate in candidates:
                candidate.selected = False
            continue

        lowered = choice.casefold()
        if any(lowered.startswith(prefix) for prefix in CATEGORY_PREFIXES):
            set_candidate_category(app, candidates, choice[2:].strip())
            continue

        positions = parse_positions(choice, len(candidates))
        if positions is not None:
            toggle_candidates(candidates, positions)
            continue

        print(paint(t("invalid_choice", low=1, high=len(candidates)), RED))


def toggle_candidates(candidates, positions):
    """Turn the named rows on or off.

    One row toggles. Several move together: if any of them is currently off
    they all go on, otherwise they all go off - so "5-13" reads as one
    decision about thirteen rows rather than thirteen separate reversals,
    which would leave a mixed selection looking untouched.
    """
    chosen = [candidates[position - 1] for position in positions]
    usable = [candidate for candidate in chosen if candidate.importable]
    if not usable:
        print(paint(t("import_row_unusable"), RED))
        return

    if len(usable) == 1:
        usable[0].selected = not usable[0].selected
        return

    turning_on = any(not candidate.selected for candidate in usable)
    for candidate in usable:
        candidate.selected = turning_on


def set_candidate_category(app, candidates, raw):
    """Set the category on one previewed row."""
    if not raw.isdigit():
        print(paint(t("invalid_number"), RED))
        return
    index = int(raw)
    if not 1 <= index <= len(candidates):
        print(paint(t("invalid_number"), RED))
        return

    candidate = candidates[index - 1]
    if candidate.kind == TRANSFER:
        print(paint(t("import_row_unusable"), YELLOW))
        return
    category = prompt_category(app, candidate.kind, current=candidate.category)
    candidate.category = category


def report_reconciliation(result):
    """Print whether the parse agreed with the bank's own totals."""
    if result.ok:
        print(paint(t("import_reconciled", count=result.checked), BOLD, GREEN))
        return True

    print(paint(t("import_reconcile_failed"), RED))
    for date, computed, stated in result.mismatches[:5]:
        print(paint(t("import_reconcile_row", date=date, computed=computed, stated=stated), RED))
    if False in (result.debit_ok, result.credit_ok, result.count_ok):
        print(
            paint(
                t(
                    "import_reconcile_totals",
                    debit="ok" if result.debit_ok is not False else "x",
                    credit="ok" if result.credit_ok is not False else "x",
                    count="ok" if result.count_ok is not False else "x",
                ),
                RED,
            )
        )
    return False


def import_statement(app, raw, path):
    """Import a recognised bank statement.

    Refuses outright when the arithmetic does not agree. A statement that does
    not reconcile has been misread somewhere, and the mistake would be money
    that is wrong in a way nothing later reveals.
    """
    from .statements import parse_statement, reconcile, to_candidates

    print(paint(t("import_statement_found"), BOLD, CYAN))
    statement = parse_statement(raw)
    if statement.opening is not None:
        print(paint(t("import_opening", amount=money(statement.opening)), DIM))

    if not report_reconciliation(reconcile(statement)):
        print(paint(t("import_refused"), YELLOW))
        return

    account_id = None
    if app.has_accounts():
        print(paint(f"\n{t('import_ask_account')}", BOLD))
        account_id = prompt_account(app)

    candidates = to_candidates(statement, account_id=account_id)
    print(paint(t("import_deposits_note"), DIM))
    filled = app.apply_rules(candidates)
    if filled:
        print(paint(t("rules_applied", count=filled), DIM))
    mark_duplicates_for(app, candidates)

    if not preview_loop(app, candidates, ".", "dd/mm/yyyy"):
        print(paint(t("import_cancelled"), YELLOW))
        return

    finish_import(app, candidates)


def mark_duplicates_for(app, candidates):
    from .importing import mark_duplicates

    mark_duplicates(candidates, app.transactions())


def finish_import(app, candidates):
    from .importing import commit

    try:
        count = commit(app, candidates)
    except Exception as error:
        print(paint(t("import_failed", error=error), RED))
        return
    print(paint(t("import_done", count=count), BOLD))


def choose_import_file(typed):
    """Find the file someone named, asking which when several match.

    The extension need not be typed: a bare name matches every file of that
    name, so nobody has to remember whether the bank sent HTML or CSV. Where
    that turns up more than one, the choice is theirs rather than a guess.
    """
    from .locations import find_import_candidates, folder_label, search_folders

    matches = find_import_candidates(typed)
    if not matches:
        folders = ", ".join(folder_label(f) for f in search_folders())
        print(paint(t("import_not_found", name=typed, folders=folders), RED))
        return None

    if len(matches) == 1:
        found, where = matches[0]
        print(paint(t("import_found", name=os.path.basename(found), folder=where), DIM))
        return found

    print(paint(f"\n{t('import_which_file')}", BOLD))
    for index, (found, where) in enumerate(matches, start=1):
        print(t("import_file_option", number=index, name=os.path.basename(found), folder=where))

    while True:
        raw = input(t("ask_which_file")).strip()
        if raw in cancels():
            print(t("cancelled"))
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(matches):
            return matches[int(raw) - 1][0]
        print(paint(t("invalid_number"), RED))


def read_import_file(path):
    """Read a file, explaining in plain words when it cannot be.

    An errno and a English message from the operating system tells someone
    nothing they can act on, and not in the language they chose.
    """
    name = os.path.basename(path)
    if os.path.isdir(path):
        print(paint(t("import_is_folder", name=name), RED))
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except FileNotFoundError:
        from .locations import folder_label, search_folders

        folders = ", ".join(folder_label(f) for f in search_folders())
        print(paint(t("import_not_found", name=name, folders=folders), RED))
    except (PermissionError, IsADirectoryError):
        print(paint(t("import_unreadable", name=name), RED))
    except OSError:
        print(paint(t("import_unreadable", name=name), RED))
    return None


def import_from_file(app, path=None):
    """Read a file, show what it contains, and import what is approved.

    `path` skips the filename prompt, for the command-line flag. Everything
    after that is identical: the preview is the point of the feature, so there
    is no way to import without seeing what will be written.
    """
    from .importing import (
        ImportError_,
        build_candidates,
        guess_columns,
        has_usable_amount,
        mark_duplicates,
        read_rows,
    )

    print(paint(f"\n{t('import_title')}", BOLD, CYAN))
    if path is None:
        from .locations import folder_label, search_folders

        # Named as they actually are on this machine rather than translated.
        # Telling someone to use a folder called "Dokumente" when Windows
        # calls it "Documents" sends them looking for one that is not there.
        where = ", ".join(folder_label(f) for f in search_folders()[1:])
        hint("hint_cancel_task")
        print(paint(f"  {t('import_where', folders=where)}", DIM))
        typed = input(t("ask_import_path")).strip()
        if not typed or typed in cancels():
            print(t("cancelled"))
            return
        path = choose_import_file(typed)
        if path is None:
            return

    from .statements import looks_like_teb

    raw = read_import_file(path)
    if raw is None:
        return

    # A bank statement is read by its own reader, which knows the column
    # meanings and can check itself against the totals printed on it.
    if looks_like_teb(raw):
        try:
            import_statement(app, raw, path)
        except ImportError_ as error:
            print(paint(t("import_failed", error=error), RED))
        return

    try:
        header, rows, _encoding = read_rows(raw)
    except ImportError_ as error:
        print(paint(t("import_failed", error=error), RED))
        return

    print(paint(t("import_read", count=len(rows), path=path), BOLD))

    mapping = guess_columns(header)
    if "date" not in mapping or not has_usable_amount(mapping):
        mapping = ask_import_columns(header, mapping)
    if "date" not in mapping or not has_usable_amount(mapping):
        print(paint(t("import_no_columns"), RED))
        return

    # Asked once. A statement comes from one account, so setting it per row
    # would be seventeen answers to the same question.
    account_id = None
    if app.has_accounts():
        print(paint(f"\n{t('import_ask_account')}", BOLD))
        account_id = prompt_account(app)

    candidates, separator, detected = build_candidates(header, rows, mapping, account_id=account_id)
    # Applied before the preview, so a matched row arrives with its category
    # already filled in and can still be changed like any other.
    filled = app.apply_rules(candidates)
    if filled:
        print(paint(t("rules_applied", count=filled), DIM))
    mark_duplicates(candidates, app.transactions())

    if not preview_loop(app, candidates, separator, detected[1] if detected else None):
        print(paint(t("import_cancelled"), YELLOW))
        return

    finish_import(app, candidates)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def show_recent_history(app):
    print_history(app.history(limit=25), names=app.reference_names())


def show_transaction_history(app):
    """Pick a transaction and show everything that has happened to it."""
    chosen = pick(app, t("ask_number_edit"))
    if chosen is None:
        return
    entries = app.transaction_history(chosen.id)
    print_history(entries, t("history_for", number=chosen.id), names=app.reference_names())


def history_menu(app):
    print(paint(f"\n{t('menu_history')}:", BOLD, CYAN))
    print(f"1. {t('history_menu_recent')}")
    print(f"2. {t('history_menu_one')}")
    print(f"3. {t('back')}")

    choice = prompt_menu_choice(1, 3)
    if choice == "1":
        show_recent_history(app)
    elif choice == "2":
        show_transaction_history(app)
    elif choice == "3":
        return
    else:
        print(paint(t("invalid_choice", low=1, high=3), RED))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def prompt_name(message_key, **kwargs):
    """Ask for a category or subcategory name. None if cancelled.

    Validated exactly as typed, like the prompts used when adding a
    transaction - a name is stored as written or not at all.
    """
    while True:
        typed = input(t(message_key, **kwargs))
        if typed in cancels():
            print(t("cancelled"))
            return None
        if not valid_name(typed):
            print(paint(t("invalid_name"), RED))
            continue
        return typed


def prompt_category_kind():
    """Ask whether a category belongs to income or expenses."""
    print(f"\n{t('pick_category_kind')}")
    return prompt_kind()


def show_categories(app):
    """Every category grouped by kind, with its subcategories underneath."""
    printed = False
    for kind in (INCOME, EXPENSE):
        categories = app.categories(kind)
        if not categories:
            continue
        printed = True
        print(paint(f"\n{type_label(kind)}", BOLD, type_color(kind)))
        for index, category in enumerate(categories, start=1):
            print(f"  {index}. {category.name}")
            for subcategory in app.subcategories(category.id):
                print(paint(f"       {subcategory.name}", DIM))
    if not printed:
        print(paint(f"\n{t('no_categories')}", YELLOW))


def pick_category(app, kind=None):
    """List categories and return the chosen one, or None."""
    kind = kind or prompt_category_kind()
    categories = app.categories(kind)
    if not categories:
        print(paint(t("no_categories"), YELLOW))
        return None
    print(paint(f"\n{type_label(kind)}", BOLD, type_color(kind)))
    for index, category in enumerate(categories, start=1):
        print(f"  {index}. {category.name}")
    index = prompt_index(len(categories), t("ask_number_category"))
    return categories[index] if index is not None else None


def pick_subcategory(app, category):
    """List a category's subcategories and return the chosen one, or None."""
    subcategories = app.subcategories(category.id)
    if not subcategories:
        print(paint(t("no_subcategories"), YELLOW))
        return None
    print(paint(f"\n{category.name}", BOLD))
    for index, subcategory in enumerate(subcategories, start=1):
        print(f"  {index}. {subcategory.name}")
    index = prompt_index(len(subcategories), t("ask_number_subcategory"))
    return subcategories[index] if index is not None else None


def add_category(app):
    kind = prompt_category_kind()
    name = prompt_name("ask_new_category")
    if name is None:
        return
    if app.category_exists(name, kind):
        print(paint(t("category_exists"), RED))
        return
    app.add_category(name, kind)
    print(paint(t("category_added", name=name), BOLD))


def rename_category(app):
    category = pick_category(app)
    if category is None:
        return
    name = prompt_name("ask_rename", current=category.name)
    if name is None:
        return
    existing = app.db.category_by_name(name, category.kind)
    if existing is not None and existing.id != category.id:
        print(paint(t("category_exists"), RED))
        return
    app.rename_category(category.id, name)
    print(paint(t("category_renamed", name=name), BOLD))


def delete_category(app):
    category = pick_category(app)
    if category is None:
        return

    subs = len(app.subcategories(category.id))
    affected = len(app.transactions(category_id=category.id))
    answer = input(
        t("confirm_delete_category", name=category.name, subs=subs, count=affected)
    ).strip()
    if answer not in affirmatives():
        print(t("cancelled"))
        return

    removed, count = app.delete_category(category.id)
    print(paint(t("category_deleted", name=removed.name, count=count), YELLOW))


def add_subcategory(app):
    category = pick_category(app)
    if category is None:
        return
    name = prompt_name("ask_new_subcategory")
    if name is None:
        return
    if app.subcategory_exists(name, category.id):
        print(paint(t("subcategory_exists"), RED))
        return
    app.add_subcategory(name, category.id)
    print(paint(t("subcategory_added", name=name, parent=category.name), BOLD))


def rename_subcategory(app):
    category = pick_category(app)
    if category is None:
        return
    subcategory = pick_subcategory(app, category)
    if subcategory is None:
        return
    name = prompt_name("ask_rename", current=subcategory.name)
    if name is None:
        return
    existing = app.db.subcategory_by_name(name, category.id)
    if existing is not None and existing.id != subcategory.id:
        print(paint(t("subcategory_exists"), RED))
        return
    app.rename_subcategory(subcategory.id, name)
    print(paint(t("subcategory_renamed", name=name), BOLD))


def delete_subcategory(app):
    category = pick_category(app)
    if category is None:
        return
    subcategory = pick_subcategory(app, category)
    if subcategory is None:
        return

    affected = len(app.transactions(subcategory_id=subcategory.id))
    answer = input(t("confirm_delete_subcategory", name=subcategory.name, count=affected)).strip()
    if answer not in affirmatives():
        print(t("cancelled"))
        return

    removed, count = app.delete_subcategory(subcategory.id)
    print(paint(t("subcategory_deleted", name=removed.name, count=count), YELLOW))


def category_menu(app):
    while True:
        print(paint(f"\n{t('menu_categories')}:", BOLD, CYAN))
        print(f"1. {t('category_menu_view')}")
        print(f"2. {t('category_menu_add')}")
        print(f"3. {t('category_menu_rename')}")
        print(f"4. {t('category_menu_delete')}")
        print(f"5. {t('category_menu_add_sub')}")
        print(f"6. {t('category_menu_rename_sub')}")
        print(f"7. {t('category_menu_delete_sub')}")
        print(f"8. {t('back')}")

        choice = prompt_menu_choice(1, 8)
        if choice == "1":
            show_categories(app)
        elif choice == "2":
            add_category(app)
        elif choice == "3":
            rename_category(app)
        elif choice == "4":
            delete_category(app)
        elif choice == "5":
            add_subcategory(app)
        elif choice == "6":
            rename_subcategory(app)
        elif choice == "7":
            delete_subcategory(app)
        elif choice == "8":
            return
        else:
            print(paint(t("invalid_choice", low=1, high=8), RED))


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def show_budgets(app, year=None, month=None):
    if year is None or month is None:
        year, month = month_of(today())
    print_budgets(
        all_statuses(app.budgets(), app.category_name_map(), app.transactions(), year, month),
        year,
        month,
    )


def set_budget(app):
    category = prompt_category(app, EXPENSE)
    if not category:
        print(paint(t("budget_no_category"), RED))
        return
    amount = prompt_amount()
    app.set_budget(category, amount)
    print(paint(t("budget_saved", category=category), BOLD))


def delete_budget(app):
    show_budgets(app)
    budgets = app.budgets()
    if not budgets:
        return
    year, month = month_of(today())
    statuses = all_statuses(budgets, app.category_name_map(), app.transactions(), year, month)
    index = prompt_index(len(statuses), t("ask_number_budget"))
    if index is None:
        return
    chosen = statuses[index]
    app.delete_budget(chosen.category_id)
    print(paint(t("budget_deleted", category=chosen.category), BOLD))


def budget_menu(app):
    while True:
        print(paint(f"\n{t('menu_budgets')}:", BOLD, CYAN))
        print(f"1. {t('budget_menu_view')}")
        print(f"2. {t('budget_menu_set')}")
        print(f"3. {t('budget_menu_delete')}")
        print(f"4. {t('back')}")

        choice = prompt_menu_choice(1, 4)
        if choice == "1":
            show_budgets(app)
        elif choice == "2":
            set_budget(app)
        elif choice == "3":
            delete_budget(app)
        elif choice == "4":
            return
        else:
            print(paint(t("invalid_choice", low=1, high=4), RED))


# ---------------------------------------------------------------------------
# Recurring
# ---------------------------------------------------------------------------


def show_recurring(app):
    print_recurring(
        app.recurring_rules(),
        today(),
        app.category_name_map(),
        {a.id: a.name for a in app.accounts()},
    )


def add_recurring(app):
    print(paint(f"\n{t('adding_recurring')}", BOLD))
    kind = prompt_kind()
    description = prompt_description()
    amount = prompt_amount()
    category = prompt_category(app, kind)
    subcategory = prompt_subcategory(app, kind, category)
    # A rule with no account would keep generating unassigned transactions.
    account_id = prompt_account(app) if app.has_accounts() else None

    names = list(FREQUENCIES.keys())
    print(f"\n{t('field_frequency')}:")
    for index, name in enumerate(names, start=1):
        print(f"  {index}. {frequency_label(name)}")
    while True:
        raw = input(t("choose_frequency", count=len(names))).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(names):
            frequency = names[int(raw) - 1]
            break
        print(paint(t("invalid_type"), RED))

    print(paint(f"\n{t('first_date')}", DIM))
    starts_on = prompt_date()

    app.add_recurring_rule(
        kind,
        description,
        amount,
        frequency,
        starts_on,
        category=category,
        subcategory=subcategory,
        account_id=account_id,
    )
    print(paint(t("recurring_added"), BOLD))
    generated = app.process_recurring()
    if generated:
        print(paint(t("generated", count=len(generated)), BOLD))


def delete_recurring(app):
    show_recurring(app)
    rules = app.recurring_rules()
    if not rules:
        return
    index = prompt_index(len(rules), t("ask_number_recurring"))
    if index is None:
        return
    removed = app.delete_recurring_rule(rules[index].id)
    print(paint(t("recurring_deleted", description=removed.description), BOLD))


def generate_recurring(app):
    generated = app.process_recurring()
    if generated:
        print(paint(t("generated", count=len(generated)), BOLD))
    else:
        print(t("nothing_due"))


def recurring_menu(app):
    while True:
        print(paint(f"\n{t('recurring_title')}", BOLD, CYAN))
        print(f"1. {t('recurring_menu_view')}")
        print(f"2. {t('recurring_menu_add')}")
        print(f"3. {t('recurring_menu_delete')}")
        print(f"4. {t('recurring_menu_generate')}")
        print(f"5. {t('back')}")

        choice = prompt_menu_choice(1, 5)
        if choice == "1":
            show_recurring(app)
        elif choice == "2":
            add_recurring(app)
        elif choice == "3":
            delete_recurring(app)
        elif choice == "4":
            generate_recurring(app)
        elif choice == "5":
            return
        else:
            print(paint(t("invalid_choice", low=1, high=5), RED))


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

MENU_ITEMS = [
    ("menu_add_income", lambda app: add_transaction(app, INCOME)),
    ("menu_add_expense", lambda app: add_transaction(app, EXPENSE)),
    ("menu_view", show_transactions),
    ("menu_balance", show_balance),
    ("menu_edit", edit_transaction),
    ("menu_delete", delete_transaction),
    ("menu_filter", filter_menu),
    ("menu_search", search_transactions),
    ("menu_report", report_menu),
    ("menu_charts", charts_menu),
    ("menu_categories", category_menu),
    ("menu_budgets", budget_menu),
    ("menu_accounts", account_menu),
    ("menu_transfer", add_transfer),
    ("menu_recurring", recurring_menu),
    ("menu_export", export_to_csv),
    ("menu_rules", rules_menu),
    ("menu_users", users_menu),
    ("menu_import", import_from_file),
    ("menu_history", history_menu),
    ("menu_logout", None),
]


def run_menu(app):
    """The interactive loop.

    Returns True when the program should stop, False to return to the sign-in
    screen. Leaving the program is offered there rather than here, so signing
    out and shutting down are two decisions rather than one.
    """
    print()
    print(paint(t("welcome"), BOLD, CYAN))
    # Named only when there is more than one, so a single-person installation
    # never sees a concept it does not use.
    if len(app.users()) > 1:
        print(paint(t("user_current", name=app.current_user().name), DIM))
    count = len(MENU_ITEMS)

    while True:
        print(paint(f"\n{t('menu')}", BOLD))
        for index, (key, _) in enumerate(MENU_ITEMS, start=1):
            # The last entry signs out where there is a sign-in screen to
            # return to, and simply leaves where there is not. It says which.
            if key == "menu_logout" and not app.sign_in_applies():
                print(f"{index}. {t('exit_program')}")
            else:
                print(f"{index}. {t(key)}")

        choice = prompt_menu_choice(1, count)
        if choice == str(count):
            # With one user and no password there is no sign-in screen to
            # return to, so the same entry simply leaves.
            if not app.sign_in_applies():
                print()
                print(paint(t("goodbye"), CYAN))
                return True
            if sign_out_and_exit(app):
                return False
            continue
        if choice.isdigit() and 1 <= int(choice) < count:
            # A menu action returns True only to stop the program, which
            # signing out does - it would otherwise leave someone looking at
            # the data they had just signed out of.
            if MENU_ITEMS[int(choice) - 1][1](app):
                return
        else:
            print(paint(t("invalid_choice", low=1, high=count), RED))
