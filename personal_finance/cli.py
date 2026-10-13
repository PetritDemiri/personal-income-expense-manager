"""Rreshti i komandes / Command-line interface.

Albanian flags are primary; English aliases are accepted for all of them. With
no flags at all, the interactive menu runs.
"""

import argparse
import contextlib
import os
import sys
from decimal import Decimal, InvalidOperation

from . import colors, console
from .accounts import balances_for, count_unassigned, find_account
from .app import FinanceApp
from .budgets import all_statuses
from .colors import BOLD, CYAN, DIM, RED, YELLOW, paint, type_color
from .config import DATA_DIR_ENV, DATABASE_FILE, data_path
from .database import UnknownUser, carry_over
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
    "importo",
    "grafiku",
    "hyr",
    "dil",
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
    actions.add_argument(
        "--hyr",
        "--login",
        action="store_true",
        dest="hyr",
        help="Hyr dhe fillo nje sesion / sign in and start a session",
    )
    actions.add_argument(
        "--dil",
        "--logout",
        action="store_true",
        dest="dil",
        help="Dil nga sesioni / sign out",
    )
    actions.add_argument(
        "--grafiku",
        "--chart",
        dest="grafiku",
        nargs="?",
        const="",
        metavar="MUAJT",
        help="Shfaq grafiket; me nje numer muajsh (3, 6 ose 12) shfaq grafikun "
        "muaj pas muaji / show charts",
    )
    actions.add_argument(
        "--importo",
        "--import",
        dest="importo",
        metavar="SKEDARI",
        help="Importo transaksione nga nje skedar, me shikim paraprak "
        "/ import transactions from a file, with a preview",
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
        "--perdoruesi",
        "--user",
        dest="perdoruesi",
        metavar="EMRI",
        help="Cili perdorues; parazgjedhja eshte i pari / which user to work as",
    )
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


def run_sessions(app):
    """Sign in, work, sign out, and offer to sign in again.

    The program loops between the sign-in screen and the menu rather than
    ending when someone signs out. Leaving is offered at the screen, which is
    the one place where nobody's data is on show.

    Returns False when the program ends because someone could not sign in -
    three wrong passwords, or a reset abandoned - so that is not mistaken for
    leaving on purpose.
    """
    from .ui import choose_user, sign_in_as

    while True:
        # A running session is a question already answered. Skipped only on
        # the way in: signing out ends the session, so the loop comes back to
        # the screen and somebody else can take a turn.
        running = app.session_user()
        if running is not None:
            app.use_user(running)
        elif app.sign_in_applies():
            # Asked outright rather than guessed. Picking a user and then
            # demanding their password left a second person unable to reach
            # their own data at all.
            chosen = choose_user(app)
            if chosen is None:
                print()
                print(paint(t("goodbye"), CYAN))
                return True
            app.use_user(chosen)
            if not sign_in_as(app, chosen):
                return False

        if run_menu(app):
            return True


