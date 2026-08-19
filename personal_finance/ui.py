"""Nderfaqja interaktive / Interactive interface.

Everything that reads from stdin lives here. The prompt helpers are shared
between adding and editing so both paths validate input identically.
"""

from decimal import Decimal, InvalidOperation

from .accounts import balances_for, find_account
from .budgets import all_statuses, check_after_adding
from .colors import BOLD, CYAN, DIM, RED, YELLOW, paint
from .config import (
    ACCOUNT_TYPES,
    CLEAR_MARKER,
    DEFAULT_CATEGORY,
    EXPENSE,
    INCOME,
    SUGGESTED_SUBCATEGORIES,
    TRANSFER,
)
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
from .i18n import affirmatives, frequency_label, negatives, t, type_label
from .models import RecurringRule, parse_amount
from .recurring import FREQUENCIES
from .reports import (
    calculate_totals,
    filter_by_dates,
    known_subcategories,
    month_report,
    search,
    sort_by_date,
)

CANCEL_KEYS = ("a",)


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
            choice = input(t("ask_today")).strip().lower()
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


def prompt_category(options, current=None):
    print(f"\n{t('suggested_categories')}")
    for i, option in enumerate(options, start=1):
        print(f"  {i}. {option}")
    print(paint(f"  {t('own_category_hint')}", DIM))

    while True:
        if current is None:
            raw = input(t("ask_category")).strip()
        else:
            raw = input(t("ask_category_keep", current=current)).strip()
            if not raw:
                return current
        if not raw:
            return DEFAULT_CATEGORY
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1]
            print(paint(t("invalid_category_number"), RED))
            continue
        return raw


def prompt_subcategory(app, trans_type, category, current=None):
    """Ask for an optional subcategory.

    When adding, pressing Enter means "no subcategory". When editing, Enter
    keeps the current value and a lone dash clears it - Enter cannot mean both
    "keep" and "clear", so clearing needs its own key.
    """
    options = known_subcategories(app.transactions, trans_type, category, SUGGESTED_SUBCATEGORIES)

    if options:
        print(f"\n{t('suggested_subcategories')}")
        for i, option in enumerate(options, start=1):
            print(f"  {i}. {option}")
        print(paint(f"  {t('own_subcategory_hint')}", DIM))
    if current is None:
        print(paint(f"  {t('skip_subcategory_hint')}", DIM))

    while True:
        if current is None:
            raw = input(t("ask_subcategory")).strip()
            if not raw:
                return ""
        else:
            raw = input(t("ask_subcategory_keep", current=current or t("no_subcategory")))
            raw = raw.strip()
            if not raw:
                return current
            if raw == CLEAR_MARKER:
                return ""

        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1]
            print(paint(t("invalid_subcategory_number"), RED))
            continue
        return raw


def prompt_type(current=None):
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


def prompt_account(app, current=None, message_key="ask_account", allow_skip=True):
    """Ask which account a transaction belongs to.

    Returns "" for no account. Never called when no accounts exist, so a user
    who does not use them is never asked.
    """
    names = [a.emri for a in app.accounts]
    print(f"\n{t('accounts_title')}")
    for i, name in enumerate(names, start=1):
        print(f"  {i}. {name}")
    if allow_skip and current is None:
        print(paint(f"  {t('skip_account_hint')}", DIM))

    while True:
        if current is None:
            raw = input(t(message_key)).strip()
            if not raw and allow_skip:
                return ""
        else:
            raw = input(t("ask_account_keep", current=current or "-")).strip()
            if not raw:
                return current
            if raw == CLEAR_MARKER and allow_skip:
                return ""

        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(names):
                return names[index - 1]
            print(paint(t("invalid_account_number"), RED))
            continue

        matched = find_account(app.accounts, raw)
        if matched is not None:
            return matched.emri
        print(paint(t("invalid_account_number"), RED))


def prompt_account_type(current=None):
    """Ask whether an account is cash, a bank account, or a card."""
    print(f"\n{t('field_type')}:")
    for i, name in enumerate(ACCOUNT_TYPES, start=1):
        print(f"  {i}. {name}")
    while True:
        raw = input(t("ask_account_type", count=len(ACCOUNT_TYPES))).strip()
        if not raw and current is not None:
            return current
        if raw.isdigit() and 1 <= int(raw) <= len(ACCOUNT_TYPES):
            return ACCOUNT_TYPES[int(raw) - 1]
        print(paint(t("invalid_type"), RED))


