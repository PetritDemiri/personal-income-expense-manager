"""Paraqitja / Rendering.

Turns data into strings. Column widths are measured from the data so nothing
is ever truncated, and every field is padded before color is applied.
"""

from decimal import Decimal

from .budgets import NEAR, OVER
from .colors import BOLD, CYAN, DIM, GREEN, RED, YELLOW, amount_color, paint, type_color
from .config import CURRENCY_SYMBOL, EXPENSE, INCOME, NO_SUBCATEGORY_DISPLAY
from .dates import format_month
from .i18n import frequency_label, t, type_label
from .recurring import next_occurrence
from .reports import (
    has_subcategories,
    totals_by_category,
    totals_by_subcategory,
)


def subcategory_display(value):
    """A subcategory for display, or a dash when there isn't one."""
    return value or NO_SUBCATEGORY_DISPLAY


def category_path(transaction):
    """'Ushqim / Dyqan', or just 'Ushqim' when there is no subcategory."""
    if transaction.nenkategoria:
        return f"{transaction.kategoria} / {transaction.nenkategoria}"
    return transaction.kategoria


def money(amount):
    """Format an amount with the currency symbol."""
    return f"{CURRENCY_SYMBOL}{amount:.2f}"


def print_transactions(numbered, title=None):
    """Print a table of (number, transaction) pairs.

    Numbers refer to positions in the full list, so a number shown in a
    filtered view can still be used to edit or delete.
    """
    title = title or t("all_transactions")

    if not numbered:
        print(paint(f"\n{t('no_transactions')}", YELLOW))
        return

    labels = {n: type_label(x.lloji) for n, x in numbered}
    amounts = {n: money(x.shuma) for n, x in numbered}

    # Only show the subcategory column when something actually uses it, so
    # users who don't need subcategories don't get a column of dashes.
    show_sub = has_subcategories(x for _, x in numbered)
    subs = {n: subcategory_display(x.nenkategoria) for n, x in numbered}

    head_num = t("field_number")
    head_date = t("field_date")
    head_type = t("field_type")
    head_desc = t("field_description")
    head_cat = t("field_category")
    head_sub = t("field_subcategory")
    head_amount = t("field_amount")

    w_num = max(len(head_num) + 1, len(str(max(n for n, _ in numbered))) + 1)
    w_date = max(len(head_date), 10)
    w_type = max([len(head_type)] + [len(v) for v in labels.values()])
    w_desc = max([len(head_desc)] + [len(x.pershkrimi) for _, x in numbered])
    w_cat = max([len(head_cat)] + [len(x.kategoria) for _, x in numbered])
    w_sub = max([len(head_sub)] + [len(v) for v in subs.values()]) if show_sub else 0
    w_amount = max([len(head_amount)] + [len(v) for v in amounts.values()])

    sub_header = f"{head_sub:<{w_sub}} " if show_sub else ""
    total = w_num + w_date + 1 + w_type + 1 + w_desc + 1 + w_cat + 1 + w_amount
    if show_sub:
        total += w_sub + 1

    print(paint(f"\n{title}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{head_num:<{w_num}}{head_date:<{w_date}} {head_type:<{w_type}} "
            f"{head_desc:<{w_desc}} {head_cat:<{w_cat}} "
            f"{sub_header}{head_amount:>{w_amount}}",
            BOLD,
        )
    )
    print("-" * total)
    for number, x in numbered:
        sub_cell = f"{subs[number]:<{w_sub}} " if show_sub else ""
        line = (
            f"{number:<{w_num}}{x.data:<{w_date}} {labels[number]:<{w_type}} "
            f"{x.pershkrimi:<{w_desc}} {x.kategoria:<{w_cat}} "
            f"{sub_cell}{amounts[number]:>{w_amount}}"
        )
        print(paint(line, type_color(x.lloji)))
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
        if len(sub_rows) == 1 and sub_rows[0][0] == "":
            sub_rows = []
        printable.append((category, total, sub_rows))

    # Categories and subcategories share one label width. Since subcategory
    # labels are indented two spaces further, a shared width puts their amounts
    # exactly two columns to the right of the category amounts - consistently
    # nested, whatever the names are. Measuring the two groups separately would
    # let a long subcategory name fling its amount far off to the right.
    labels = [category for category, _, _ in printable]
    labels += [subcategory_display(name) for _, _, subs in printable for name, _ in subs]
    label_width = max(len(label) for label in labels)

    amounts = [money(total) for _, total, _ in printable]
    amounts += [money(sub_total) for _, _, subs in printable for _, sub_total in subs]
    amount_width = max([12] + [len(a) for a in amounts])

    print(paint(f"\n  {t('by_category', type=type_label(trans_type))}", type_color(trans_type)))

    for category, total, sub_rows in printable:
        print(f"    {category:<{label_width}}  {money(total):>{amount_width}}")
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

    w_cat = max([len(t("field_category"))] + [len(s.category) for s in statuses])
    spent_strs = {s.category: money(s.spent) for s in statuses}
    limit_strs = {s.category: money(s.limit) for s in statuses}
    left_strs = {s.category: money(s.remaining) for s in statuses}
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
            f"{i:<4}{status.category:<{w_cat}}  "
            f"{spent_strs[status.category]:>{w_spent}}  "
            f"{limit_strs[status.category]:>{w_limit}}  "
            f"{left_strs[status.category]:>{w_left}}  {bar} {percent:>5}"
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
                t("budget_over", category=status.category, amount=money(status.overspent)),
                BOLD,
                RED,
            )
        )
    else:
        print(
            paint(
                t("budget_near", percent=f"{status.percent_used:.0f}", category=status.category),
                YELLOW,
            )
        )


def print_recurring(rules, as_of):
    """Print every recurring rule with its next scheduled date."""
    if not rules:
        print(paint(f"\n{t('no_recurring')}", YELLOW))
        return

    labels = [type_label(r.lloji) for r in rules]
    freqs = [frequency_label(r.frekuenca) for r in rules]
    amounts = [money(r.shuma) for r in rules]

    w_type = max([len(t("field_type"))] + [len(v) for v in labels])
    w_desc = max([len(t("field_description"))] + [len(r.pershkrimi) for r in rules])
    paths = [category_path(r) for r in rules]
    w_cat = max([len(t("field_category"))] + [len(v) for v in paths])
    w_freq = max([len(t("field_frequency"))] + [len(v) for v in freqs])
    w_amount = max([len(t("field_amount"))] + [len(v) for v in amounts])
    total = 4 + w_type + 1 + w_desc + 1 + w_cat + 1 + w_freq + 1 + w_amount

    print(paint(f"\n{t('recurring_title')}", BOLD, CYAN))
    print("-" * total)
    print(
        paint(
            f"{'#':<4}{t('field_type'):<{w_type}} "
            f"{t('field_description'):<{w_desc}} {t('field_category'):<{w_cat}} "
            f"{t('field_frequency'):<{w_freq}} {t('field_amount'):>{w_amount}}",
            BOLD,
        )
    )
    print("-" * total)
    for i, rule in enumerate(rules, start=1):
        line = (
            f"{i:<4}{labels[i - 1]:<{w_type}} {rule.pershkrimi:<{w_desc}} "
            f"{paths[i - 1]:<{w_cat}} {freqs[i - 1]:<{w_freq}} "
            f"{amounts[i - 1]:>{w_amount}}"
        )
        print(paint(line, type_color(rule.lloji)))
        upcoming = next_occurrence(rule, as_of)
        if upcoming is not None:
            from .dates import format_date

            print(paint(f"    {t('next_occurrence', date=format_date(upcoming))}", DIM))
    print("-" * total)
