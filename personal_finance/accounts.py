"""Llogarite / Accounts.

An account is somewhere money sits: cash, a bank account, a card. Pure
calculation - no printing, no database.

Accounts remain optional throughout. With none defined the program behaves as
it always did: no account prompt, no account column, one combined balance.

Two things make per-account balances correct rather than merely plausible. An
opening balance, because an account that already held money when tracking began
does not start at zero. And transfers, because moving money between your own
accounts is neither income nor an expense: recording an ATM withdrawal as
spending would drop the combined total by money still held, and recording
nothing would leave one account too high and the other too low.
"""

from .reports import ZERO
from .schema import EXPENSE, INCOME, TRANSFER

# Key for transactions tied to no account, so they can still be totalled.
UNASSIGNED = None


class AccountBalance:
    """One account's opening balance, movements and resulting balance."""

    def __init__(self, account_id, name, kind="", opening=ZERO):
        self.account_id = account_id
        self.name = name
        self.kind = kind
        self.opening = opening
        self.income = ZERO
        self.expenses = ZERO
        self.transferred_in = ZERO
        self.transferred_out = ZERO
        self.count = 0

    @property
    def balance(self):
        return (
            self.opening + self.income - self.expenses + self.transferred_in - self.transferred_out
        )

    @property
    def is_unassigned(self):
        return self.account_id is UNASSIGNED

    def __repr__(self):
        shown = self.name or "<pa llogari>"
        return f"AccountBalance({shown!r}, balance={self.balance})"


def apply_transaction(balances, item):
    """Add one transaction's effect to whichever balances it touches.

    A transfer touches two: it leaves one account and arrives in another.
    """
    source = balances.get(item.account_id)
    if source is not None:
        source.count += 1

    if item.kind == INCOME:
        if source is not None:
            source.income += item.amount
    elif item.kind == EXPENSE:
        if source is not None:
            source.expenses += item.amount
    elif item.kind == TRANSFER:
        if source is not None:
            source.transferred_out += item.amount
        destination = balances.get(item.to_account_id)
        if destination is not None:
            destination.transferred_in += item.amount
            destination.count += 1


def balances_for(accounts, transactions):
    """Balances for every account, plus unassigned money if any exists.

    The unassigned entry appears only when something needs it, so someone who
    has always used accounts never sees a stray row.
    """
    balances = {
        account.id: AccountBalance(account.id, account.name, account.kind, account.opening)
        for account in accounts
    }

    needs_unassigned = any(
        item.account_id is None or (item.kind == TRANSFER and item.to_account_id is None)
        for item in transactions
    )
    if needs_unassigned:
        balances[UNASSIGNED] = AccountBalance(UNASSIGNED, None)

    for item in transactions:
        apply_transaction(balances, item)

    ordered = [balances[a.id] for a in accounts if a.id in balances]
    if UNASSIGNED in balances:
        ordered.append(balances[UNASSIGNED])
    return ordered


def total_balance(accounts, transactions):
    """Combined balance across every account, including unassigned money."""
    return sum((item.balance for item in balances_for(accounts, transactions)), ZERO)


def find_account(accounts, name):
    """The account with this name, or None. Matching ignores case."""
    from .models import name_key

    if not name:
        return None
    needle = name_key(name)
    for account in accounts:
        if name_key(account.name) == needle:
            return account
    return None


def filter_by_account(transactions, account_id):
    """Transactions touching one account, transfers in either direction."""
    return [
        item
        for item in transactions
        if item.account_id == account_id
        or (item.kind == TRANSFER and item.to_account_id == account_id)
    ]


def count_unassigned(transactions, rules):
    """How many transactions and rules are tied to no account."""
    return sum(1 for t in transactions if t.account_id is None) + sum(
        1 for r in rules if r.account_id is None
    )
