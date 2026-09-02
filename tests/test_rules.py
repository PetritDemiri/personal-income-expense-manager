"""Tests for category rules.

Rules exist because import produces dozens of rows at once and categorising
each by hand is the tedium that makes importing not worth doing. They apply
during the import preview, where every row is visible and changeable before
anything is written.

They do not apply to manual entry - there they are shown as a suggestion. A
pre-filled category would let a rule written weeks ago decide the answer on an
unread Enter, and a single entry has no preview to catch that.
"""

import sqlite3
from decimal import Decimal

import pytest

from personal_finance.database import Database
from personal_finance.importing import Candidate
from personal_finance.models import CategoryRule, best_rule
from personal_finance.schema import EXPENSE, INCOME, SCHEMA_VERSION, TRANSFER


class TestMatching:
    def test_a_substring_matches(self):
        rule = CategoryRule("STEAM", 1)
        assert rule.matches("E-commerce 0STEAMGAMES.CO")

    def test_matching_ignores_case(self):
        assert CategoryRule("steam", 1).matches("E-commerce 0STEAMGAMES.CO")
        assert CategoryRule("STEAM", 1).matches("e-commerce 0steamgames.co")

    def test_albanian_letters_fold(self):
        """The same folding category names use, so ë matches Ë."""
        assert CategoryRule("Mirëmbajtje", 1).matches("MIRËMBAJTJE per llog")
        assert CategoryRule("MIRËMBAJTJE", 1).matches("mirëmbajtje per llog")

    def test_a_non_match(self):
        assert not CategoryRule("STEAM", 1).matches("Ushqime nga dyqani")

    def test_an_empty_pattern_matches_nothing(self):
        """Otherwise it would silently claim every transaction."""
        assert not CategoryRule("", 1).matches("anything at all")
        assert not CategoryRule("   ", 1).matches("anything at all")


class TestBestRule:
    def test_the_longest_pattern_wins(self):
        """So a general rule and a specific one can coexist without ordering."""
        rules = [CategoryRule("STEAM", 1, id=1), CategoryRule("STEAMGAMES.CO", 2, id=2)]
        assert best_rule(rules, "E-commerce 0STEAMGAMES.CO").pattern == "STEAMGAMES.CO"

    def test_the_general_rule_still_catches_the_rest(self):
        rules = [CategoryRule("STEAM", 1, id=1), CategoryRule("STEAMGAMES.CO", 2, id=2)]
        assert best_rule(rules, "E-commerce 0Steam Purchas").pattern == "STEAM"

    def test_order_in_the_list_does_not_matter(self):
        specific = CategoryRule("STEAMGAMES.CO", 2, id=2)
        general = CategoryRule("STEAM", 1, id=1)
        forwards = best_rule([general, specific], "0STEAMGAMES.CO")
        backwards = best_rule([specific, general], "0STEAMGAMES.CO")
        assert forwards.pattern == backwards.pattern == "STEAMGAMES.CO"

    def test_no_match_returns_none(self):
        assert best_rule([CategoryRule("STEAM", 1, id=1)], "Ushqime") is None

    def test_no_rules_at_all(self):
        assert best_rule([], "anything") is None


