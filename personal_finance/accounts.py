"""Llogarite / Accounts.

An account is somewhere money sits: cash in a wallet, a bank account, a card.
Pure calculation only - no printing, no input.

Accounts are optional throughout. With none defined the program behaves
exactly as it did before: no account prompt, no account column, one combined
balance. Everything here degrades to that case rather than special-casing it.

Two things make per-account balances correct rather than merely plausible:

An opening balance, because an account that already held 500 euros when
tracking began does not have a balance of zero.

Transfers, because moving money between your own accounts is neither income
nor an expense. Recording an ATM withdrawal as an expense would make the total
across all accounts fall by money you still have; recording nothing would
leave the bank too high and the cash too low.
"""

from decimal import Decimal

from .config import EXPENSE, INCOME, TRANSFER

ZERO = Decimal("0.00")

# Key used for transactions with no account, so they can still be totalled.
UNASSIGNED = ""


class AccountBalance:
    """One account's opening balance, movements, and resulting balance."""

    def __init__(self, name, account_type="", opening=ZERO):
        self.name = name
        self.account_type = account_type
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
        return self.name == UNASSIGNED

    def __repr__(self):
        name = self.name or "<pa llogari>"
        return f"AccountBalance({name!r}, balance={self.balance})"


def apply_transaction(balances, transaction):
    """Add one transaction's effect to whichever balances it touches.

    A transfer touches two: it leaves one account and arrives in another.
    """
    source = balances.get(transaction.llogaria)
    if source is not None:
        source.count += 1

    if transaction.lloji == INCOME:
        if source is not None:
            source.income += transaction.shuma
    elif transaction.lloji == EXPENSE:
        if source is not None:
            source.expenses += transaction.shuma
    elif transaction.lloji == TRANSFER:
        if source is not None:
            source.transferred_out += transaction.shuma
        destination = balances.get(transaction.llogaria_dest)
        if destination is not None:
            destination.transferred_in += transaction.shuma
            destination.count += 1


def balances_for(accounts, transactions):
    """Balances for every account, plus unassigned transactions if any exist.

    The unassigned entry appears only when something actually needs it, so a
    user who has always used accounts never sees a stray row.
    """
    balances = {
        account.emri: AccountBalance(account.emri, account.lloji, account.gjendja_fillestare)
        for account in accounts
    }

    needs_unassigned = any(
        not t.llogaria or (t.lloji == TRANSFER and not t.llogaria_dest) for t in transactions
    )
    if needs_unassigned:
        balances[UNASSIGNED] = AccountBalance(UNASSIGNED)

    for transaction in transactions:
        apply_transaction(balances, transaction)

    ordered = [balances[account.emri] for account in accounts if account.emri in balances]
    if UNASSIGNED in balances:
        ordered.append(balances[UNASSIGNED])
    return ordered


def total_balance(accounts, transactions):
    """Combined balance across every account, including unassigned money."""
    return sum((item.balance for item in balances_for(accounts, transactions)), ZERO)


def find_account(accounts, name):
    """The account with this name, or None. Matching ignores case."""
    if not name:
        return None
    needle = name.strip().casefold()
    for account in accounts:
        if account.emri.casefold() == needle:
            return account
    return None


def account_names(accounts):
    """Account names in the order they were defined."""
    return [account.emri for account in accounts]


def filter_by_account(transactions, name):
    """Transactions touching one account, transfers in either direction included."""
    return [
        t
        for t in transactions
        if t.llogaria == name or (t.lloji == TRANSFER and t.llogaria_dest == name)
    ]


def rename_account(accounts, transactions, rules, old_name, new_name):
    """Rename an account and repoint everything that referenced it.

    Names are the reference, so a rename that missed a transaction would
    silently orphan it into the unassigned pile.
    """
    account = find_account(accounts, old_name)
    if account is None:
        return 0

    touched = 0
    for transaction in transactions:
        if transaction.llogaria == account.emri:
            transaction.llogaria = new_name
            touched += 1
        if transaction.llogaria_dest == account.emri:
            transaction.llogaria_dest = new_name
            touched += 1
    for rule in rules:
        if rule.llogaria == account.emri:
            rule.llogaria = new_name
            touched += 1

    account.emri = new_name
    return touched


def unassign_account(transactions, rules, name):
    """Clear an account from everything that referenced it, before deleting it.

    Deleting an account leaves its transactions behind - they still happened.
    They become unassigned rather than pointing at something gone.
    """
    touched = 0
    for transaction in transactions:
        if transaction.llogaria == name:
            transaction.llogaria = ""
            touched += 1
        if transaction.llogaria_dest == name:
            transaction.llogaria_dest = ""
            touched += 1
    for rule in rules:
        if rule.llogaria == name:
            rule.llogaria = ""
            touched += 1
    return touched


def assign_unassigned(transactions, rules, name):
    """Give every transaction and recurring rule with no account to `name`.

    Returns (assigned, skipped). Recurring rules are included deliberately: a
    rule with no account would keep generating unassigned transactions after
    the existing ones were tidied up.

    A transfer whose other side is already this account is skipped rather than
    turned into a transfer from an account to itself.
    """
    assigned = 0
    skipped = 0

    for transaction in transactions:
        if transaction.llogaria:
            continue
        if transaction.lloji == TRANSFER and transaction.llogaria_dest == name:
            skipped += 1
            continue
        transaction.llogaria = name
        assigned += 1

    for rule in rules:
        if not rule.llogaria:
            rule.llogaria = name
            assigned += 1

    return assigned, skipped


def count_unassigned(transactions, rules):
    """How many transactions and rules currently have no account."""
    return sum(1 for t in transactions if not t.llogaria) + sum(1 for r in rules if not r.llogaria)