def prompt_opening_balance(current=None):
    """Ask for an opening balance.

    Unlike a transaction amount this may be negative - a credit card usually
    starts out owing money - so it is not validated with parse_amount.
    """
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
    """Ask for a 1-based number within range. Returns a 0-based index or None."""
    raw = input(message).strip().lower()
    if raw in CANCEL_KEYS:
        print(t("cancelled"))
        return None
    try:
        number = int(raw)
        if number < 1 or number > count:
            raise ValueError
    except ValueError:
        print(paint(t("invalid_number"), RED))
        return None
    return number - 1


def prompt_menu_choice(low, high):
    raw = input(t("choose", range=f"{low}-{high}")).strip()
    return raw


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def numbered(transactions, subset=None):
    """Pair transactions with their 1-based position in the full list."""
    positions = {id(x): i for i, x in enumerate(transactions, start=1)}
    items = subset if subset is not None else transactions
    return [(positions.get(id(x), 0), x) for x in items]


def show_transactions(app):
    print_transactions(numbered(app.transactions, sort_by_date(app.transactions)))


def show_balance(app):
    print_summary(app.transactions, calculate_totals(app.transactions))
    if app.has_accounts():
        print_accounts(balances_for(app.accounts, app.transactions))


def add_transaction(app, trans_type):
    print(paint(f"\n{t('adding', type=type_label(trans_type))}", BOLD))
    description = prompt_description()
    amount = prompt_amount()
    date = prompt_date()
    category = prompt_category(app.categories_for(trans_type))
    subcategory = prompt_subcategory(app, trans_type, category)
    # Asked only when accounts exist, so a user who does not use them is never
    # prompted.
    account = prompt_account(app) if app.has_accounts() else ""

    transaction = app.add_transaction(
        trans_type, description, amount, date, category, subcategory, account
    )
    print(paint(t("added", type=type_label(trans_type)), BOLD))
    print_budget_warning(check_after_adding(app.budgets, app.transactions, transaction))


def edit_transaction(app):
    show_transactions(app)
    if not app.transactions:
        return
    index = prompt_index(len(app.transactions), t("ask_number_edit"))
    if index is None:
        return

    transaction = app.transactions[index]
    print(paint(f"\n{t('editing', number=index + 1)}", BOLD))
    print(paint(t("press_enter_keep"), DIM))

    print(f"\n{t('field_type')}:")
    new_type = prompt_type(current=transaction.lloji)
    new_description = prompt_description(current=transaction.pershkrimi)
    new_amount = prompt_amount(current=transaction.shuma)
    new_date = prompt_date(current=transaction.data)
    new_category = prompt_category(app.categories_for(new_type), current=transaction.kategoria)
    # Pass the existing subcategory only when the category is unchanged; moving
    # a transaction to a different category makes the old subcategory
    # meaningless, so it is asked for fresh.
    current_sub = transaction.nenkategoria if new_category == transaction.kategoria else None
    new_subcategory = prompt_subcategory(app, new_type, new_category, current=current_sub)
    changes = {
        "lloji": new_type,
        "pershkrimi": new_description,
        "shuma": new_amount,
        "data": new_date,
        "kategoria": new_category,
        "nenkategoria": new_subcategory,
    }
    if app.has_accounts():
        changes["llogaria"] = prompt_account(app, current=transaction.llogaria or None)

    app.update_transaction(index, **changes)
    print(paint(t("edited"), BOLD))


def delete_transaction(app):
    show_transactions(app)
    if not app.transactions:
        return
    index = prompt_index(len(app.transactions), t("ask_number_delete"))
    if index is None:
        return
    removed = app.delete_transaction(index)
    print(
        paint(
            t(
                "deleted",
                date=removed.data,
                type=type_label(removed.lloji),
                description=removed.pershkrimi,
                category=category_path(removed),
            ),
            BOLD,
        )
    )


def show_filtered(app, start, end, title):
    matches = sort_by_date(filter_by_dates(app.transactions, start, end))
    print_transactions(numbered(app.transactions, matches), title)
    if matches:
        print_summary(matches, calculate_totals(matches), t("filter_totals"))


