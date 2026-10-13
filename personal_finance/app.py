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
    CategoryRule,
    RecurringRule,
    Subcategory,
    Transaction,
)
from .recurring import generate_due
from .reports import ordered_options
from .schema import EXPENSE


class FinanceApp:
    """Everything the interface can ask the program to do."""

    def __init__(self, database=None, path=None, quiet=False, user=None, auto_user=True):
        self.db = database or Database(path, user=user, auto_user=auto_user)
        self.quiet = quiet

    @property
    def has_users(self):
        return bool(self.db.users())

    def session_user(self):
        """The user a running session belongs to, or None.

        A session means the person already said who they are and proved it, so
        asking again inside the twelve hours would be asking twice. Signing
        out ends it and returns them to the screen, which is how somebody else
        takes a turn.
        """
        from . import auth

        token = auth.read_token(self.db.path)
        return auth.session_user(self.db, token)

    def sign_in_applies(self):
        """Whether this installation has a sign-in screen at all.

        With one user and no password there is nothing to choose between and
        nothing to prove, so the screen never appears - and signing out has
        nowhere to return to.
        """
        users = self.users()
        return len(users) > 1 or any(user.has_password for user in users)

    @property
    def setup_pending(self):
        """Whether a generated administrator is still waiting to be claimed.

        An abandoned setup leaves a user row with no password on it, which the
        ordinary path would read as a single-user installation that never
        wanted one - and let the next person straight in. Until the account
        has a name and password of its own, the database is not ready for
        anybody. That includes a setup abandoned after the right code was
        typed: counting only codes not yet typed let exactly that case through.
        """
        from . import auth

        return bool(auth.unclaimed_admins(self.db.connection))

    def use_user(self, user_id):
        """Work as this user for the rest of the session."""
        self.db.use_user(user_id)

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

    def subcategories(self, category_id):
        return self.db.subcategories(category_id)

    def category_exists(self, name, kind):
        return self.db.category_by_name(name, kind) is not None

    def subcategory_exists(self, name, category_id):
        return self.db.subcategory_by_name(name, category_id) is not None

    def rename_category(self, category_id, name):
        """Rename a category. One row, since transactions reference an id."""
        self.db.update_category(category_id, name)
        return self.db.category(category_id)

    def rename_subcategory(self, subcategory_id, name):
        self.db.update_subcategory(subcategory_id, name)
        return self.db.subcategory(subcategory_id)

    def delete_category(self, category_id):
        """Delete a category. Returns (removed, affected transactions).

        Its transactions survive, uncategorised; its subcategories and any
        budget go with it.
        """
        removed = self.db.category(category_id)
        affected = len(self.db.transactions(category_id=category_id))
        self.db.delete_category(category_id)
        return removed, affected

    def delete_subcategory(self, subcategory_id):
        removed = self.db.subcategory(subcategory_id)
        affected = len(self.db.transactions(subcategory_id=subcategory_id))
        self.db.delete_subcategory(subcategory_id)
        return removed, affected

    # -- users -------------------------------------------------------------

    @property
    def user_id(self):
        return self.db.user_id

    def current_user(self):
        return self.db.user()

    def users(self):
        return self.db.users()

    def add_user(self, name, password=None, is_admin=False):
        return self.db.add_user(name, password, is_admin)

    def set_admin(self, user_id, is_admin):
        self.db.set_admin(user_id, is_admin)

    def admin_count(self):
        return sum(1 for u in self.db.users() if u.is_admin)

    def rename_user(self, user_id, name):
        self.db.rename_user(user_id, name)
        return self.db.user(user_id)

    def set_password(self, user_id, password):
        """Store a password, which the sign-in screen will then ask for."""
        self.db.set_password(user_id, password)

    def delete_user(self, user_id):
        removed = self.db.user(user_id)
        self.db.delete_user(user_id)
        return removed

    def user_exists(self, name):
        return self.db.user_by_name(name) is not None

    # -- first run and signing in -------------------------------------------

    def needs_setup(self):
        from . import auth

        return auth.needs_setup(self.db)

    def create_admin(self):
        from . import auth
        from .locations import documents_directory

        return auth.create_admin(self.db, documents_directory())

    def forget_unclaimed_setup(self):
        """Discard a first-run code nobody claimed, and delete its file.

        See auth.forget_setup: a code lives only while the program that
        showed it is open.
        """
        from . import auth
        from .locations import documents_directory

        auth.forget_setup(self.db.connection, documents_directory())

    def check_setup_password(self, typed):
        from . import auth

        return auth.check_setup_password(self.db, typed)

    def pending_admin(self):
        from . import auth

        row = auth.pending_setup(self.db)
        return (row["user_id"], row["name"]) if row else (None, None)

    def complete_setup(self, user_id, name, password, setup_file=None):
        """Claim the generated account, and sign in as it.

        A session is started here because the person has just proved who they
        are twice over - they held the generated password and chose a new one.
        Asking them to sign in again immediately would be asking them to prove
        it a third time.
        """
        from . import auth

        auth.complete_setup(self.db, user_id, name, password, setup_file)
        self.db.use_user(user_id)
        auth.purge_expired(self.db)
        auth.write_token(self.db.path, auth.start_session(self.db, user_id))

    @property
    def is_admin(self):
        user = self.current_user()
        return bool(user and user.is_admin)

    def require_admin(self):
        """Whether the signed-in user may manage other people's accounts."""
        return self.is_admin

    # -- signing in ---------------------------------------------------------

    def signed_in_user(self):
        """The user a running session belongs to, or None."""
        from . import auth

        token = auth.read_token(self.db.path)
        return auth.session_user(self.db, token)

    def needs_login(self):
        """Whether this user must sign in before the program will show anything.

        Only when they have set a password and have no running session. A user
        without one never sees a prompt, so a single-person installation is
        unchanged.
        """
        from . import auth

        user = self.current_user()
        if user is None or not user.has_password:
            return False
        token = auth.read_token(self.db.path)
        return auth.session_user(self.db, token) != user.id

    def sign_in(self, password, user_id=None):
        """Check a password and start a session. Returns True on success."""
        from . import auth

        user_id = user_id or self.user_id
        if not auth.authenticate(self.db, user_id, password):
            return False
        self.db.use_user(user_id)
        auth.purge_expired(self.db)
        auth.write_token(self.db.path, auth.start_session(self.db, user_id))
        return True

    def sign_out(self):
        from . import auth

        auth.end_session(self.db, auth.read_token(self.db.path))
        auth.clear_token(self.db.path)

    def change_password(self, current, new_password):
        from . import auth

        changed = auth.change_password(self.db, self.user_id, current, new_password)
        if changed:
            auth.clear_token(self.db.path)
        return changed

    def begin_reset(self, user_id):
        """Write a one-time code for a user, and return (code, path)."""
        from . import auth
        from .locations import documents_directory

        user = self.db.user(user_id)
        return auth.begin_reset(self.db, user_id, documents_directory(), user.name)

    def check_reset_code(self, user_id, typed):
        from . import auth

        return auth.check_code(self.db, user_id, typed)

    def finish_reset(self, user_id, new_password, code_file=None):
        from . import auth

        auth.finish_reset(self.db, user_id, new_password, code_file)
        auth.clear_token(self.db.path)

    # -- category rules ----------------------------------------------------

    def category_rules(self):
        return self.db.category_rules()

    def rule_for(self, description):
        """The rule that applies to a description, or None."""
        from .models import best_rule

        return best_rule(self.db.category_rules(), description)

    def add_category_rule(self, pattern, category_name, kind, subcategory_name=None):
        """Create a rule, making the category if it does not exist yet."""
        category_id = self.db.ensure_category(category_name, kind)
        if category_id is None:
            return None
        subcategory_id = (
            self.db.ensure_subcategory(subcategory_name, category_id) if subcategory_name else None
        )
        rule = CategoryRule(
            pattern=pattern.strip(),
            category_id=category_id,
            subcategory_id=subcategory_id,
        )
        self.db.add_category_rule(rule)
        return rule

    def delete_category_rule(self, rule_id):
        removed = next((r for r in self.db.category_rules() if r.id == rule_id), None)
        self.db.delete_category_rule(rule_id)
        return removed

    def rule_exists(self, pattern):
        return self.db.rule_by_pattern(pattern) is not None

    def count_matching(self, pattern):
        return self.db.count_matching(pattern)

    def apply_rules(self, candidates):
        """Fill in the category on any candidate a rule matches.

        Only where the file did not already say. Something the import itself
        provided is better evidence than a pattern written weeks ago.
        Returns how many were filled in.
        """
        rules = self.db.category_rules()
        if not rules:
            return 0
        from .models import best_rule
        from .schema import TRANSFER

        filled = 0
        for candidate in candidates:
            if candidate.category or candidate.kind == TRANSFER:
                continue
            rule = best_rule(rules, candidate.description)
            if rule is None:
                continue
            candidate.category = rule.category
            candidate.subcategory = rule.subcategory
            filled += 1
        return filled

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

    # -- history -----------------------------------------------------------

    def history(self, entity=None, entity_id=None, limit=50):
        """Recorded changes, newest first."""
        return self.db.audit_entries(entity=entity, entity_id=entity_id, limit=limit)

    def reference_names(self):
        """Every referenced row's name, keyed by table then id.

        Passed to the history display so a change of category reads as a
        category name rather than as a number.
        """
        return {
            "categories": {c.id: c.name for c in self.db.categories()},
            "accounts": {a.id: a.name for a in self.db.accounts()},
            "subcategories": {
                s.id: s.name
                for category in self.db.categories()
                for s in self.db.subcategories(category.id)
            },
        }

    def transaction_history(self, transaction_id, limit=50):
        """Everything that has happened to one transaction."""
        return self.db.audit_entries(entity="transactions", entity_id=transaction_id, limit=limit)

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
