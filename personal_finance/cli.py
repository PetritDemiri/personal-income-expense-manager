"""Rreshti i komandes / Command-line interface.

Albanian flags are primary; English aliases are accepted for all of them.
With no flags at all, the interactive menu runs.
"""

import argparse
import sys

from . import colors
from .app import FinanceApp
from .budgets import all_statuses, check_after_adding
from .colors import BOLD, RED, paint
from .config import DEFAULT_CATEGORY, EXPENSE, INCOME
from .dates import (
    format_date,
    month_of,
    parse_date,
    parse_month,
    today,
)
from .display import (
    print_budget_warning,
    print_budgets,
    print_monthly_report,
    print_recurring,
    print_summary,
    print_transactions,
)
from .i18n import set_language, t, type_label
from .models import parse_amount
from .reports import (
    calculate_totals,
    filter_by_dates,
    month_report,
    search,
    sort_by_date,
)
from .ui import numbered, run_menu


def build_parser():
    parser = argparse.ArgumentParser(
        prog="financat",
        description="Menaxheri i te Ardhurave dhe Shpenzimeve Personale / "
        "Personal Income and Expense Manager. "
        "Pa asnje flamur, hapet menuja interaktive.",
        epilog="Shembuj / Examples:\n"
        "  %(prog)s --lista\n"
        "  %(prog)s --lista --data 05-08-2026\n"
        "  %(prog)s --lista --nga 01-08-2026 --deri 31-08-2026\n"
        "  %(prog)s --kerko ushqim\n"
        "  %(prog)s --raporti --muaji 07-2026\n"
        "  %(prog)s --buxhetet\n"
        '  %(prog)s --shto-shpenzime --pershkrimi "Qera" --shuma 300 '
        "--kategoria Qera\n"
        "  %(prog)s --gjuha en --gjendja\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--ndihma", action="help", help="Shfaq kete mesazh ndihme dhe dil / show this help"
    )

    actions = parser.add_argument_group("veprimet / actions")
    actions.add_argument(
        "--lista", "--list", action="store_true", help="Shfaq transaksionet / list transactions"
    )
    actions.add_argument(
        "--gjendja",
        "--balance",
        action="store_true",
        help="Shfaq permbledhjen financiare / show the summary",
    )
    actions.add_argument(
        "--raporti", "--report", action="store_true", help="Raporti mujor / monthly report"
    )
    actions.add_argument(
        "--buxhetet", "--budgets", action="store_true", help="Shfaq buxhetet / show budgets"
    )
    actions.add_argument(
        "--cakto-buxhet",
        "--set-budget",
        dest="cakto_buxhet",
        nargs=2,
        metavar=("KATEGORIA", "SHUMA"),
        help="Cakto nje buxhet mujor / set a monthly budget",
    )
    actions.add_argument(
        "--shto-te-ardhura",
        "--add-income",
        action="store_true",
        dest="shto_te_ardhura",
        help="Shto nje te ardhur / add income",
    )
    actions.add_argument(
        "--shto-shpenzime",
        "--add-expense",
        action="store_true",
        dest="shto_shpenzime",
        help="Shto nje shpenzim / add an expense",
    )
    actions.add_argument(
        "--perserit",
        "--recurring",
        action="store_true",
        help="Gjenero perseritjet e radhes / generate due recurring",
    )
    actions.add_argument(
        "--perseritjet",
        "--list-recurring",
        action="store_true",
        help="Shfaq rregullat e perseritura / list recurring rules",
    )
    actions.add_argument(
        "--kerko", "--search", metavar="TERMI", help="Kerko ne pershkrim ose kategori / search"
    )

    fields = parser.add_argument_group("fushat dhe filtrat / fields and filters")
    fields.add_argument(
        "--pershkrimi", "--description", help="Pershkrimi i transaksionit te ri / description"
    )
    fields.add_argument("--shuma", "--amount", help="Shuma e transaksionit te ri / amount")
    fields.add_argument(
        "--data",
        "--date",
        help="Data (dite-muaj-Vit). Me --lista filtron nje date; me --shto-* cakton daten / date",
    )
    fields.add_argument(
        "--kategoria", "--category", help="Kategoria e transaksionit te ri / category"
    )
    fields.add_argument(
        "--nenkategoria",
        "--subcategory",
        help="Nenkategoria e transaksionit te ri / subcategory (optional)",
    )
    fields.add_argument(
        "--nga", "--from", dest="nga", help="Data e fillimit e filtrit / filter start (inclusive)"
    )
    fields.add_argument(
        "--deri", "--to", dest="deri", help="Data e mbarimit e filtrit / filter end (inclusive)"
    )
    fields.add_argument(
        "--muaji", "--month", help="Muaji per raportin (muaj-Vit) / month for the report"
    )

    output = parser.add_argument_group("dalja / output")
    output.add_argument(
        "--gjuha",
        "--language",
        dest="gjuha",
        choices=["sq", "en"],
        default="sq",
        help="Gjuha e nderfaqes / interface language (default: sq)",
    )
    output.add_argument(
        "--pa-ngjyra",
        "--no-color",
        action="store_true",
        dest="pa_ngjyra",
        help="Dalje pa ngjyra / disable colored output",
    )

    return parser


