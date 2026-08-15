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
from .models import Transaction
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

    def save_budgets(self, announce=False):
        try:
            self.storage.save_budgets(self.budgets)
            return True
        except Exception as error:
            print(paint(t("save_error", error=error), RED))
            return False

    # -- transactions ------------------------------------------------------

    def add_transaction(
        self, trans_type, description, amount, date, category=None, subcategory=None
    ):
        """Create, store and save a transaction. Returns the new object."""
        transaction = Transaction(
            lloji=trans_type,
            pershkrimi=description,
            shuma=amount,
            data=date,
            kategoria=category or DEFAULT_CATEGORY,
            nenkategoria=(subcategory or "").strip(),
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

    def set_budget(self, category, amount):
        from .budgets import set_budget

        budget = set_budget(self.budgets, category, amount)
        self.save_budgets()
        return budget

    def delete_budget(self, index):
        removed = self.budgets.pop(index)
        self.save_budgets()
        return removed
