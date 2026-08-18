"""Logjika e aplikacionit / Application service layer.

Holds the loaded data and the operations on it. The UI and the CLI both drive
this object, so behaviour cannot drift between the interactive menu and the
command-line flags.

Nothing here reads from stdin. Printing is limited to load/save notices, which
callers can silence.
"""

from .colors import RED, YELLOW, paint
from .config import DEFAULT_CATEGORY, SUGGESTED_CATEGORIES, SUGGESTED_SUBCATEGORIES
from .dates import today
from .i18n import t
from .models import Account, Transaction
from .recurring import FREQUENCIES, generate_due
from .reports import known_categories, known_subcategories, sort_by_date
from .storage import CsvStorage


class FinanceApp:
    """The application's data and the operations that change it."""

    def __init__(self, storage=None, quiet=False):
        self.storage = storage or CsvStorage()
        self.quiet = quiet
        self.transactions = []
        self.recurring_rules = []
        self.budgets = []
        self.accounts = []

    # -- loading and saving ------------------------------------------------

    def _notice(self, message):
        if not self.quiet:
            print(message)

    def load(self):
        """Load every data file, reporting anything that had to be skipped."""
        try:
            result = self.storage.load_transactions()
            self.transactions = list(result.records)
            self._notice(t("loaded", count=len(self.transactions), file=self.storage.location))
            if result.skipped:
                self._notice(paint(t("skipped_rows", count=result.skipped), YELLOW))
        except Exception as error:
            print(paint(t("load_error", error=error), RED))
            self.transactions = []

        try:
            result = self.storage.load_recurring(valid_frequencies=FREQUENCIES)
            self.recurring_rules = list(result.records)
            if result.skipped:
                self._notice(paint(t("skipped_rows", count=result.skipped), YELLOW))
        except Exception as error:
            print(paint(t("load_error", error=error), RED))
            self.recurring_rules = []

        try:
            result = self.storage.load_budgets()
            self.budgets = list(result.records)
            if result.skipped:
                self._notice(paint(t("skipped_rows", count=result.skipped), YELLOW))
        except Exception as error:
            print(paint(t("load_error", error=error), RED))
            self.budgets = []

        try:
            result = self.storage.load_accounts()
            self.accounts = list(result.records)
            if result.skipped:
                self._notice(paint(t("skipped_rows", count=result.skipped), YELLOW))
        except Exception as error:
            print(paint(t("load_error", error=error), RED))
            self.accounts = []

    def save_transactions(self, announce=True):
        try:
            self.storage.save_transactions(self.transactions)
            if announce:
                self._notice(t("saved", count=len(self.transactions), file=self.storage.location))
            return True
        except Exception as error:
            print(paint(t("save_error", error=error), RED))
            return False

    def save_recurring(self, announce=False):
        try:
            self.storage.save_recurring(self.recurring_rules)
            return True
        except Exception as error:
            print(paint(t("save_error", error=error), RED))
            return False

    def save_accounts(self, announce=False):
        try:
            self.storage.save_accounts(self.accounts)
            return True
        except Exception as error:
            print(paint(t("save_error", error=error), RED))
            return False

    def save_budgets(self, announce=False):
        try:
            self.storage.save_budgets(self.budgets)
            return True
        except Exception as error:
            print(paint(t("save_error", error=error), RED))
            return False

    # -- transactions ------------------------------------------------------

    def add_transaction(
        self,
        trans_type,
        description,
        amount,
        date,
        category=None,
        subcategory=None,
        account=None,
        destination=None,
    ):
        """Create, store and save a transaction. Returns the new object."""
        transaction = Transaction(
            lloji=trans_type,
            pershkrimi=description,
            shuma=amount,
            data=date,
            kategoria=category or DEFAULT_CATEGORY,
            nenkategoria=(subcategory or "").strip(),
            llogaria=(account or "").strip(),
            llogaria_dest=(destination or "").strip(),
        )
        self.transactions.append(transaction)
        self.save_transactions()
        return transaction

    def update_transaction(self, index, **changes):
        """Apply changes to one transaction and save."""
        transaction = self.transactions[index]
        for name, value in changes.items():
            if value is not None:
                setattr(transaction, name, value)
        self.save_transactions()
        return transaction

    def delete_transaction(self, index):
        """Remove one transaction and save. Returns the removed object."""
        removed = self.transactions.pop(index)
        self.save_transactions()
        return removed

    def sorted_transactions(self):
        """Transactions in chronological order."""
        return sort_by_date(self.transactions)

    def categories_for(self, trans_type):
        """Suggested categories for a type, including ones already in use."""
        return known_categories(self.transactions, trans_type, SUGGESTED_CATEGORIES)

    def subcategories_for(self, trans_type, category):
        """Suggested subcategories for a category, including ones already in use."""
        return known_subcategories(self.transactions, trans_type, category, SUGGESTED_SUBCATEGORIES)

    # -- recurring ---------------------------------------------------------

    def process_recurring(self, as_of=None):
        """Generate any recurring transactions that have come due.

        Returns the list generated - empty if there was nothing to do.
        """
        as_of = as_of or today()
        generated = generate_due(self.recurring_rules, self.transactions, as_of)
        if generated:
            # Both must land together. Saving them separately means a crash in
            # between leaves the transactions written while the rules still
            # think nothing was generated, so the next run creates them again.
            try:
                self.storage.save_recurring_run(self.transactions, self.recurring_rules)
            except Exception as error:
                print(paint(t("save_error", error=error), RED))
        return generated

    def add_recurring(self, rule):
        self.recurring_rules.append(rule)
        self.save_recurring()
        return rule

    def delete_recurring(self, index):
        removed = self.recurring_rules.pop(index)
        self.save_recurring()
        return removed

    # -- budgets -----------------------------------------------------------

    # -- accounts ----------------------------------------------------------

    def has_accounts(self):
        """Whether any account is defined.

        Everything account-related is skipped when this is False, so a user who
        never creates one sees the program exactly as it was.
        """
        return bool(self.accounts)

    def add_account(self, name, account_type, opening):
        account = Account(emri=name, lloji=account_type, gjendja_fillestare=opening)
        self.accounts.append(account)
        self.save_accounts()
        return account

    def update_account(self, index, name=None, account_type=None, opening=None):
        """Change an account, repointing every reference if it was renamed."""
        from .accounts import rename_account

        account = self.accounts[index]
        renamed = name is not None and name != account.emri

        if renamed:
            rename_account(
                self.accounts,
                self.transactions,
                self.recurring_rules,
                account.emri,
                name,
            )
        if account_type is not None:
            account.lloji = account_type
        if opening is not None:
            account.gjendja_fillestare = opening

        if renamed:
            # The rename touched transactions and rules too, so all three must
            # land together or a transaction is left pointing at a name that
            # no longer exists.
            try:
                self.storage.save_account_change(
                    self.accounts, self.transactions, self.recurring_rules
                )
            except Exception as error:
                print(paint(t("save_error", error=error), RED))
        else:
            self.save_accounts()
        return account

    def delete_account(self, index):
        """Delete an account, leaving its transactions behind as unassigned."""
        from .accounts import unassign_account

        removed = self.accounts.pop(index)
        touched = unassign_account(self.transactions, self.recurring_rules, removed.emri)
        try:
            self.storage.save_account_change(self.accounts, self.transactions, self.recurring_rules)
        except Exception as error:
            print(paint(t("save_error", error=error), RED))
        return removed, touched

    def assign_unassigned_to(self, name):
        """Move every account-less transaction and rule onto one account.

        Saved as a single change, since it rewrites transactions and rules
        together with the account list.
        """
        from .accounts import assign_unassigned

        assigned, skipped = assign_unassigned(self.transactions, self.recurring_rules, name)
        if assigned:
            try:
                self.storage.save_account_change(
                    self.accounts, self.transactions, self.recurring_rules
                )
            except Exception as error:
                print(paint(t("save_error", error=error), RED))
        return assigned, skipped

    def set_budget(self, category, amount):
        from .budgets import set_budget

        budget = set_budget(self.budgets, category, amount)
        self.save_budgets()
        return budget

    def delete_budget(self, index):
        removed = self.budgets.pop(index)
        self.save_budgets()
        return removed
