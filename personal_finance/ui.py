"""Nderfaqja interaktive / Interactive interface.

Everything that reads from stdin lives here. The prompt helpers are shared
between adding and editing so both paths validate input identically.

Rows are numbered 1..N on screen and mapped back to database ids internally.
The two must not be conflated: ids develop gaps as things are deleted, and a
menu that showed them would look broken.
"""

from decimal import Decimal, InvalidOperation

from .accounts import balances_for, count_unassigned, find_account
from .budgets import all_statuses
from .colors import BOLD, CYAN, DIM, RED, YELLOW, paint, type_color
from .config import CLEAR_MARKER
from .dates import (
    current_date_str,
    format_date,
    month_of,
    parse_date,
    parse_month,
    previous_month,
    today,
)
from .display import (
    category_path,
    print_accounts,
    print_budget_warning,
    print_budgets,
    print_monthly_report,
    print_recurring,
    print_summary,
    print_transactions,
)
from .i18n import affirmatives, cancels, frequency_label, negatives, t, type_label
from .models import ACCOUNT_KINDS, parse_amount, valid_name
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


def prompt_description(current=None):
    while True:
        if current is None:
            value = input(t("ask_description")).strip()
        else:
            value = input(t("ask_description_keep", current=current)).strip()
            if not value:
                return current
        if value:
            return value
        print(paint(t("empty_description"), RED))


def prompt_amount(current=None):
    while True:
        if current is None:
            raw = input(t("ask_amount"))
        else:
            raw = input(t("ask_amount_keep", current=f"{current:.2f}"))
            if not raw.strip():
                return current
        amount = parse_amount(raw)
        if amount is None:
            print(paint(t("invalid_amount"), RED))
            continue
        return amount


def prompt_date(current=None):
    """Ask for a date, offering today as a shortcut when adding."""
    if current is None:
        while True:
            # Compared exactly as typed - not lowercased, not stripped. Both
            # would quietly accept something the user did not write: "PO", or
            # " po " with spaces around it.
            choice = input(t("ask_today"))
            if choice in affirmatives():
                return current_date_str()
            if choice in negatives():
                break
            print(paint(t("yes_no_only"), RED))

    while True:
        if current is None:
            raw = input(t("ask_date")).strip()
        else:
            raw = input(t("ask_date_keep", current=current)).strip()
            if not raw:
                return current
        if parse_date(raw) is not None:
            return raw
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


def prompt_category(app, kind, current=None):
    """Ask for a category, offering the ones already defined.

    A name typed here that does not exist yet is created when the transaction
    is saved, so entry never stalls on defining a category first.
    """
    options = app.category_names(kind)
    if options:
        print(f"\n{t('suggested_categories')}")
        for index, name in enumerate(options, start=1):
            print(f"  {index}. {name}")
        print(paint(f"  {t('own_category_hint')}", DIM))

    while True:
        # Validated exactly as typed. Stripping first would silently accept
        # " Ushqim ", and the stored name would not be the one entered.
        typed = (
            input(t("ask_category"))
            if current is None
            else input(t("ask_category_keep", current=current))
        )

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
        print(paint(f"  {t('own_subcategory_hint')}", DIM))
    if current is None:
        print(paint(f"  {t('skip_subcategory_hint')}", DIM))

    while True:
        typed = (
            input(t("ask_subcategory"))
            if current is None
            else input(t("ask_subcategory_keep", current=current or t("no_subcategory")))
        )

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
        print(paint(f"  {t('skip_account_hint')}", DIM))

    current_name = None
    if current is not None:
        match = [a for a in accounts if a.id == current]
        current_name = match[0].name if match else None

    while True:
        if current is None:
            raw = input(t(message_key)).strip()
            if not raw and allow_skip:
                return None
        else:
            raw = input(
                t("ask_account_keep", current=current_name or t("no_account_display"))
            ).strip()
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
    print(paint(f"\n{t('adding', type=type_label(kind))}", BOLD))
    description = prompt_description()
    amount = prompt_amount()
    occurred_on = prompt_date()
    category = prompt_category(app, kind)
    subcategory = prompt_subcategory(app, kind, category)
    account_id = prompt_account(app) if app.has_accounts() else None

    transaction = app.add_transaction(
        kind, description, amount, occurred_on, category, subcategory, account_id
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


def delete_transaction(app):
    chosen = pick(app, t("ask_number_delete"))
    if chosen is None:
        return
    removed = app.delete_transaction(chosen.id)
    print(
        paint(
            t(
                "deleted",
                date=removed.occurred_on,
                type=type_label(removed.kind),
                description=removed.description,
                category=category_path(removed),
            ),
            BOLD,
        )
    )


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
    path = input(t("ask_export_path")).strip()
    if not path:
        print(t("cancelled"))
        return

    # Resolved before the check, so the prompt names the file that would
    # actually be replaced rather than the name that was typed.
    target = resolve_export_path(path)
    if os.path.exists(target):
        answer = input(t("export_overwrite", path=target)).strip().lower()
        if answer not in affirmatives():
            print(t("cancelled"))
            return

    answer = input(t("ask_export_filter")).strip().lower()
    if answer in affirmatives():
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
    ("menu_categories", category_menu),
    ("menu_budgets", budget_menu),
    ("menu_accounts", account_menu),
    ("menu_transfer", add_transfer),
    ("menu_recurring", recurring_menu),
    ("menu_export", export_to_csv),
    ("menu_exit", None),
]


def run_menu(app):
    """The interactive loop."""
    print(paint(t("welcome"), BOLD, CYAN))
    count = len(MENU_ITEMS)

    while True:
        print(paint(f"\n{t('menu')}", BOLD))
        for index, (key, _) in enumerate(MENU_ITEMS, start=1):
            print(f"{index}. {t(key)}")

        choice = prompt_menu_choice(1, count)
        if choice == str(count):
            print(paint(t("goodbye"), CYAN))
            return
        if choice.isdigit() and 1 <= int(choice) < count:
            MENU_ITEMS[int(choice) - 1][1](app)
        else:
            print(paint(t("invalid_choice", low=1, high=count), RED))