def do_charts(app, args):
    """Draw the charts. A number of months draws only the monthly one."""
    from .charts import SPANS, account_bars, category_bars, monthly_bars
    from .dates import format_month
    from .display import (
        print_account_chart,
        print_category_chart,
        print_monthly_chart,
    )

    rows = app.transactions()
    year, month = month_of(today())

    if args.grafiku:
        if not args.grafiku.isdigit() or int(args.grafiku) not in SPANS:
            spans = ", ".join(str(s) for s in SPANS)
            print(paint(t("invalid_span", spans=spans), RED))
            return
        span = int(args.grafiku)
        _months, income, expenses = monthly_bars(rows, today(), span)
        print_monthly_chart(income, expenses, t("chart_months_title", span=span))
        return

    print_category_chart(
        category_bars(rows, EXPENSE, year, month),
        t("chart_categories_title", month=format_month(year, month)),
        type_color(EXPENSE),
    )
    print_category_chart(
        category_bars(rows, INCOME, year, month),
        t("chart_income_title", month=format_month(year, month)),
        type_color(INCOME),
    )
    if app.has_accounts():
        print_account_chart(
            account_bars(balances_for(app.accounts(), rows)),
            t("chart_accounts_title"),
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

    if args.dil:
        app.sign_out()
        print(paint(t("logged_out"), BOLD))
        did_something = True

    if args.hyr:
        # Explicit sign-in. Already handled below for every other command, so
        # this only reports when there was nothing to do.
        user = app.current_user()
        if not user.has_password:
            print(paint(t("no_password_set", name=user.name), YELLOW))
        did_something = True

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

    if args.grafiku is not None:
        do_charts(app, args)
        did_something = True

    if args.raporti:
        do_report(app, args)
        did_something = True

    if args.importo:
        from .ui import import_from_file

        # The preview is the whole safety of this feature, so the flag opens
        # the same interactive review rather than importing blind.
        import_from_file(app, path=args.importo)
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


# Exit codes after which a person at the program is given time to read why it
# ended: a failure (a cancelled or failed setup, a refused sign-in), and a user
# that does not exist. Not Ctrl+C - leaving on purpose needs no reading.
FAILURE_CODES = (1, 2)


def database_location(args):
    """The database to open, carrying an old one over to the new place first.

    Before 3.10.0 the database lived in whichever folder the program was
    started from. The first time this version runs from a folder that still
    holds one, and the new place has none yet, it is copied across - never
    moved: the original stays exactly where it was, so nothing can be lost if
    the copy goes wrong. If it cannot be copied, it is used where it is.
    """
    if args.baza:
        return args.baza
    path = data_path(DATABASE_FILE)
    if os.environ.get(DATA_DIR_ENV) or os.path.exists(path):
        return path
    old = os.path.abspath(DATABASE_FILE)
    if not os.path.isfile(old) or os.path.abspath(path) == old:
        return path

    import sqlite3

    try:
        carry_over(old, path)
    except (OSError, sqlite3.Error):
        print(paint(t("data_not_carried", path=path, old=old), YELLOW))
        return old
    print(paint(t("data_carried", path=path), BOLD))
    print(paint(t("data_old_kept", path=old), DIM))
    return path


def main(argv=None):
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    set_language(args.gjuha)
    colors.configure(force_off=args.pa_ngjyra)

    # A flag counts as given when it is anything but absent. Two of them take
    # an optional value and default to an empty string when written bare, and
    # an empty string is falsy - so testing truthiness alone read `--grafiku`
    # as if it had not been given at all.
    def was_given(name):
        value = getattr(args, name, None)
        return value is not None and value is not False

    interactive = not any(was_given(name) for name in ACTION_FLAGS)
    # A person at a terminal, as opposed to a script, a pipe or the tests. Only
    # then is the window named, the tests run on a first launch, and the window
    # held open after a failure - none of which a script would want.
    attended = interactive and console.attended()

    if attended:
        console.set_title(t("window_title"))
    try:
        code = run_program(args, interactive, attended)
    except Exception:
        if console.window_closed():
            # The terminal went away mid-way, and whatever broke on the way
            # out broke because of that. There is nobody to tell.
            return 129
        path = console.log_crash()
        if not attended:
            raise
        console.report_crash(path)
        code = 1
    finally:
        if attended:
            console.restore_title()

    if attended and code in FAILURE_CODES and not console.window_closed():
        console.pause(t("press_enter_close"))
    return code


def run_program(args, interactive, attended):
    """Everything main does between reading the flags and handing back a code."""
    if attended:
        from .selftest import run_on_first_launch

        run_on_first_launch(console.pause)

    path = database_location(args)
    try:
        app = FinanceApp(
            path=path,
            quiet=not interactive,
            user=args.perdoruesi,
            # No user is invented for an empty database, whichever way the
            # program was started. Inventing one for a flagged run let a single
            # `--lista` claim an empty database silently, with no password on
            # it, and the generated-credentials flow then never ran because
            # users existed.
            auto_user=False,
        )
    except UnknownUser as error:
        print(paint(t("unknown_user", name=error.args[0]), RED))
        return 2

    # Catch up on anything due since the last run. --perserit reports the same
    # work in full, so the quiet pass is skipped in that case.
    if not args.perserit:
        generated = app.process_recurring()
        if generated and interactive:
            print(paint(t("generated", count=len(generated)), BOLD))

    # A database nobody has claimed cannot be worked in. The setup is
    # interactive by nature - a generated password has to be read from a file
    # and typed back - so a flagged run says what to do rather than inventing
    # an owner or prompting where nobody may be watching.
    if not interactive and (not app.has_users or app.setup_pending):
        print(paint(t("setup_required"), YELLOW))
        app.close()
        return 1

    # While a person is at the program, closing its window clears a first-run
    # code just as leaving it does. On Windows that has to happen in a handler
    # with a connection of its own; elsewhere the close becomes an ordinary
    # exit, and the clean-up below runs on the way out.
    watch = contextlib.nullcontext()
    if attended:
        from . import auth
        from .locations import documents_directory

        documents = documents_directory()
        watch = console.CloseWatch(lambda: auth.forget_setup_at(path, documents))

    try:
        with watch:
            if interactive:
                from .ui import run_first_setup

                # A first-run code lives only while the program that showed it
                # is open, so whatever an earlier run left - closed, killed, or
                # abandoned after the right code - is cleared before anything
                # else is decided.
                app.forget_unclaimed_setup()

                # An empty database is claimed by whoever holds the generated
                # credentials, not by whoever happens to run the program.
                if not app.has_users or app.setup_pending:
                    if not run_first_setup(app):
                        return 1
                elif not app.sign_in_applies():
                    app.use_user(app.users()[0].id)
            elif not args.dil and app.needs_login():
                from .ui import sign_in

                if not sign_in(app):
                    return 1

            if not run_cli(app, args) and not run_sessions(app):
                return 1
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
        if interactive:
            import sqlite3

            try:
                app.forget_unclaimed_setup()
            except sqlite3.Error:
                pass
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
