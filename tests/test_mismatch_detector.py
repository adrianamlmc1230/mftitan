"""Unit tests for core.mismatch_detector module.

Validates Requirements 1.3, 1.4:
- detect_mismatches returns empty when no groups configured
- detect_mismatches returns empty when all teams are in pool
- validate_fixes returns empty for non-conflicting fix actions
"""

import pytest

from core.mismatch_detector import detect_mismatches, validate_fixes, FixAction
from core.models import GlobalGroup, LeagueGroupTeams


# ---------------------------------------------------------------------------
# detect_mismatches unit tests
# ---------------------------------------------------------------------------

class TestDetectMismatches:
    """Unit tests for detect_mismatches()."""

    def test_empty_group_teams_returns_empty(self):
        """When all_group_teams is empty (no groups configured),
        result should be empty regardless of team_pool content.

        Validates: Requirement 1.3 (no groups → nothing to compare)
        """
        team_pool = {"Team A", "Team B", "Team C"}
        group_lookup = {1: GlobalGroup(id=1, name="Top", display_name="Top", display_order=0)}

        result = detect_mismatches(
            all_group_teams=[],
            team_pool=team_pool,
            group_lookup=group_lookup,
        )

        assert result == []

    def test_all_teams_in_pool_returns_empty(self):
        """When every team in group configs exists in team_pool,
        detect_mismatches should return an empty list.

        Validates: Requirement 1.4
        """
        team_pool = {"Team A", "Team B", "Team C", "Team D"}
        group_lookup = {
            1: GlobalGroup(id=1, name="Top", display_name="Top", display_order=0),
            2: GlobalGroup(id=2, name="Weak", display_name="Weak", display_order=1),
        }
        all_group_teams = [
            LeagueGroupTeams(id=1, league_id=10, global_group_id=1, role="current", teams=["Team A", "Team B"]),
            LeagueGroupTeams(id=2, league_id=10, global_group_id=2, role="current", teams=["Team C", "Team D"]),
            LeagueGroupTeams(id=3, league_id=10, global_group_id=1, role="previous", teams=["Team A"]),
        ]

        result = detect_mismatches(
            all_group_teams=all_group_teams,
            team_pool=team_pool,
            group_lookup=group_lookup,
        )

        assert result == []


# ---------------------------------------------------------------------------
# validate_fixes unit tests
# ---------------------------------------------------------------------------

class TestValidateFixes:
    """Unit tests for validate_fixes()."""

    def test_no_conflict_returns_empty(self):
        """When fix actions have no conflicts (no duplicate targets,
        no duplicate operations), validate_fixes should return empty list.

        Validates: Requirement 1.3, 1.4 (validation passes for clean fixes)
        """
        all_group_teams = [
            LeagueGroupTeams(id=1, league_id=10, global_group_id=1, role="current", teams=["Old A", "Old B", "Team C"]),
            LeagueGroupTeams(id=2, league_id=10, global_group_id=2, role="current", teams=["Old X"]),
        ]
        fixes = [
            FixAction(league_id=10, group_name="Top", global_group_id=1, role="current", old_team="Old A", action="replace", new_team="New A"),
            FixAction(league_id=10, group_name="Top", global_group_id=1, role="current", old_team="Old B", action="delete", new_team=None),
            FixAction(league_id=10, group_name="Weak", global_group_id=2, role="current", old_team="Old X", action="replace", new_team="New X"),
        ]

        errors = validate_fixes(fixes=fixes, all_group_teams=all_group_teams)

        assert errors == []


# ---------------------------------------------------------------------------
# Integration tests for apply_fixes (with real SQLite DB)
# Validates Requirements 2.5, 4.2, 4.3
# ---------------------------------------------------------------------------

import json
import os
import shutil
import sqlite3
import tempfile

from core.config_store import ConfigStore
from core.mismatch_detector import apply_fixes


def _make_store() -> tuple[ConfigStore, str]:
    """Create a ConfigStore backed by a temp SQLite DB.

    Returns (store, tmp_dir) so the caller can clean up.
    """
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")
    store = ConfigStore(db_path=db_path)
    return store, tmp_dir


def _seed_data(store: ConfigStore) -> int:
    """Insert a league, two global groups, and league_group_teams rows.

    Returns the league_id.
    """
    league_id = store.create_league(
        continent="ASI", code="TEST1", name_zh="測試聯賽",
    )
    top_id = store.create_global_group("Top", display_name="Top")
    weak_id = store.create_global_group("Weak", display_name="Weak")

    store.set_league_group_teams(league_id, top_id, "current", ["Old A", "Team B", "Team C"])
    store.set_league_group_teams(league_id, weak_id, "current", ["Old X", "Team Y"])

    return league_id


