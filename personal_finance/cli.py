"""Rreshti i komandes / Command-line interface.

Albanian flags are primary; English aliases are accepted for all of them. With
no flags at all, the interactive menu runs.
"""

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation

from . import colors
from .accounts import balances_for, count_unassigned, find_account
from .app import FinanceApp
from .budgets import all_statuses
from .colors import BOLD, RED, YELLOW, paint
from .config import DATABASE_FILE, data_path
from .dates import current_date_str, format_date, month_of, parse_date, parse_month, today
from .display import (
    print_accounts,
    print_budget_warning,
    print_budgets,
    print_history,
    print_monthly_report,
    print_recurring,
    print_summary,
    print_transactions,
)
from .i18n import set_language, t, type_label
from .models import ACCOUNT_KINDS, parse_amount
from .reports import calculate_totals, month_report, sort_by_date
from .schema import EXPENSE, INCOME, TRANSFER
from .ui import numbered, run_menu

# Every flag that performs an action. Any of these means flag mode rather than
# the interactive menu. Kept in one place because it was previously spelled out
# inline and drifted twice, letting start-up notices leak into scripted output.
# A test asserts this matches the parser's action group exactly.
ACTION_FLAGS = (
    "lista",
    "gjendja",
    "raporti",
    "buxhetet",
    "cakto_buxhet",
    "shto_te_ardhura",
    "shto_shpenzime",
    "perserit",
    "perseritjet",
    "kerko",
    "llogarite",
    "shto_llogari",
    "cakto_pa_llogari",
    "transfero",
    "eksporto",
    "historia",
)


def action_flag_dests(parser):
    """The dest names in the parser's action group, for the sync test."""
    for group in parser._action_groups:
        if group.title and group.title.startswith("veprimet"):
            return tuple(action.dest for action in group._group_actions)
    return ()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="financat",
        description="Menaxheri i te Ardhurave dhe Shpenzimeve Personale / "
        "Personal Income and Expense Manager. "
        "Pa asnje flamur, hapet menuja interaktive.",
        epilog="Shembuj / Examples:\n"
        "  %(prog)s --lista\n"
        "  %(prog)s --lista --nga 01-08-2026 --deri 31-08-2026\n"
        "  %(prog)s --kerko ushqim\n"
        "  %(prog)s --raporti --muaji 07-2026\n"
        '  %(prog)s --shto-shpenzime --pershkrimi "Qera" --shuma 300 '
        "--kategoria Qera\n"
        "  %(prog)s --eksporto transaksionet.csv\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--ndihma", action="help", help="Shfaq kete mesazh ndihme dhe dil / show help"
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
    actions.add_argument(
        "--llogarite",
        "--accounts",
        action="store_true",
        help="Shfaq gjendjen e secilës llogari / per-account balances",
    )
    actions.add_argument(
        "--shto-llogari",
        "--add-account",
        dest="shto_llogari",
        nargs=3,
        metavar=("EMRI", "LLOJI", "GJENDJA"),
        help="Shto nje llogari / add an account",
    )
    actions.add_argument(
        "--cakto-pa-llogari",
        "--assign-unassigned",
        dest="cakto_pa_llogari",
        metavar="EMRI",
        help="Cakto transaksionet pa llogari / assign account-less rows",
    )
    actions.add_argument(
        "--transfero",
        "--transfer",
        dest="transfero",
        nargs=2,
        metavar=("NGA", "TEK"),
        help="Transfero mes dy llogarive / transfer between accounts",
    )
    actions.add_argument(
        "--eksporto",
        "--export",
        dest="eksporto",
        metavar="SKEDARI",
        help="Eksporto ne nje skedar CSV / export to CSV",
    )
    actions.add_argument(
        "--historia",
        "--history",
        dest="historia",
        nargs="?",
        const="",
        metavar="NUMRI",
        help="Shfaq historikun e ndryshimeve; me nje numer, vetem ate "
        "transaksion / show the change history",
    )

    fields = parser.add_argument_group("fushat dhe filtrat / fields and filters")
    fields.add_argument("--pershkrimi", "--description", help="Pershkrimi / description")
    fields.add_argument("--shuma", "--amount", help="Shuma / amount")
    fields.add_argument("--data", "--date", help="Data (dite-muaj-Vit) / date")
    fields.add_argument("--kategoria", "--category", help="Kategoria / category")
    fields.add_argument("--nenkategoria", "--subcategory", help="Nenkategoria / subcategory")
    fields.add_argument("--llogaria", "--account", help="Llogaria / account")
    fields.add_argument("--nga", "--from", dest="nga", help="Data e fillimit / filter start")
    fields.add_argument("--deri", "--to", dest="deri", help="Data e mbarimit / filter end")
    fields.add_argument("--muaji", "--month", help="Muaji (muaj-Vit) / month")

    storage = parser.add_argument_group("ruajtja / storage")
    storage.add_argument(
        "--baza",
        "--database",
        dest="baza",
        help="Shtegu i bazes se te dhenave / path to the database",
    )

    output = parser.add_argument_group("dalja / output")
    output.add_argument(
        "--gjuha",
        "--language",
        dest="gjuha",
        choices=["sq", "en"],
        default="sq",
        help="Gjuha e nderfaqes / interface language",
    )
    output.add_argument(
        "--ndares",
        "--delimiter",
        dest="ndares",
        default=",",
        help="Ndaresi i kolonave per eksportim / export delimiter",
    )
    output.add_argument(
        "--detaje",
        "--details",
        action="store_true",
        dest="detaje",
        help="Shfaq kur u regjistrua dhe u ndryshua secili rresht "
        "/ show when each row was recorded and last changed",
    )
    output.add_argument(
        "--pa-ngjyra",
        "--no-color",
        action="store_true",
        dest="pa_ngjyra",
        help="Dalje pa ngjyra / disable colored output",
    )

    return parser


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def resolve_filter_dates(args):
    """Turn the filter flags into (start, end, title, ok)."""
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


