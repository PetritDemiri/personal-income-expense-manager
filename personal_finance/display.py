"""Paraqitja / Rendering.

Turns data into strings. Column widths are measured from the data so nothing
is ever truncated, and every field is padded before color is applied.
"""

from decimal import Decimal

from .budgets import NEAR, OVER
from .colors import BOLD, CYAN, DIM, GREEN, RED, YELLOW, amount_color, paint, type_color
from .config import CURRENCY_SYMBOL
from .dates import format_date, format_month
from .i18n import frequency_label, t, type_label
from .recurring import next_occurrence
from .reports import (
    ZERO,
    has_subcategories,
    totals_by_category,
    totals_by_subcategory,
)
from .schema import EXPENSE, INCOME, TRANSFER


def category_display(value):
    """A category for display, or a readable label when there is none.

    There is no stored placeholder any more - a transaction with no category
    has NULL in that column - so this turns absence into words rather than
    translating a sentinel.
    """
    return value or t("no_category_display")


def account_display(value):
    """An account name for display, or a readable label when there isn't one."""
    return value or t("no_account_display")


def account_cell(item):
    """The account column: 'Kesh' normally, 'Kesh -> Banka' for a transfer."""
    if item.kind == TRANSFER:
        return f"{account_display(item.account)} -> {account_display(item.to_account)}"
    return account_display(item.account)


def subcategory_display(value):
    """A subcategory for display, or a readable label when there isn't one.

    A bare dash was too easy to read as a formatting artefact rather than as
    "this field is empty".
    """
    return value or t("no_subcategory_display")


def category_path(item):
    """'Ushqim / Dyqan', or just 'Ushqim' when there is no subcategory."""
    if item.subcategory:
        return f"{category_display(item.category)} / {item.subcategory}"
    return category_display(item.category)


def money(amount):
    """Format an amount with the currency symbol."""
    return f"{CURRENCY_SYMBOL}{amount:.2f}"