def resolve_filter_dates(args):
    """Turn the filter flags into a (start, end, title, ok) tuple."""
    if args.data:
        target = parse_date(args.data)
        if target is None:
            print(paint(t("invalid_date"), RED))
            return None, None, None, False
        return target, target, t("transactions_on", date=format_date(target)), True

    start = end = None
    if args.nga:
        start = parse_date(args.nga)
        if start is None:
            print(paint(t("invalid_date"), RED))
            return None, None, None, False
    if args.deri:
        end = parse_date(args.deri)
        if end is None:
            print(paint(t("invalid_date"), RED))
            return None, None, None, False
    if start and end and end < start:
        print(paint(t("end_before_start"), RED))
        return None, None, None, False

    if start and end:
        title = t("transactions_between", start=format_date(start), end=format_date(end))
    elif start:
        title = t("transactions_from", start=format_date(start))
    elif end:
        title = t("transactions_until", end=format_date(end))
    else:
        title = t("all_transactions")
    return start, end, title, True


def do_add(app, args, trans_type):
    """Add a transaction from flags, prompting for anything not supplied."""
    from .ui import (
        prompt_amount,
        prompt_category,
        prompt_date,
        prompt_description,
        prompt_subcategory,
    )

    if args.pershkrimi is not None:
        description = args.pershkrimi.strip()
        if not description:
            print(paint(t("empty_description"), RED))
            return False
    else:
        description = prompt_description()

    if args.shuma is not None:
        amount = parse_amount(args.shuma)
        if amount is None:
            print(paint(t("invalid_amount"), RED))
            return False
    else:
        amount = prompt_amount()

    if args.data is not None:
        if parse_date(args.data) is None:
            print(paint(t("invalid_date"), RED))
            return False
        date = args.data.strip()
    else:
        date = prompt_date()

    if args.kategoria is not None:
        category = args.kategoria.strip() or DEFAULT_CATEGORY
    else:
        category = prompt_category(app.categories_for(trans_type))

    # An omitted --nenkategoria with --kategoria given means "no subcategory",
    # so a fully-flagged invocation stays non-interactive.
    if args.nenkategoria is not None:
        subcategory = args.nenkategoria.strip()
    elif args.kategoria is not None:
        subcategory = ""
    else:
        subcategory = prompt_subcategory(app, trans_type, category)

    transaction = app.add_transaction(trans_type, description, amount, date, category, subcategory)
    print(paint(t("added", type=type_label(trans_type)), BOLD))
    print_budget_warning(check_after_adding(app.budgets, app.transactions, transaction))
    return True


def do_set_budget(app, args):
    category, raw_amount = args.cakto_buxhet
    amount = parse_amount(raw_amount)
    if amount is None or amount == 0:
        print(paint(t("invalid_amount"), RED))
        return
    app.set_budget(category.strip(), amount)
    print(paint(t("budget_saved", category=category.strip()), BOLD))


def do_report(app, args):
    if args.muaji:
        parsed = parse_month(args.muaji)
        if parsed is None:
            print(paint(t("invalid_month"), RED))
            return
        year, month = parsed
    else:
        year, month = month_of(today())
    print_monthly_report(month_report(app.transactions, year, month))


def run_cli(app, args):
    """Run whatever the flags asked for. Returns True if anything ran."""
    did_something = False

    if args.perserit:
        generated = app.process_recurring()
        if generated:
            print(paint(t("generated", count=len(generated)), BOLD))
        else:
            print(t("nothing_due"))
        did_something = True

    if args.cakto_buxhet:
        do_set_budget(app, args)
        did_something = True

    if args.shto_te_ardhura or args.shto_shpenzime:
        do_add(app, args, INCOME if args.shto_te_ardhura else EXPENSE)
        did_something = True

    if args.kerko:
        matches = sort_by_date(search(app.transactions, args.kerko))
        print_transactions(
            numbered(app.transactions, matches), t("transactions_matching", term=args.kerko)
        )
        if matches:
            print_summary(matches, calculate_totals(matches), t("filter_totals"))
        did_something = True

    if args.lista:
        start, end, title, ok = resolve_filter_dates(args)
        if not ok:
            return True
        matches = sort_by_date(filter_by_dates(app.transactions, start, end))
        print_transactions(numbered(app.transactions, matches), title)
        if matches and (start or end):
            print_summary(matches, calculate_totals(matches), t("filter_totals"))
        did_something = True

    if args.perseritjet:
        print_recurring(app.recurring_rules, today())
        did_something = True

    if args.buxhetet:
        year, month = month_of(today())
        print_budgets(all_statuses(app.budgets, app.transactions, year, month), year, month)
        did_something = True

    if args.raporti:
        do_report(app, args)
        did_something = True

    if args.gjendja:
        print_summary(app.transactions, calculate_totals(app.transactions))
        did_something = True

    return did_something


def main(argv=None):
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    set_language(args.gjuha)
    colors.configure(force_off=args.pa_ngjyra)

    # The menu prints its own load notice; flag mode stays quiet unless
    # something goes wrong.
    interactive = not any(
        [
            args.lista,
            args.gjendja,
            args.raporti,
            args.buxhetet,
            args.cakto_buxhet,
            args.shto_te_ardhura,
            args.shto_shpenzime,
            args.perserit,
            args.perseritjet,
            args.kerko,
        ]
    )

    app = FinanceApp(quiet=not interactive)
    app.load()

    # Catch up on anything due since the last run. --perserit reports the same
    # work in full, so skip the quiet pass in that case.
    if not args.perserit:
        generated = app.process_recurring()
        if generated and interactive:
            print(paint(t("generated", count=len(generated)), BOLD))

    try:
        if not run_cli(app, args):
            run_menu(app)
    except (KeyboardInterrupt, EOFError):
        print()
        print(t("goodbye"))
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