class TestStorage:
    def test_a_rule_round_trips(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        rule_id = db.add_category_rule(CategoryRule("STEAM", category_id))
        stored = db.category_rules()[0]
        assert stored.id == rule_id
        assert stored.pattern == "STEAM"
        assert stored.category == "Argëtim"

    def test_the_subcategory_name_comes_back_too(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        subcategory_id = db.ensure_subcategory("Lojëra", category_id)
        db.add_category_rule(CategoryRule("STEAM", category_id, subcategory_id))
        assert db.category_rules()[0].subcategory == "Lojëra"

    def test_duplicate_patterns_are_rejected(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        db.add_category_rule(CategoryRule("STEAM", category_id))
        with pytest.raises(sqlite3.IntegrityError):
            db.add_category_rule(CategoryRule("steam", category_id))

    def test_an_empty_pattern_is_rejected_by_the_database(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection as conn:
                conn.execute(
                    "INSERT INTO category_rules (pattern, pattern_key, category_id) "
                    "VALUES ('   ', 'x', ?)",
                    (category_id,),
                )

    def test_rules_come_back_most_specific_first(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        db.add_category_rule(CategoryRule("STEAM", category_id))
        db.add_category_rule(CategoryRule("STEAMGAMES.CO", category_id))
        assert db.category_rules()[0].pattern == "STEAMGAMES.CO"

    def test_deleting_a_category_takes_its_rules(self, db):
        """A rule pointing at nothing would stop working without saying so."""
        category_id = db.ensure_category("Argëtim", EXPENSE)
        db.add_category_rule(CategoryRule("STEAM", category_id))
        db.delete_category(category_id)
        assert db.category_rules() == []

    def test_deleting_a_subcategory_only_detaches_it(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        subcategory_id = db.ensure_subcategory("Lojëra", category_id)
        db.add_category_rule(CategoryRule("STEAM", category_id, subcategory_id))
        db.delete_subcategory(subcategory_id)

        rules = db.category_rules()
        assert len(rules) == 1
        assert rules[0].subcategory is None

    def test_delete(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        rule_id = db.add_category_rule(CategoryRule("STEAM", category_id))
        db.delete_category_rule(rule_id)
        assert db.category_rules() == []

    def test_lookup_by_pattern_ignores_case(self, db):
        category_id = db.ensure_category("Argëtim", EXPENSE)
        db.add_category_rule(CategoryRule("STEAM", category_id))
        assert db.rule_by_pattern("steam") is not None
        assert db.rule_by_pattern("other") is None


class TestCountMatching:
    def test_counts_existing_transactions(self, app):
        """Said before saving: a pattern matching everything is worth knowing."""
        app.add_transaction(EXPENSE, "STEAMGAMES purchase", Decimal("5"), "01-08-2026")
        app.add_transaction(EXPENSE, "Steam purchase", Decimal("5"), "02-08-2026")
        app.add_transaction(EXPENSE, "Ushqime", Decimal("5"), "03-08-2026")
        assert app.count_matching("Steam") == 2

    def test_counts_nothing_when_nothing_matches(self, app):
        app.add_transaction(EXPENSE, "Ushqime", Decimal("5"), "01-08-2026")
        assert app.count_matching("Steam") == 0


class TestApplyingToCandidates:
    def candidate(self, description, category=None, kind=EXPENSE):
        return Candidate(
            row_number=2,
            kind=kind,
            description=description,
            amount=Decimal("10"),
            occurred_on="01-08-2026",
            category=category,
        )

    def test_a_matching_candidate_gets_its_category(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        candidates = [self.candidate("E-commerce 0STEAMGAMES.CO")]
        assert app.apply_rules(candidates) == 1
        assert candidates[0].category == "Argëtim"

    def test_the_subcategory_is_applied_too(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE, "Lojëra")
        candidates = [self.candidate("0STEAMGAMES.CO")]
        app.apply_rules(candidates)
        assert candidates[0].subcategory == "Lojëra"

    def test_a_category_from_the_file_is_not_overwritten(self, app):
        """What the import itself said beats a pattern written weeks ago."""
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        candidates = [self.candidate("0STEAMGAMES.CO", category="Dhurata")]
        assert app.apply_rules(candidates) == 0
        assert candidates[0].category == "Dhurata"

    def test_transfers_are_left_alone(self, app):
        """A transfer has no category; it is money moved, not money spent."""
        app.add_category_rule("ATM", "Argëtim", EXPENSE)
        candidates = [self.candidate("ATM Deponimi", kind=TRANSFER)]
        assert app.apply_rules(candidates) == 0
        assert candidates[0].category is None

    def test_unmatched_candidates_are_untouched(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        candidates = [self.candidate("Ushqime nga dyqani")]
        assert app.apply_rules(candidates) == 0
        assert candidates[0].category is None

    def test_the_count_returned_is_how_many_were_filled(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        candidates = [
            self.candidate("0STEAMGAMES.CO"),
            self.candidate("0Steam Purchas"),
            self.candidate("Ushqime"),
        ]
        assert app.apply_rules(candidates) == 2

    def test_no_rules_changes_nothing(self, app):
        candidates = [self.candidate("0STEAMGAMES.CO")]
        assert app.apply_rules(candidates) == 0

    def test_the_most_specific_rule_is_the_one_applied(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        app.add_category_rule("STEAMGAMES.CO", "Lojëra", EXPENSE)
        candidates = [self.candidate("E-commerce 0STEAMGAMES.CO")]
        app.apply_rules(candidates)
        assert candidates[0].category == "Lojëra"


class TestServiceLayer:
    def test_adding_a_rule_creates_the_category(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        assert [c.name for c in app.categories(EXPENSE)] == ["Argëtim"]

    def test_rule_for_finds_the_match(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        assert app.rule_for("0STEAMGAMES.CO").category == "Argëtim"
        assert app.rule_for("Ushqime") is None

    def test_rule_exists(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        assert app.rule_exists("steam")
        assert not app.rule_exists("other")

    def test_delete_returns_what_was_removed(self, app):
        rule = app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        removed = app.delete_category_rule(rule.id)
        assert removed.pattern == "STEAM"
        assert app.category_rules() == []

    def test_a_rule_can_target_an_income_category(self, app):
        app.add_category_rule("Paga", "Paga", INCOME)
        assert app.rule_for("Paga e gushtit").category == "Paga"


class TestChangesAreRecorded:
    def test_creating_a_rule_is_audited(self, app):
        app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        entries = app.history(entity="category_rules")
        assert len(entries) == 1
        assert entries[0].action == "create"

    def test_deleting_a_rule_is_audited(self, app):
        rule = app.add_category_rule("STEAM", "Argëtim", EXPENSE)
        app.delete_category_rule(rule.id)
        actions = [e.action for e in app.history(entity="category_rules")]
        assert "delete" in actions

    def test_the_pattern_reads_as_a_label_not_a_column_name(self):
        from personal_finance import i18n
        from personal_finance.display import field_label

        assert field_label("pattern") == "Modeli"
        i18n.set_language("en")
        assert field_label("pattern") == "Pattern"
        i18n.set_language("sq")


class TestMigrationFromVersionFive:
    @staticmethod
    def build_v5(path):
        """A database as 3.5.0 left it: every table and trigger except rules."""
        from personal_finance.schema import AUDITED_TABLES

        from .conftest import audit_triggers_before_users, schema_before_users

        connection = sqlite3.connect(path)
        body = schema_before_users()
        start = body.index("CREATE TABLE category_rules")
        end = body.index("-- Append only.")
        # The index on the rules table goes with it.
        script = body[:start] + body[end:]
        script = "\n".join(line for line in script.split("\n") if "idx_rules_category" not in line)
        connection.executescript(script)
        legacy = audit_triggers_before_users()
        for table in AUDITED_TABLES:
            if table == "category_rules":
                continue
            start = legacy.index(f"CREATE TRIGGER IF NOT EXISTS audit_{table}_insert")
            end = legacy.index(f"audit_{table}_delete")
            end = legacy.index("END;", end) + 4
            connection.executescript(legacy[start:end])
        connection.execute("PRAGMA user_version = 5")
        connection.execute(
            "INSERT INTO categories (name,name_key,kind) VALUES ('Ushqim','ushqim','Shpenzime')"
        )
        connection.execute(
            "INSERT INTO transactions (kind,description,amount_cents,occurred_on) "
            "VALUES ('Shpenzime','Ushqime',4550,'2026-08-03')"
        )
        connection.commit()
        connection.close()

    def test_the_table_is_added_and_the_data_survives(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v5(path)

        db = Database(path)
        assert db.schema_version == SCHEMA_VERSION
        assert db.category_rules() == []
        assert db.count_transactions() == 1
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        db.close()

    def test_rules_work_after_migrating(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v5(path)

        db = Database(path)
        category_id = db.ensure_category("Argëtim", EXPENSE)
        db.add_category_rule(CategoryRule("STEAM", category_id))
        assert len(db.category_rules()) == 1
        db.close()

    def test_the_new_rules_are_audited_after_migrating(self, tmp_path):
        path = str(tmp_path / "finance.db")
        self.build_v5(path)

        db = Database(path)
        category_id = db.ensure_category("Argëtim", EXPENSE)
        db.add_category_rule(CategoryRule("STEAM", category_id))
        assert db.audit_entries(entity="category_rules")
        db.close()
