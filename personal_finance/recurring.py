"""Transaksionet e perseritura / Recurring transactions.

Each occurrence is computed as "the k-th occurrence counted from the rule's
start date", never as "one step after the previous occurrence". That
distinction is what stops a short month from shifting a schedule permanently:
a rule anchored on the 31st fires 31 Jan, 28 Feb, then 31 Mar again.
"""

import datetime

from .dates import add_months

# Adding a frequency is a single entry here: a function returning the k-th
# occurrence after the start date, where k=0 is the start date itself.
FREQUENCIES = {
    "javore": lambda start, k: start + datetime.timedelta(weeks=k),
    "mujore": lambda start, k: add_months(start, k),
    "vjetore": lambda start, k: add_months(start, 12 * k),
}

# Guard against a malformed rule producing an unbounded loop.
MAX_OCCURRENCES = 5000


def due_occurrences(rule, as_of):
    """Every occurrence of a rule that is due by `as_of` but not yet generated."""
    advance = FREQUENCIES.get(rule.frekuenca)
    start = rule.start_date
    if advance is None or start is None:
        return []

    last = rule.last_generated
    occurrences = []
    for k in range(MAX_OCCURRENCES):
        occurrence = advance(start, k)
        if occurrence > as_of:
            break
        if last is None or occurrence > last:
            occurrences.append(occurrence)
    return occurrences


def next_occurrence(rule, as_of=None):
    """The first occurrence of a rule that has not been generated yet."""
    advance = FREQUENCIES.get(rule.frekuenca)
    start = rule.start_date
    if advance is None or start is None:
        return None

    last = rule.last_generated
    for k in range(MAX_OCCURRENCES):
        occurrence = advance(start, k)
        if last is None or occurrence > last:
            return occurrence
    return None


def generate_due(rules, transactions, as_of):
    """Append every due transaction to `transactions`, updating each rule.

    Returns the list of transactions that were generated. Safe to call as
    often as you like: a rule records the last date it produced, so the same
    occurrence is never created twice.
    """
    from .dates import format_date

    generated = []
    for rule in rules:
        for occurrence in due_occurrences(rule, as_of):
            transaction = rule.to_transaction(occurrence)
            transactions.append(transaction)
            generated.append(transaction)
            rule.data_e_fundit = format_date(occurrence)
    return generated