def print_transactions(numbered, title=None, show_times=False):
    """Print a table of (number, transaction) pairs.

    Numbers refer to positions in the full list, so a number shown in a
    filtered view can still be used to edit or delete.
    """
    title = title or t("all_transactions")

    if not numbered:
        print(paint(f"\n{t('no_transactions')}", YELLOW))
        return

    labels = {n: type_label(x.kind) for n, x in numbered}
    amounts = {n: money(x.amount) for n, x in numbered}

    # Only show the subcategory column when something actually uses it, so
    # users who don't need subcategories don't get a column of dashes.
    show_sub = has_subcategories(x for _, x in numbered)
    subs = {n: subcategory_display(x.subcategory) for n, x in numbered}

    # Same rule for accounts: the column appears only once something uses one.
    show_account = any(x.account or x.to_account for _, x in numbered)
    accounts = {n: account_cell(x) for n, x in numbered}

    head_num = t("field_number")
    head_date = t("field_date")
    head_type = t("field_type")
    head_desc = t("field_description")
    head_cat = t("field_category")
    head_sub = t("field_subcategory")
    head_account = t("field_account")
    head_amount = t("field_amount")
    head_created = t("field_created")
    head_updated = t("field_updated")

    # Off unless asked for. Two more columns on every row would crowd out the
    # description, and the answer is rarely the one being looked for.
    created = {n: (x.created_at or "")[:16] for n, x in numbered}
    updated = {n: (x.updated_at or "")[:16] for n, x in numbered}

    w_num = max(len(head_num) + 1, len(str(max(n for n, _ in numbered))) + 1)
    w_date = max(len(head_date), 10)
    w_type = max([len(head_type)] + [len(v) for v in labels.values()])
    w_desc = max([len(head_desc)] + [len(x.description) for _, x in numbered])
    categories = {n: category_display(x.category) for n, x in numbered}
    w_cat = max([len(head_cat)] + [len(v) for v in categories.values()])
    w_sub = max([len(head_sub)] + [len(v) for v in subs.values()]) if show_sub else 0
    w_account = (
        max([len(head_account)] + [len(v) for v in accounts.values()]) if show_account else 0
    )
    w_amount = max([len(head_amount)] + [len(v) for v in amounts.values()])
    w_created = max([len(head_created)] + [len(v) for v in created.values()]) if show_times else 0
    w_updated = max([len(head_updated)] + [len(v) for v in updated.values()]) if show_times else 0

    sub_header = f"{head_sub:<{w_sub}} " if show_sub else ""
    account_header = f"{head_account:<{w_account}} " if show_account else ""
    time_header = (
        f"  {head_created:<{w_created}}  {head_updated:<{w_updated}}" if show_times else ""
    )
    total = w_num + w_date + 1 + w_type + 1 + w_desc + 1 + w_cat + 1 + w_amount
    if show_sub:
        total += w_sub + 1
    if show_account:
        total += w_account + 1
    if show_times:
        total += w_created + w_updated + 4

    print(paint(f"\n{title}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{head_num:<{w_num}}{head_date:<{w_date}} {head_type:<{w_type}} "
            f"{head_desc:<{w_desc}} {head_cat:<{w_cat}} "
            f"{sub_header}{account_header}{head_amount:>{w_amount}}{time_header}",
            BOLD,
        )
    )
    print("-" * total)
    for number, x in numbered:
        sub_cell = f"{subs[number]:<{w_sub}} " if show_sub else ""
        account_cell_text = f"{accounts[number]:<{w_account}} " if show_account else ""
        line = (
            f"{number:<{w_num}}{x.occurred_on:<{w_date}} {labels[number]:<{w_type}} "
            f"{x.description:<{w_desc}} {categories[number]:<{w_cat}} "
            f"{sub_cell}{account_cell_text}{amounts[number]:>{w_amount}}"
        )
        if show_times:
            line += f"  {created[number]:<{w_created}}  {updated[number]:<{w_updated}}"
        print(paint(line, type_color(x.kind)))
    print("-" * total)


def print_category_breakdown(transactions, trans_type):
    """Print per-category totals, with subcategories nested underneath.

    A category whose only subcategory is "none" prints as a single line - there
    is nothing to break down, so the extra row would only add noise.

    Column widths are measured across the whole block, never per category.
    Measuring per category would put the subcategory amounts wherever that one
    category's names happened to end - sometimes left of the category amounts,
    sometimes right - so the same report could look aligned in one section and
    broken in the next.
    """
    rows = totals_by_category(transactions, trans_type)
    if not rows:
        return

    # Gather every row that will be printed, so all widths come from the same
    # measurement pass.
    printable = []
    for category, total in rows:
        sub_rows = totals_by_subcategory(transactions, trans_type, category)
        # Nothing worth nesting if every amount sits directly in the category.
        # Nothing worth nesting if every amount sits directly in the
        # category. That is now None rather than an empty string.
        if len(sub_rows) == 1 and sub_rows[0][0] is None:
            sub_rows = []
        printable.append((category, total, sub_rows))

    # Categories and subcategories share one label width. Since subcategory
    # labels are indented two spaces further, a shared width puts their amounts
    # exactly two columns to the right of the category amounts - consistently
    # nested, whatever the names are. Measuring the two groups separately would
    # let a long subcategory name fling its amount far off to the right.
    labels = [category_display(category) for category, _, _ in printable]
    labels += [subcategory_display(name) for _, _, subs in printable for name, _ in subs]
    label_width = max(len(label) for label in labels)

    amounts = [money(total) for _, total, _ in printable]
    amounts += [money(sub_total) for _, _, subs in printable for _, sub_total in subs]
    amount_width = max([12] + [len(a) for a in amounts])

    print(paint(f"\n  {t('by_category', type=type_label(trans_type))}", type_color(trans_type)))

    for category, total, sub_rows in printable:
        print(f"    {category_display(category):<{label_width}}  {money(total):>{amount_width}}")
        for name, sub_total in sub_rows:
            label = subcategory_display(name)
            print(paint(f"      {label:<{label_width}}  {money(sub_total):>{amount_width}}", DIM))