def selected_transactions(app, args):
    """Apply the filter flags in SQL. Returns (rows, title, ok).

    Shared by --lista and --eksporto so a filter selects the same set however
    it is used.
    """
    start, end, title, ok = resolve_filter_dates(args)
    if not ok:
        return [], None, False

    filters = {"start": start, "end": end}
    if args.kerko:
        filters["search"] = args.kerko
    if args.llogaria:
        matched = find_account(app.accounts(), args.llogaria)
        if matched is None:
            print(paint(t("unknown_account", name=args.llogaria), RED))
            return [], None, False
        filters["account_id"] = matched.id
        title = f"{title} [{matched.name}]"

    return app.transactions(**filters), title, True


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def do_add(app, args, kind):
    """Add a transaction from flags, prompting for anything not supplied."""
    from .ui import (
        prompt_account,
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
        occurred_on = args.data.strip()
    else:
        occurred_on = prompt_date()

    if args.kategoria is not None:
        category = args.kategoria.strip() or None
    else:
        category = prompt_category(app, kind)

    # An omitted --nenkategoria alongside --kategoria means "none", so a fully
    # flagged invocation stays non-interactive.
    if args.nenkategoria is not None:
        subcategory = args.nenkategoria.strip() or None
    elif args.kategoria is not None:
        subcategory = None
    else:
        subcategory = prompt_subcategory(app, kind, category)

    if args.llogaria is not None:
        requested = args.llogaria.strip()
        matched = find_account(app.accounts(), requested)
        if requested and matched is None:
            print(paint(t("unknown_account", name=requested), RED))
            return False
        account_id = matched.id if matched else None
    elif app.has_accounts():
        account_id = prompt_account(app)
    else:
        account_id = None

    transaction = app.add_transaction(
        kind, description, amount, occurred_on, category, subcategory, account_id
    )
    print(paint(t("added", type=type_label(kind)), BOLD))
    print_budget_warning(app.budget_warning(transaction))
    return True


def do_add_account(app, args):
    name, kind, opening_raw = args.shto_llogari
    name = name.strip()

    if not name:
        print(paint(t("empty_description"), RED))
        return
    if app.account_by_name(name) is not None:
        print(paint(t("account_exists"), RED))
        return

    matched_kind = next((k for k in ACCOUNT_KINDS if k.casefold() == kind.strip().casefold()), None)
    if matched_kind is None:
        print(paint(t("invalid_account_type", types=", ".join(ACCOUNT_KINDS)), RED))
        return

    try:
        opening = Decimal(opening_raw.strip())
        if not opening.is_finite():
            raise InvalidOperation
    except (InvalidOperation, AttributeError):
        print(paint(t("invalid_opening"), RED))
        return

    app.add_account(name, matched_kind, opening)
    print(paint(t("account_added", name=name), BOLD))


def do_transfer(app, args):
    source_raw, destination_raw = args.transfero
    accounts = app.accounts()

    source = find_account(accounts, source_raw)
    if source is None:
        print(paint(t("unknown_account", name=source_raw), RED))
        return
    destination = find_account(accounts, destination_raw)
    if destination is None:
        print(paint(t("unknown_account", name=destination_raw), RED))
        return
    if source.id == destination.id:
        print(paint(t("same_account"), RED))
        return

    amount = parse_amount(args.shuma) if args.shuma is not None else None
    if amount is None:
        print(paint(t("invalid_amount"), RED))
        return

    description = (args.pershkrimi or t("type_transfer")).strip()

    if args.data is not None:
        if parse_date(args.data) is None:
            print(paint(t("invalid_date"), RED))
            return
        occurred_on = args.data.strip()
    else:
        occurred_on = current_date_str()

    app.add_transaction(
        TRANSFER,
        description,
        amount,
        occurred_on,
        account_id=source.id,
        to_account_id=destination.id,
    )
    print(paint(t("transfer_added"), BOLD))


def do_assign_unassigned(app, args):
    target = app.account_by_name(args.cakto_pa_llogari)
    if target is None:
        print(paint(t("unknown_account", name=args.cakto_pa_llogari), RED))
        return
    if not count_unassigned(app.transactions(), app.recurring_rules()):
        print(paint(t("nothing_unassigned"), YELLOW))
        return
    assigned = app.assign_unassigned_to(target.id)
    print(paint(t("assigned", count=assigned, name=target.name), BOLD))


def do_set_budget(app, args):
    category, raw_amount = args.cakto_buxhet
    amount = parse_amount(raw_amount, allow_zero=False)
    if amount is None:
        print(paint(t("invalid_amount"), RED))
        return
    app.set_budget(category.strip(), amount)
    print(paint(t("budget_saved", category=category.strip()), BOLD))


def do_export(app, args):
    from .export import ALLOWED_DELIMITERS, export_transactions

    if args.ndares not in ALLOWED_DELIMITERS:
        readable = ", ".join(d if d != "\t" else "tab" for d in ALLOWED_DELIMITERS)
        print(paint(t("invalid_delimiter", allowed=readable), RED))
        return

    rows, _title, ok = selected_transactions(app, args)
    if not ok:
        return
    if not rows:
        print(paint(t("export_empty"), YELLOW))
        return

    try:
        count, written_to = export_transactions(
            args.eksporto, sort_by_date(rows), delimiter=args.ndares
        )
    except Exception as error:
        print(paint(t("export_failed", error=error), RED))
        return
    print(paint(t("exported", count=count, path=written_to), BOLD))


def do_history(app, args):
    """Show recorded changes, optionally for one transaction."""
    names = app.reference_names()
    if not args.historia:
        print_history(app.history(limit=25), names=names)
        return

    rows = app.transactions()
    try:
        position = int(args.historia)
        if position < 1 or position > len(rows):
            raise ValueError
    except ValueError:
        print(paint(t("invalid_number"), RED))
        return

    chosen = rows[position - 1]
    print_history(
        app.transaction_history(chosen.id),
        t("history_for", number=chosen.id),
        names=names,
    )


def do_report(app, args):
    if args.muaji:
        parsed = parse_month(args.muaji)
        if parsed is None:
            print(paint(t("invalid_month"), RED))
            return
        year, month = parsed
    else:
        year, month = month_of(today())
    print_monthly_report(month_report(app.transactions(), year, month))


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

    if args.shto_llogari:
        do_add_account(app, args)
        did_something = True

    if args.cakto_pa_llogari:
        do_assign_unassigned(app, args)
        did_something = True

    if args.transfero:
        do_transfer(app, args)
        did_something = True

    if args.cakto_buxhet:
        do_set_budget(app, args)
        did_something = True

    if args.shto_te_ardhura or args.shto_shpenzime:
        do_add(app, args, INCOME if args.shto_te_ardhura else EXPENSE)
        did_something = True

    if args.eksporto:
        do_export(app, args)
        did_something = True

    if args.kerko and not args.eksporto:
        rows, title, ok = selected_transactions(app, args)
        if ok:
            print_transactions(
                numbered(app.transactions(), rows),
                t("transactions_matching", term=args.kerko),
            )
            if rows:
                print_summary(rows, calculate_totals(rows), t("filter_totals"))
        did_something = True

    if args.lista:
        rows, title, ok = selected_transactions(app, args)
        if not ok:
            return True
        print_transactions(numbered(app.transactions(), rows), title, show_times=args.detaje)
        if rows and (args.nga or args.deri or args.data or args.llogaria):
            print_summary(rows, calculate_totals(rows), t("filter_totals"))
        did_something = True

    if args.perseritjet:
        print_recurring(
            app.recurring_rules(),
            today(),
            app.category_name_map(),
            {a.id: a.name for a in app.accounts()},
        )
        did_something = True

    if args.llogarite:
        print_accounts(balances_for(app.accounts(), app.transactions()))
        did_something = True

    if args.buxhetet:
        year, month = month_of(today())
        print_budgets(
            all_statuses(app.budgets(), app.category_name_map(), app.transactions(), year, month),
            year,
            month,
        )
        did_something = True

    if args.raporti:
        do_report(app, args)
        did_something = True

    if args.historia is not None:
        do_history(app, args)
        did_something = True

    if args.gjendja:
        rows = app.transactions()
        print_summary(rows, calculate_totals(rows))
        if app.has_accounts():
            print_accounts(balances_for(app.accounts(), rows))
        did_something = True

    return did_something


def main(argv=None):
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    set_language(args.gjuha)
    colors.configure(force_off=args.pa_ngjyra)

    interactive = not any(getattr(args, name, None) for name in ACTION_FLAGS)
    app = FinanceApp(path=args.baza or data_path(DATABASE_FILE), quiet=not interactive)

    # Catch up on anything due since the last run. --perserit reports the same
    # work in full, so the quiet pass is skipped in that case.
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
    except BrokenPipeError:
        # Whatever was reading the output closed the pipe first - piping into
        # `head` does this. Point stdout at the null device so the interpreter
        # does not warn while shutting down.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
