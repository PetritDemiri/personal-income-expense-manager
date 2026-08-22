"""Logjika e aplikacionit / Application service layer.

Sits between the interface and the database. Holds no data of its own: there is
no cached list of transactions any more, because a cached list can drift from
what is stored and every write used to have to rewrite the whole table to keep
them in step. Reads are queries; writes are single rows.

Nothing here reads from stdin, and printing is limited to failures the user
must know about.
"""

from .accounts import find_account
from .budgets import check_after_adding
from .colors import RED, paint
from .database import Database
from .i18n import t
from .models import (
    Account,
    Category,
    RecurringRule,
    Subcategory,
    Transaction,
)
from .recurring import generate_due
from .reports import ordered_options
from .schema import EXPENSE


class FinanceApp:
    """Everything the interface can ask the program to do."""

    def __init__(self, database=None, path=None, quiet=False):
        self.db = database or Database(path)
        self.quiet = quiet

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    @property
    def location(self):
        return self.db.path

    def _fail(self, key, **kwargs):
        print(paint(t(key, **kwargs), RED))

    # -- reading -----------------------------------------------------------

    def transactions(self, **filters):
        """Transaction views, filtered in SQL. Oldest first."""
        return self.db.transactions(**filters)

    def transaction(self, transaction_id):
        return self.db.transaction(transaction_id)

    def count(self):
        return self.db.count_transactions()

    # -- transactions ------------------------------------------------------

    def add_transaction(
        self,
        kind,
        description,
        amount,
        occurred_on,
        category=None,
        subcategory=None,
        account_id=None,
        to_account_id=None,
    ):
        """Create one transaction. Category and subcategory are names.

        Naming rather than referencing is deliberate: a category typed for the
        first time is created here, so entry never stalls on defining things
        up front.
        """
        category_id = self.db.ensure_category(category, kind) if category else None
        subcategory_id = (
            self.db.ensure_subcategory(subcategory, category_id)
            if subcategory and category_id
            else None
        )
        transaction = Transaction(
            kind=kind,
            description=description,
            amount=amount,
            occurred_on=occurred_on,
            category_id=category_id,
            subcategory_id=subcategory_id,
            account_id=account_id,
            to_account_id=to_account_id,
        )
        self.db.add_transaction(transaction)
        return transaction

    def update_transaction(self, transaction_id, **fields):
        """Change one transaction. Names are resolved to ids first."""
        if "category" in fields:
            kind = fields.get("kind") or self.db.transaction(transaction_id).kind
            name = fields.pop("category")
            fields["category_id"] = self.db.ensure_category(name, kind) if name else None
        if "subcategory" in fields:
            name = fields.pop("subcategory")
            category_id = fields.get("category_id")
            if category_id is None:
                existing = self.db.transaction(transaction_id)
                category_id = existing.category_id if existing else None
            fields["subcategory_id"] = (
                self.db.ensure_subcategory(name, category_id) if name and category_id else None
            )
        self.db.update_transaction(transaction_id, **fields)
        return self.db.transaction(transaction_id)

    def delete_transaction(self, transaction_id):
        removed = self.db.transaction(transaction_id)
        self.db.delete_transaction(transaction_id)
        return removed

    # -- categories --------------------------------------------------------

    def categories(self, kind):
        return self.db.categories(kind)

    def category_names(self, kind):
        """Category names for a kind, ordered for display."""
        return ordered_options([c.name for c in self.db.categories(kind)])

    def subcategory_names(self, category_name, kind):
        """Subcategory names under a category, ordered for display."""
        category = self.db.category_by_name(category_name, kind) if category_name else None
        if category is None:
            return []
        return ordered_options([s.name for s in self.db.subcategories(category.id)])

    def category_name_map(self):
        """Every category id mapped to its name, for rendering labels."""
        return {c.id: c.name for c in self.db.categories()}

    def add_category(self, name, kind):
        return self.db.add_category(Category(name=name, kind=kind))

    def add_subcategory(self, name, category_id):
        return self.db.add_subcategory(Subcategory(name=name, category_id=category_id))

    # -- accounts ----------------------------------------------------------

    def accounts(self):
        return self.db.accounts()

    def has_accounts(self):
        """Whether any account exists.

        Everything account-related is skipped when this is False, so someone
        who never creates one sees the program exactly as it was.
        """
        return bool(self.db.accounts())

    def account_by_name(self, name):
        return find_account(self.db.accounts(), name)

    def add_account(self, name, kind, opening):
        return self.db.add_account(
            Account(name=name, kind=kind, opening=opening, position=len(self.db.accounts()))
        )

    def update_account(self, account_id, **fields):
        """Change an account. A rename needs no other rows touched.

        Transactions reference an id, so renaming is one row - where before it
        meant finding and rewriting every transaction and rule that named it.
        """
        self.db.update_account(account_id, **fields)
        return self.db.account(account_id)

    def delete_account(self, account_id):
        """Delete an account. Its transactions survive, unassigned."""
        removed = self.db.account(account_id)
        affected = len(self.db.transactions(account_id=account_id))
        self.db.delete_account(account_id)
        return removed, affected

    def assign_unassigned_to(self, account_id):
        """Put every account-less transaction and rule on one account."""
        assigned = 0
        with self.db.atomic() as connection:
            for view in self.db.transactions():
                if view.account_id is not None:
                    continue
                if view.to_account_id == account_id:
                    continue
                connection.execute(
                    "UPDATE transactions SET account_id = ? WHERE id = ?",
                    (account_id, view.id),
                )
                assigned += 1
            for rule in self.db.recurring_rules():
                if rule.account_id is None:
                    connection.execute(
                        "UPDATE recurring_rules SET account_id = ? WHERE id = ?",
                        (account_id, rule.id),
                    )
                    assigned += 1
        return assigned

    # -- budgets -----------------------------------------------------------

    def budgets(self):
        return self.db.budgets()

    def set_budget(self, category_name, amount, kind=EXPENSE):
        category_id = self.db.ensure_category(category_name, kind)
        if category_id is None:
            return None
        self.db.set_budget(category_id, amount)
        return category_id

    def delete_budget(self, category_id):
        self.db.delete_budget(category_id)

    def budget_warning(self, transaction):
        """Status worth warning about after adding a transaction, or None."""
        return check_after_adding(
            self.db.budgets(),
            self.category_name_map(),
            self.db.transactions(),
            transaction,
        )

    # -- recurring ---------------------------------------------------------

    def recurring_rules(self):
        return self.db.recurring_rules()

    def add_recurring_rule(
        self,
        kind,
        description,
        amount,
        frequency,
        starts_on,
        category=None,
        subcategory=None,
        account_id=None,
    ):
        category_id = self.db.ensure_category(category, kind) if category else None
        subcategory_id = (
            self.db.ensure_subcategory(subcategory, category_id)
            if subcategory and category_id
            else None
        )
        rule = RecurringRule(
            kind=kind,
            description=description,
            amount=amount,
            frequency=frequency,
            starts_on=starts_on,
            category_id=category_id,
            subcategory_id=subcategory_id,
            account_id=account_id,
        )
        self.db.add_recurring_rule(rule)
        return rule

    def delete_recurring_rule(self, rule_id):
        rules = {r.id: r for r in self.db.recurring_rules()}
        removed = rules.get(rule_id)
        self.db.delete_recurring_rule(rule_id)
        return removed

    def process_recurring(self, as_of=None):
        """Generate any recurring transactions that have come due."""
        from .dates import today

        try:
            return generate_due(self.db, self.db.recurring_rules(), as_of or today())
        except Exception as error:
            self._fail("save_error", error=error)
            return []