def print_summary(transactions, totals, title=None):
    """Print totals plus a per-category breakdown."""
    title = title or t("summary")
    print(paint(f"\n{title}", BOLD, CYAN))
    print(f"{t('total_income')}{paint(money(totals.income), GREEN)}")
    print(f"{t('total_expenses')}{paint(money(totals.expenses), RED)}")
    print(f"{t('balance')}{paint(money(totals.balance), BOLD, amount_color(totals.balance))}")
    print(f"{t('count')}{totals.count}")

    print_category_breakdown(transactions, INCOME)
    print_category_breakdown(transactions, EXPENSE)


def format_change(change):
    """Format a percent change with a sign, or a dash when undefined."""
    if change is None:
        return "-"
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def print_monthly_report(report):
    """Print one month's totals, comparison, and category breakdown."""
    heading = t("report_title", month=format_month(report.year, report.month))
    print(paint(f"\n{heading}", BOLD, CYAN))

    if report.is_empty:
        print(paint(t("report_no_data"), YELLOW))
        return

    print(f"{t('total_income')}{paint(money(report.totals.income), GREEN)}")
    print(f"{t('total_expenses')}{paint(money(report.totals.expenses), RED)}")
    print(
        f"{t('balance')}"
        f"{paint(money(report.totals.balance), BOLD, amount_color(report.totals.balance))}"
    )
    print(f"{t('count')}{report.totals.count}")

    if report.has_previous:
        print(paint(f"\n{t('report_vs_previous')}", BOLD))
        income_change = report.income_change
        expense_change = report.expense_change
        # More income is good, more expenses are not - so the two are colored
        # by meaning rather than by sign.
        income_color = GREEN if (income_change or 0) >= 0 else RED
        expense_color = RED if (expense_change or 0) >= 0 else GREEN
        print(f"  {t('total_income')}{paint(format_change(income_change), income_color)}")
        print(f"  {t('total_expenses')}{paint(format_change(expense_change), expense_color)}")

    print_category_breakdown(report.transactions, INCOME)
    print_category_breakdown(report.transactions, EXPENSE)


def budget_state_color(state):
    if state == OVER:
        return RED
    if state == NEAR:
        return YELLOW
    return GREEN


def print_budgets(statuses, year, month):
    """Print every budget with the amount spent, remaining, and a usage bar."""
    heading = f"{t('budgets_title')} ({format_month(year, month)})"
    if not statuses:
        print(paint(f"\n{heading}", BOLD, CYAN))
        print(paint(t("no_budgets"), YELLOW))
        return

    labels = {s.category_id: category_display(s.category) for s in statuses}
    w_cat = max([len(t("field_category"))] + [len(v) for v in labels.values()])
    spent_strs = {s.category_id: money(s.spent) for s in statuses}
    limit_strs = {s.category_id: money(s.limit) for s in statuses}
    left_strs = {s.category_id: money(s.remaining) for s in statuses}
    w_spent = max([len(t("budget_spent"))] + [len(v) for v in spent_strs.values()])
    w_limit = max([len(t("budget_limit"))] + [len(v) for v in limit_strs.values()])
    w_left = max([len(t("budget_left"))] + [len(v) for v in left_strs.values()])

    total = 4 + w_cat + 2 + w_spent + 2 + w_limit + 2 + w_left + 2 + 16

    print(paint(f"\n{heading}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{'#':<4}{t('field_category'):<{w_cat}}  "
            f"{t('budget_spent'):>{w_spent}}  {t('budget_limit'):>{w_limit}}  "
            f"{t('budget_left'):>{w_left}}  {t('budget_used')}",
            BOLD,
        )
    )
    print("-" * total)
    for i, status in enumerate(statuses, start=1):
        bar = usage_bar(status.fraction_used)
        percent = f"{status.percent_used:.0f}%"
        line = (
            f"{i:<4}{labels[status.category_id]:<{w_cat}}  "
            f"{spent_strs[status.category_id]:>{w_spent}}  "
            f"{limit_strs[status.category_id]:>{w_limit}}  "
            f"{left_strs[status.category_id]:>{w_left}}  {bar} {percent:>5}"
        )
        print(paint(line, budget_state_color(status.state)))
    print("-" * total)