class TestApplyFixesIntegration:
    """Integration tests that exercise apply_fixes against a real SQLite DB.

    Validates Requirements 2.5, 4.2, 4.3.
    """

    # -- helpers ----------------------------------------------------------

    def setup_method(self):
        self.store, self.tmp_dir = _make_store()
        self.league_id = _seed_data(self.store)

    def teardown_method(self):
        # Close the connection before removing the temp dir
        self.store._conn.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -- tests ------------------------------------------------------------

    def test_commit_writes_correctly(self):
        """apply_fixes should commit replace/delete changes to the DB.

        Validates: Requirement 2.5
        """
        # Resolve group IDs from DB
        groups = {g.name: g for g in self.store.list_global_groups()}
        top_id = groups["Top"].id
        weak_id = groups["Weak"].id

        fixes = [
            FixAction(league_id=self.league_id, group_name="Top", global_group_id=top_id, role="current",
                       old_team="Old A", action="replace", new_team="New A"),
            FixAction(league_id=self.league_id, group_name="Weak", global_group_id=weak_id, role="current",
                       old_team="Old X", action="delete", new_team=None),
        ]

        summary = apply_fixes(self.store, self.league_id, fixes)

        # Verify DB state after commit
        top_teams = self.store.get_league_group_teams(self.league_id, top_id, "current")
        weak_teams = self.store.get_league_group_teams(self.league_id, weak_id, "current")

        assert "New A" in top_teams
        assert "Old A" not in top_teams
        # Other teams untouched
        assert "Team B" in top_teams
        assert "Team C" in top_teams

        assert "Old X" not in weak_teams
        assert "Team Y" in weak_teams

    def test_rollback_on_error(self):
        """apply_fixes should rollback all changes when an error occurs.

        Validates: Requirement 4.2
        """
        groups = {g.name: g for g in self.store.list_global_groups()}
        top_id = groups["Top"].id

        # Snapshot teams before the failing call
        teams_before = self.store.get_league_group_teams(self.league_id, top_id, "current")

        # sqlite3.Connection is a C extension type whose attributes are
        # read-only, so we cannot monkey-patch execute directly.
        # Instead, wrap the connection with a proxy that intercepts execute.
        real_conn = self.store._conn

        class _FailingConnProxy:
            """Thin proxy that raises on audit_logs INSERT."""

            def __getattr__(self, name):
                return getattr(real_conn, name)

            def execute(self, sql, params=()):
                if "INSERT INTO audit_logs" in sql:
                    raise sqlite3.OperationalError("simulated DB failure")
                return real_conn.execute(sql, params)

        self.store._conn = _FailingConnProxy()

        fixes = [
            FixAction(league_id=self.league_id, group_name="Top", global_group_id=top_id, role="current",
                       old_team="Old A", action="replace", new_team="New A"),
        ]

        with pytest.raises(RuntimeError, match="修正操作失敗"):
            apply_fixes(self.store, self.league_id, fixes)

        # Restore real connection for verification reads
        self.store._conn = real_conn

        # DB should be unchanged (rollback)
        teams_after = self.store.get_league_group_teams(self.league_id, top_id, "current")
        assert teams_after == teams_before

    def test_audit_log_recorded(self):
        """apply_fixes should write an audit_logs entry on success.

        Validates: Requirement 4.3
        """
        groups = {g.name: g for g in self.store.list_global_groups()}
        top_id = groups["Top"].id

        fixes = [
            FixAction(league_id=self.league_id, group_name="Top", global_group_id=top_id, role="current",
                       old_team="Old A", action="replace", new_team="New A"),
        ]

        apply_fixes(self.store, self.league_id, fixes)

        # Query audit_logs directly
        row = self.store._conn.execute(
            "SELECT * FROM audit_logs WHERE action = 'fix_team_names' ORDER BY id DESC LIMIT 1"
        ).fetchone()

        assert row is not None
        assert row["entity_type"] == "league"
        assert row["entity_id"] == self.league_id

        details = json.loads(row["details"])
        assert "league_id" in details
        assert "changes" in details
        assert details["league_id"] == self.league_id

    def test_summary_format(self):
        """apply_fixes should return a summary dict keyed by
        '{group_name}/{role}' with a list of change descriptions.

        Validates: Requirement 2.5
        """
        groups = {g.name: g for g in self.store.list_global_groups()}
        top_id = groups["Top"].id
        weak_id = groups["Weak"].id

        fixes = [
            FixAction(league_id=self.league_id, group_name="Top", global_group_id=top_id, role="current",
                       old_team="Old A", action="replace", new_team="New A"),
            FixAction(league_id=self.league_id, group_name="Weak", global_group_id=weak_id, role="current",
                       old_team="Old X", action="delete", new_team=None),
        ]

        summary = apply_fixes(self.store, self.league_id, fixes)

        # Keys follow "{group_name}/{role}" pattern
        assert "Top/current" in summary
        assert "Weak/current" in summary

        # Values are non-empty lists of strings
        assert isinstance(summary["Top/current"], list)
        assert len(summary["Top/current"]) > 0
        assert all(isinstance(s, str) for s in summary["Top/current"])

        assert isinstance(summary["Weak/current"], list)
        assert len(summary["Weak/current"]) > 0