def filter_single_date(app):
    while True:
        raw = input(t("filter_date")).strip()
        if raw.lower() in CANCEL_KEYS:
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
        raw = input(t("filter_start")).strip()
        if raw.lower() in CANCEL_KEYS:
            print(t("cancelled"))
            return
        start = parse_date(raw)
        if start is None:
            print(paint(t("invalid_date"), RED))
            continue
        break

    while True:
        raw = input(t("filter_end")).strip()
        if raw.lower() in CANCEL_KEYS:
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
        app, start, end, t("transactions_between", start=format_date(start), end=format_date(end))
    )


def search_transactions(app):
    term = input(t("ask_search")).strip()
    matches = sort_by_date(search(app.transactions, term))
    print_transactions(numbered(app.transactions, matches), t("transactions_matching", term=term))
    if matches:
        print_summary(matches, calculate_totals(matches), t("filter_totals"))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def show_month_report(app, year, month):
    print_monthly_report(month_report(app.transactions, year, month))


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
        prev_year, prev_month = previous_month(year, month)
        show_month_report(app, prev_year, prev_month)
    elif choice == "3":
        raw = input(t("ask_month")).strip()
        parsed = parse_month(raw)
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
    print_accounts(balances_for(app.accounts, app.transactions))


def add_account(app):
    print(paint(f"\n{t('adding_account')}", BOLD))
    while True:
        name = input(t("ask_account_name")).strip()
        if not name:
            print(paint(t("empty_description"), RED))
            continue
        if find_account(app.accounts, name) is not None:
            print(paint(t("account_exists"), RED))
            continue
        break

    account_type = prompt_account_type()
    opening = prompt_opening_balance()

    app.add_account(name, account_type, opening)
    print(paint(t("account_added", name=name), BOLD))


def edit_account(app):
    show_accounts(app)
    if not app.accounts:
        # The list above may still show an unassigned row, so returning in
        # silence here looked like the menu was ignoring the choice.
        print(paint(t("no_accounts_to_change"), YELLOW))
        return
    index = prompt_index(len(app.accounts), t("ask_number_account"))
    if index is None:
        return

    account = app.accounts[index]
    print(paint(t("press_enter_keep"), DIM))

    while True:
        name = input(t("ask_account_name_keep", current=account.emri)).strip()
        if not name:
            name = account.emri
            break
        existing = find_account(app.accounts, name)
        if existing is not None and existing is not account:
            print(paint(t("account_exists"), RED))
            continue
        break

    account_type = prompt_account_type(current=account.lloji)
    opening = prompt_opening_balance(current=account.gjendja_fillestare)

    app.update_account(index, name=name, account_type=account_type, opening=opening)
    print(paint(t("account_updated"), BOLD))


def delete_account(app):
    show_accounts(app)
    if not app.accounts:
        print(paint(t("no_accounts_to_delete"), YELLOW))
        return
    index = prompt_index(len(app.accounts), t("ask_number_account"))
    if index is None:
        return
    removed, touched = app.delete_account(index)
    print(paint(t("account_deleted", name=removed.emri, count=touched), YELLOW))


def add_transfer(app):
    """Record a movement between two of the user's own accounts."""
    if len(app.accounts) < 2:
        print(paint(t("transfer_needs_two"), YELLOW))
        return

    print(paint(f"\n{t('adding_transfer')}", BOLD))
    source = prompt_account(app, allow_skip=False)
    if not source:
        return

    while True:
        destination = prompt_account(app, message_key="ask_destination", allow_skip=False)
        if not destination:
            return
        if destination == source:
            print(paint(t("same_account"), RED))
            continue
        break

    description = prompt_description()
    amount = prompt_amount()
    date = prompt_date()

    app.add_transaction(
        TRANSFER,
        description,
        amount,
        date,
        category=DEFAULT_CATEGORY,
        subcategory="",
        account=source,
        destination=destination,
    )
    print(paint(t("transfer_added"), BOLD))


def assign_unassigned_transactions(app):
    """Move every account-less transaction onto a chosen account."""
    from .accounts import count_unassigned

    if not app.accounts:
        print(paint(t("no_accounts_to_change"), YELLOW))
        return

    pending = count_unassigned(app.transactions, app.recurring_rules)
    if not pending:
        print(paint(t("nothing_unassigned"), YELLOW))
        return

    target = prompt_account(app, allow_skip=False)
    if not target:
        return

    # Confirmed first: this rewrites every account-less record at once, and
    # there is no undo.
    answer = input(t("assign_confirm", count=pending, name=target)).strip().lower()
    if answer not in affirmatives():
        print(t("cancelled"))
        return

    assigned, skipped = app.assign_unassigned_to(target)
    print(paint(t("assigned", count=assigned, name=target), BOLD))
    if skipped:
        print(paint(t("assign_skipped", count=skipped), YELLOW))


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
# Budgets
# ---------------------------------------------------------------------------


