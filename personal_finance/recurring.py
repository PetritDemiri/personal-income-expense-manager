"""Transaksionet e perseritura / Recurring transactions.

Each occurrence is computed as "the k-th occurrence counted from the rule's
start date", never as "one step after the previous occurrence". That
distinction is what stops a short month from shifting a schedule permanently: a
rule anchored on the 31st fires 31 Jan, 28 Feb, then 31 Mar again.
"""

import datetime

from .dates import add_months, format_date, parse_date

# Adding a frequency is one entry here: a function returning the k-th
# occurrence after the start date, where k=0 is the start date itself.
FREQUENCIES = {
    "javore": lambda start, k: start + datetime.timedelta(weeks=k),
    "mujore": lambda start, k: add_months(start, k),
    "vjetore": lambda start, k: add_months(start, 12 * k),
}

# Guard against a malformed rule producing an unbounded loop.
MAX_OCCURRENCES = 5000


def due_occurrences(rule, as_of):
    """Every occurrence of a rule due by `as_of` but not yet generated."""
    advance = FREQUENCIES.get(rule.frequency)
    start = parse_date(rule.starts_on)
    if advance is None or start is None:
        return []

    last = parse_date(rule.generated_upto) if rule.generated_upto else None
    occurrences = []
    for k in range(MAX_OCCURRENCES):
        occurrence = advance(start, k)
        if occurrence > as_of:
            break
        if last is None or occurrence > last:
            occurrences.append(occurrence)
    return occurrences


def next_occurrence(rule):
    """The first occurrence of a rule not yet generated."""
    advance = FREQUENCIES.get(rule.frequency)
    start = parse_date(rule.starts_on)
    if advance is None or start is None:
        return None

    last = parse_date(rule.generated_upto) if rule.generated_upto else None
    for k in range(MAX_OCCURRENCES):
        occurrence = advance(start, k)
        if last is None or occurrence > last:
            return occurrence
    return None


def generate_due(database, rules, as_of):
    """Insert every due transaction and advance each rule, atomically.

    Returns the transactions created. Safe to call as often as you like: a rule
    records the last date it produced, so the same occurrence is never created
    twice.

    Both the inserts and the rule updates happen inside one database
    transaction. With two CSV files this could not be done, and a crash between
    the two writes regenerated every occurrence on the next run.
    """
    generated = []
    pending = []

    for rule in rules:
        for occurrence in due_occurrences(rule, as_of):
            pending.append((rule, occurrence))

    if not pending:
        return generated

    with database.atomic() as connection:
        for rule, occurrence in pending:
            transaction = rule.to_transaction(occurrence)
            database.add_transaction(transaction, connection=connection)
            generated.append(transaction)
            rule.generated_upto = format_date(occurrence)
            database.set_rule_generated_upto(rule.id, rule.generated_upto, connection=connection)

    return generated