def usage_bar(fraction, width=10):
    """A small text bar showing how much of a budget is used."""
    if fraction < 0:
        fraction = Decimal("0")
    filled = int(min(Decimal("1"), fraction) * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def print_budget_warning(status):
    """Warn once a budget is near or past its limit."""
    if status is None:
        return
    if status.state == OVER:
        print(
            paint(
                t(
                    "budget_over",
                    category=category_display(status.category),
                    amount=money(status.overspent),
                ),
                BOLD,
                RED,
            )
        )
    else:
        print(
            paint(
                t(
                    "budget_near",
                    percent=f"{status.percent_used:.0f}",
                    category=category_display(status.category),
                ),
                YELLOW,
            )
        )


def print_recurring(rules, as_of, category_names=None, account_names=None):
    """Print every recurring rule with its next scheduled date.

    A rule holds ids, not names - it comes back as a model rather than a joined
    view - so the caller passes the lookups. That keeps the display free of
    database access.
    """
    if not rules:
        print(paint(f"\n{t('no_recurring')}", YELLOW))
        return

    category_names = category_names or {}
    account_names = account_names or {}

    labels = [type_label(r.kind) for r in rules]
    freqs = [frequency_label(r.frequency) for r in rules]
    amounts = [money(r.amount) for r in rules]
    paths = [category_display(category_names.get(r.category_id)) for r in rules]
    accts = [account_display(account_names.get(r.account_id)) for r in rules]

    w_type = max([len(t("field_type"))] + [len(v) for v in labels])
    w_desc = max([len(t("field_description"))] + [len(r.description) for r in rules])
    w_cat = max([len(t("field_category"))] + [len(v) for v in paths])
    w_acct = max([len(t("field_account"))] + [len(v) for v in accts])
    w_freq = max([len(t("field_frequency"))] + [len(v) for v in freqs])
    w_amount = max([len(t("field_amount"))] + [len(v) for v in amounts])
    total = 4 + w_type + 1 + w_desc + 1 + w_cat + 1 + w_acct + 1 + w_freq + 1 + w_amount

    print(paint(f"\n{t('recurring_title')}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{'#':<4}{t('field_type'):<{w_type}} "
            f"{t('field_description'):<{w_desc}} {t('field_category'):<{w_cat}} "
            f"{t('field_account'):<{w_acct}} "
            f"{t('field_frequency'):<{w_freq}} {t('field_amount'):>{w_amount}}",
            BOLD,
        )
    )
    print("-" * total)
    for i, rule in enumerate(rules, start=1):
        line = (
            f"{i:<4}{labels[i - 1]:<{w_type}} {rule.description:<{w_desc}} "
            f"{paths[i - 1]:<{w_cat}} {accts[i - 1]:<{w_acct}} "
            f"{freqs[i - 1]:<{w_freq}} {amounts[i - 1]:>{w_amount}}"
        )
        print(paint(line, type_color(rule.kind)))
        upcoming = next_occurrence(rule)
        if upcoming is not None:
            print(paint(f"    {t('next_occurrence', date=format_date(upcoming))}", DIM))
    print("-" * total)


def print_accounts(balances, show_total=True):
    """Print every account with its opening balance, movements and balance."""
    if not balances:
        print(paint(f"\n{t('no_accounts')}", YELLOW))
        return

    names = [account_display(b.name) for b in balances]
    types = [b.kind for b in balances]
    openings = [money(b.opening) for b in balances]
    totals = [money(b.balance) for b in balances]

    head_name = t("field_account")
    head_type = t("field_type")
    head_opening = t("field_opening")
    head_balance = t("account_balance")

    w_name = max([len(head_name)] + [len(v) for v in names])
    w_type = max([len(head_type)] + [len(v) for v in types])
    w_opening = max([len(head_opening)] + [len(v) for v in openings])
    w_balance = max([len(head_balance)] + [len(v) for v in totals])
    width = 4 + w_name + 2 + w_type + 2 + w_opening + 2 + w_balance

    print(paint(f"\n{t('accounts_title')}", BOLD, CYAN))
    print("-" * width)
    print(
        paint(
            f"{'#':<4}{head_name:<{w_name}}  {head_type:<{w_type}}  "
            f"{head_opening:>{w_opening}}  {head_balance:>{w_balance}}",
            BOLD,
        )
    )
    print("-" * width)
    # Only real accounts are numbered. The unassigned row is a summary of
    # transactions that belong to no account - numbering it would make it look
    # like something that can be chosen, edited or deleted.
    number = 0
    for position, item in enumerate(balances):
        if item.is_unassigned:
            label = ""
        else:
            number += 1
            label = str(number)
        line = (
            f"{label:<4}{account_display(item.name):<{w_name}}  {item.kind:<{w_type}}  "
            f"{openings[position]:>{w_opening}}  {totals[position]:>{w_balance}}"
        )
        print(paint(line, amount_color(item.balance)))
    print("-" * width)

    if any(item.is_unassigned for item in balances):
        print(paint(f"  {t('unassigned_legend')}", DIM))

    if show_total:
        combined = sum((b.balance for b in balances), ZERO)
        print(f"{t('account_total')}{paint(money(combined), BOLD, amount_color(combined))}")


def action_label(action):
    """Display label for a recorded action."""
    return t(f"action_{action}")


def entity_label(entity):
    """Display label for the kind of thing that changed."""
    return t(f"entity_{entity}")


# Database column names, mapped to the label the rest of the program uses for
# the same thing. The history reads a row as the database stores it, which is
# not how anyone wants to read it.
_FIELD_LABELS = {
    "kind": "field_type",
    "description": "field_description",
    "amount_cents": "field_amount",
    "occurred_on": "field_date",
    "category_id": "field_category",
    "subcategory_id": "field_subcategory",
    "account_id": "field_account",
    "to_account_id": "field_destination",
    "name": "field_name",
    "opening_cents": "field_opening",
    "position": "field_position",
    "frequency": "field_frequency",
    "starts_on": "field_start",
    "generated_upto": "field_generated",
    "limit_cents": "field_limit",
    "pattern": "field_pattern",
}

# Columns holding money, so the log shows euros rather than raw cents.
_CENT_FIELDS = ("amount_cents", "opening_cents", "limit_cents")

# Columns holding a reference, so the log can show the name instead of the id.
_REFERENCE_FIELDS = {
    "category_id": "categories",
    "subcategory_id": "subcategories",
    "account_id": "accounts",
    "to_account_id": "accounts",
}


def field_label(field):
    """The display label for a database column, or the column name itself."""
    key = _FIELD_LABELS.get(field)
    return t(key) if key else field


def audit_value(field, value, names=None):
    """One side of a change, formatted for reading.

    Cents become euros, ISO dates become dd-mm-yyyy, and a reference becomes
    the name of the thing it points at. An id is shown only when the row it
    referred to has since been deleted, since there is no name left to give.
    """
    if value is None:
        return "-"
    if field in _CENT_FIELDS:
        return money((Decimal(int(value)) / 100).quantize(Decimal("0.01")))
    if field == "occurred_on" or field in ("starts_on", "generated_upto"):
        from .database import from_iso

        return from_iso(value) or str(value)
    if field in _REFERENCE_FIELDS and names:
        lookup = names.get(_REFERENCE_FIELDS[field], {})
        return lookup.get(value, f"#{value}")
    if field == "kind":
        from .i18n import type_label

        return type_label(value)
    return str(value)


def print_history(entries, title=None, names=None):
    """Print recorded changes, newest first, with what differed on each.

    `names` maps each referenced table to {id: name}, so a change of category
    reads as a category rather than as a number.
    """
    if not entries:
        print(paint(f"\n{t('no_history')}", YELLOW))
        return

    print(paint(f"\n{title or t('history_title')}", BOLD, CYAN))
    for entry in entries:
        heading = (
            f"{entry.at}  {action_label(entry.action)} "
            f"{entity_label(entry.entity)} #{entry.entity_id}"
        )
        print(paint(heading, BOLD))

        changes = entry.changes()
        if not changes:
            continue
        labels = {field: field_label(field) for field, _, _ in changes}
        width = max(len(value) for value in labels.values())
        for field, before, after in changes:
            shown_before = audit_value(field, before, names)
            shown_after = audit_value(field, after, names)
            print(
                paint(
                    f"    {labels[field]:<{width}}  {shown_before}  ->  {shown_after}",
                    DIM,
                )
            )


def print_candidates(candidates, decimal_separator=None, date_label=None):
    """Print parsed rows before any of them is written.

    The amounts and dates shown are the parsed ones, not the file's text. That
    is the whole point: a misread decimal separator or a day and month the
    wrong way round are silent errors, and seeing EUR 1.23 where EUR 1,234.56
    was meant is how they get caught.
    """
    if not candidates:
        print(paint(f"\n{t('import_nothing')}", YELLOW))
        return

    numbers = {c.row_number: str(index) for index, c in enumerate(candidates, start=1)}
    dates = {c.row_number: c.occurred_on or "?" for c in candidates}
    types = {c.row_number: type_label(c.kind) for c in candidates}
    amounts = {c.row_number: money(c.amount) for c in candidates}
    categories = {c.row_number: category_display(c.category) for c in candidates}

    def status(candidate):
        if candidate.problem == "date":
            return t("import_bad_date")
        if candidate.problem == "amount":
            return t("import_bad_amount")
        if candidate.duplicate_of is not None:
            return t("import_duplicate")
        return ""

    statuses = {c.row_number: status(c) for c in candidates}

    w_num = max(len("#"), max(len(v) for v in numbers.values()))
    w_date = max([len(t("field_date"))] + [len(v) for v in dates.values()])
    w_type = max([len(t("field_type"))] + [len(v) for v in types.values()])
    w_desc = max([len(t("field_description"))] + [len(c.description) for c in candidates])
    w_cat = max([len(t("field_category"))] + [len(v) for v in categories.values()])
    w_amount = max([len(t("field_amount"))] + [len(v) for v in amounts.values()])
    w_status = max([len(t("import_status"))] + [len(v) for v in statuses.values()])

    total = 2 + w_num + w_date + w_type + w_desc + w_cat + w_amount + w_status + 7

    if decimal_separator or date_label:
        detected = []
        if date_label:
            detected.append(t("import_date_format", format=date_label))
        if decimal_separator:
            detected.append(t("import_number_format", separator=decimal_separator))
        print(paint("  " + "   ".join(detected), DIM))

    print("-" * total)
    print(
        paint(
            f"{'':<2}{'#':<{w_num}} {t('field_date'):<{w_date}} "
            f"{t('field_type'):<{w_type}} {t('field_description'):<{w_desc}} "
            f"{t('field_category'):<{w_cat}} {t('field_amount'):>{w_amount}} "
            f"{t('import_status'):<{w_status}}",
            BOLD,
        )
    )
    print("-" * total)

    for candidate in candidates:
        key = candidate.row_number
        mark = "*" if candidate.will_import else " "
        line = (
            f"{mark:<2}{numbers[key]:<{w_num}} {dates[key]:<{w_date}} "
            f"{types[key]:<{w_type}} {candidate.description:<{w_desc}} "
            f"{categories[key]:<{w_cat}} {amounts[key]:>{w_amount}} "
            f"{statuses[key]:<{w_status}}"
        )
        if not candidate.importable:
            print(paint(line, RED))
        elif candidate.duplicate_of is not None:
            print(paint(line, YELLOW))
        elif candidate.will_import:
            print(paint(line, type_color(candidate.kind)))
        else:
            print(paint(line, DIM))

    print("-" * total)
    chosen = sum(1 for c in candidates if c.will_import)
    print(paint(t("import_selected", count=chosen, total=len(candidates)), BOLD))


# A three-quarter block rather than a full one. A full block fills the whole
# character cell, so stacked rows run together into a solid mass with no gap
# between them - terminals have no line spacing to separate them. This leaves
# the top quarter empty, which reads as separate bars.
BAR_FULL = "▆"
BAR_EMPTY = " "
BAR_WIDTH = 28


def bar_of(fraction, width=BAR_WIDTH):
    """A bar of `width` characters, filled to `fraction`.

    A non-zero amount always gets at least one block, so a small category is
    visibly present rather than looking like nothing at all.
    """
    filled = int((fraction or 0) * width)
    if filled == 0 and fraction and fraction > 0:
        filled = 1
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def print_category_chart(bars, title, color=None):
    """A horizontal bar per category, largest first."""
    from .charts import has_data, percent

    print(paint(f"\n{title}", BOLD, CYAN))
    if not has_data(bars):
        print(paint(t("no_chart_data"), YELLOW))
        return

    labels = {i: category_display(b.label) for i, b in enumerate(bars)}
    amounts = {i: money(b.amount) for i, b in enumerate(bars)}
    w_label = max(len(v) for v in labels.values())
    w_amount = max(len(v) for v in amounts.values())

    for index, bar in enumerate(bars):
        line = (
            f"  {labels[index]:<{w_label}}  {bar_of(bar.fraction)}  "
            f"{amounts[index]:>{w_amount}}  {percent(bar.share):>3}%"
        )
        print(paint(line, color) if color else line)


def print_monthly_chart(income_bars, expense_bars, title):
    """Income and expenses side by side, one row per month."""
    from .charts import has_data

    print(paint(f"\n{title}", BOLD, CYAN))
    if not has_data(income_bars) and not has_data(expense_bars):
        print(paint(t("no_chart_data"), YELLOW))
        return

    half = BAR_WIDTH // 2
    w_amount = max([len(money(b.amount)) for b in income_bars + expense_bars] or [6])

    print(
        paint(
            f"  {'':<7}  {t('field_income'):<{half + w_amount + 2}}  {t('field_expenses')}",
            DIM,
        )
    )
    for earned, spent in zip(income_bars, expense_bars):
        line = (
            f"  {earned.label:<7}  {bar_of(earned.fraction, half)} "
            f"{money(earned.amount):>{w_amount}}"
            f"  {bar_of(spent.fraction, half)} {money(spent.amount):>{w_amount}}"
        )
        print(line)


def print_account_chart(bars, title):
    """A bar per account. Negative balances are drawn to the left of zero."""
    from .charts import has_data

    print(paint(f"\n{title}", BOLD, CYAN))
    if not has_data(bars):
        print(paint(t("no_chart_data"), YELLOW))
        return

    labels = {i: account_display(b.label) for i, b in enumerate(bars)}
    amounts = {i: money(b.amount) for i, b in enumerate(bars)}
    w_label = max(len(v) for v in labels.values())
    w_amount = max(len(v) for v in amounts.values())

    for index, bar in enumerate(bars):
        drawn = bar_of(bar.fraction)
        colour = RED if bar.amount < 0 else GREEN
        line = f"  {labels[index]:<{w_label}}  {drawn}  {amounts[index]:>{w_amount}}"
        print(paint(line, colour))