def show_budgets(app, year=None, month=None):
    if year is None or month is None:
        year, month = month_of(today())
    print_budgets(all_statuses(app.budgets, app.transactions, year, month), year, month)


def set_budget(app):
    category = prompt_category(app.categories_for(EXPENSE))
    amount = prompt_amount()
    app.set_budget(category, amount)
    print(paint(t("budget_saved", category=category), BOLD))


def delete_budget(app):
    show_budgets(app)
    if not app.budgets:
        return
    index = prompt_index(len(app.budgets), t("ask_number_budget"))
    if index is None:
        return
    # The list shown is sorted by usage, so resolve the number against that
    # same ordering rather than against storage order.
    year, month = month_of(today())
    statuses = all_statuses(app.budgets, app.transactions, year, month)
    category = statuses[index].category
    for position, budget in enumerate(app.budgets):
        if budget.kategoria == category:
            app.delete_budget(position)
            print(paint(t("budget_deleted", category=category), BOLD))
            return


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
    print_recurring(app.recurring_rules, today())


def add_recurring(app):
    print(paint(f"\n{t('adding_recurring')}", BOLD))
    trans_type = prompt_type()
    description = prompt_description()
    amount = prompt_amount()
    category = prompt_category(app.categories_for(trans_type))
    subcategory = prompt_subcategory(app, trans_type, category)
    # A rule without an account would generate unassigned transactions every
    # month, so it is asked for here too.
    account = prompt_account(app) if app.has_accounts() else ""

    names = list(FREQUENCIES.keys())
    print(f"\n{t('field_frequency')}:")
    for i, name in enumerate(names, start=1):
        print(f"  {i}. {frequency_label(name)}")
    while True:
        raw = input(t("choose_frequency", count=len(names))).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(names):
            frequency = names[int(raw) - 1]
            break
        print(paint(t("invalid_type"), RED))

    print(paint(f"\n{t('first_date')}", DIM))
    start_date = prompt_date()

    app.add_recurring(
        RecurringRule(
            lloji=trans_type,
            pershkrimi=description,
            shuma=amount,
            kategoria=category,
            nenkategoria=subcategory,
            llogaria=account,
            frekuenca=frequency,
            data_fillimit=start_date,
            data_e_fundit="",
        )
    )
    print(paint(t("recurring_added"), BOLD))
    generated = app.process_recurring()
    if generated:
        print(paint(t("generated", count=len(generated)), BOLD))


def delete_recurring(app):
    show_recurring(app)
    if not app.recurring_rules:
        return
    index = prompt_index(len(app.recurring_rules), t("ask_number_recurring"))
    if index is None:
        return
    removed = app.delete_recurring(index)
    print(paint(t("recurring_deleted", description=removed.pershkrimi), BOLD))


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
    ("menu_filter", None),  # replaced below - needs its own submenu
    ("menu_search", search_transactions),
    ("menu_report", report_menu),
    ("menu_budgets", budget_menu),
    ("menu_accounts", account_menu),
    ("menu_transfer", add_transfer),
    ("menu_recurring", recurring_menu),
    ("menu_exit", None),
]


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


MENU_ITEMS[6] = ("menu_filter", filter_menu)


def run_menu(app):
    """The interactive loop."""
    print(paint(t("welcome"), BOLD, CYAN))
    count = len(MENU_ITEMS)

    while True:
        print(paint(f"\n{t('menu')}", BOLD))
        for i, (key, _) in enumerate(MENU_ITEMS, start=1):
            print(f"{i}. {t(key)}")

        choice = prompt_menu_choice(1, count)
        if choice == str(count):
            print(paint(t("goodbye"), CYAN))
            return
        if choice.isdigit() and 1 <= int(choice) < count:
            MENU_ITEMS[int(choice) - 1][1](app)
        else:
            print(paint(t("invalid_choice", low=1, high=count), RED))
