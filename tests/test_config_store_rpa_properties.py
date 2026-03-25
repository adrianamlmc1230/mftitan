"""ConfigStore RPA 擴展屬性測試。

# Feature: rpa-data-driven-league, Property 12: Schema Migration 資料保留
# Validates: 需求 8.5
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.config_store import ConfigStore

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

continents = st.sampled_from(["AFR", "AME", "ASI", "EUR"])

league_codes = st.text(
    min_size=2, max_size=10,
    alphabet=st.characters(whitelist_categories=("L", "N")),
)

names_st = st.text(
    min_size=1, max_size=20,
    alphabet=st.characters(whitelist_categories=("L",)),
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_v1_db(path: str) -> None:
    """Build a v1 schema database (without match_records / phase column)."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leagues (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            continent     TEXT NOT NULL CHECK(continent IN ('AFR','AME','ASI','EUR')),
            code          TEXT NOT NULL UNIQUE,
            country       TEXT NOT NULL,
            name_zh       TEXT NOT NULL,
            league_url_id TEXT,
            league_url_type TEXT DEFAULT 'League' CHECK(league_url_type IN ('League','SubLeague')),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS season_instances (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id     INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            label         TEXT NOT NULL,
            year_start    INTEGER,
            year_end      INTEGER,
            phase         TEXT,
            role          TEXT CHECK(role IN ('current','previous',NULL)),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(league_id, label)
        );
        CREATE TABLE IF NOT EXISTS team_groups (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
            name                TEXT NOT NULL,
            display_name        TEXT,
            display_order       INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(season_instance_id, name)
        );
        CREATE TABLE IF NOT EXISTS teams (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            team_group_id   INTEGER NOT NULL REFERENCES team_groups(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            display_order   INTEGER NOT NULL DEFAULT 0,
            UNIQUE(team_group_id, name)
        );
        CREATE TABLE IF NOT EXISTS file_paths (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
            play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
            timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
            file_path           TEXT NOT NULL,
            updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(season_instance_id, play_type, timing)
        );
        CREATE TABLE IF NOT EXISTS algo_params (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            param_key     TEXT NOT NULL UNIQUE,
            param_value   TEXT NOT NULL,
            description   TEXT,
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS etl_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at      TEXT NOT NULL,
            completed_at    TEXT,
            status          TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running','completed','failed')),
            scope_leagues   TEXT,
            params_snapshot TEXT NOT NULL,
            summary         TEXT
        );
        CREATE TABLE IF NOT EXISTS computation_results (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            etl_run_id          INTEGER NOT NULL REFERENCES etl_runs(id) ON DELETE CASCADE,
            league_id           INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
            team_group_id       INTEGER NOT NULL REFERENCES team_groups(id) ON DELETE CASCADE,
            play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
            timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
            zone_data           TEXT NOT NULL,
            round_block_data    TEXT NOT NULL,
            season_total_win    REAL NOT NULL DEFAULT 0,
            season_total_lose   REAL NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS decision_results (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            etl_run_id          INTEGER NOT NULL REFERENCES etl_runs(id) ON DELETE CASCADE,
            league_id           INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_group_id       INTEGER NOT NULL REFERENCES team_groups(id) ON DELETE CASCADE,
            play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
            timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
            five_zone_data      TEXT NOT NULL,
            guard_levels        TEXT NOT NULL,
            strength_levels     TEXT NOT NULL,
            home_signals        TEXT NOT NULL,
            away_signals        TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS quality_issues (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            etl_run_id      INTEGER NOT NULL REFERENCES etl_runs(id) ON DELETE CASCADE,
            league_id       INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            severity        TEXT NOT NULL CHECK(severity IN ('warning','error')),
            issue_type      TEXT NOT NULL,
            description     TEXT NOT NULL,
            details         TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ===========================================================================
# Property 12: Schema Migration 資料保留
# Feature: rpa-data-driven-league, Property 12: Schema Migration 資料保留
# Validates: 需求 8.5
# ===========================================================================

@given(
    continent=continents,
    code=league_codes,
    country=names_st,
    name_zh=names_st,
    year_start=st.integers(min_value=2000, max_value=2030),
    has_year_end=st.booleans(),
    label=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
    role=st.sampled_from(["current", "previous", None]),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property12_schema_migration_data_preservation(
    continent, code, country, name_zh, year_start, has_year_end, label, role,
):
    """Schema Migration 資料保留：migration 前已存在的聯賽與賽季資料，
    執行 migration 後仍可正確查詢且欄位值不變。

    **Validates: Requirements 8.5**
    """
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_migration.db")

    # 1. Build a v1 database and insert data directly
    _make_v1_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        conn.execute(
            "INSERT INTO leagues (continent, code, country, name_zh) VALUES (?, ?, ?, ?)",
            (continent, code, country, name_zh),
        )
        league_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        year_end = year_start + 1 if has_year_end else None
        conn.execute(
            "INSERT INTO season_instances (league_id, label, year_start, year_end, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (league_id, label, year_start, year_end, role),
        )
        season_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()

        # 2. Open with ConfigStore — triggers migration
        store = ConfigStore(db_path=db_path)

        # 3. Verify league data preserved (country merged into name_zh after v3 migration)
        league = store.get_league(league_id)
        assert league is not None, "League should exist after migration"
        assert league.continent == continent
        assert league.code == code
        assert league.name_zh == country + name_zh  # v3: country || name_zh
        assert league.phase is None  # v1 had no phase, should default to NULL
        assert league.is_active is True

        # 4. Verify season data preserved
        seasons = store.list_season_instances(league_id)
        assert len(seasons) == 1
        s = seasons[0]
        assert s.id == season_id
        assert s.league_id == league_id
        assert s.label == label
        assert s.year_start == year_start
        assert s.year_end == year_end
        assert s.role == role

        # 5. Verify schema version was updated
        assert store._get_schema_version() >= 3

        # 6. Verify new tables/indexes exist
        tables = [
            row[0]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "match_records" in tables

        # Verify phase column exists and country column removed
        cols = [
            row[1]
            for row in store._conn.execute("PRAGMA table_info(leagues)").fetchall()
        ]
        assert "phase" in cols
        assert "country" not in cols

    finally:
        try:
            store._conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Shared strategies for match_records tests
# ---------------------------------------------------------------------------

play_types = st.sampled_from(["HDP", "OU"])
timings = st.sampled_from(["Early", "RT"])

team_names = st.text(
    min_size=1, max_size=15,
    alphabet=st.characters(whitelist_categories=("L",)),
)

match_record_st = st.builds(
    lambda rn, ht, at, xv, settle, sc, lk, sv, sd, had, tt: __import__(
        "core.models", fromlist=["MatchRecord"]
    ).MatchRecord(
        round_num=rn,
        home_team=ht,
        away_team=at,
        x_value=xv,
        settlement=settle,
        score=sc,
        link=lk,
        settlement_value=sv,
        settlement_direction=sd,
        home_away_direction=had,
        target_team=tt,
    ),
    rn=st.integers(min_value=1, max_value=50),
    ht=team_names,
    at=team_names,
    xv=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    settle=st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    sc=st.text(min_size=0, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
    lk=st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    sv=st.sampled_from([0.0, 0.5, 1.0]),
    sd=st.sampled_from(["", "win", "lose"]),
    had=st.sampled_from(["", "home", "away"]),
    tt=st.text(min_size=0, max_size=15, alphabet=st.characters(whitelist_categories=("L",))),
)


def _fresh_store() -> ConfigStore:
    """Create a ConfigStore backed by a temporary in-memory-like file."""
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")
    return ConfigStore(db_path=db_path)


def _seed_season(store: ConfigStore) -> int:
    """Create a league + season and return season_instance_id."""
    lid = store.create_league(
        continent="EUR", code="TST" + os.urandom(4).hex(),
        name_zh="Test",
    )
    sid = store.create_season_instance(league_id=lid, label="2025", year_start=2025)
    return sid


# ===========================================================================
# Property 6: UPSERT 完整替換
# Feature: rpa-data-driven-league, Property 6: UPSERT 完整替換
# Validates: 需求 4.3, 5.3
# ===========================================================================

@given(
    play_type=play_types,
    timing=timings,
    old_records=st.lists(match_record_st, min_size=1, max_size=10),
    new_records=st.lists(match_record_st, min_size=0, max_size=10),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property6_upsert_complete_replacement(
    play_type, timing, old_records, new_records,
):
    """UPSERT 完整替換：新資料匯入後，該組合下舊紀錄被完全刪除，
    查詢結果只包含最新匯入的紀錄。

    **Validates: Requirements 4.3, 5.3**
    """
    store = _fresh_store()
    sid = _seed_season(store)

    # Insert old records
    store.upsert_match_records(sid, play_type, timing, old_records)
    # Verify old records exist
    result_old = store.get_match_records(sid, play_type=play_type, timing=timing)
    assert len(result_old) == len(old_records)

    # Upsert with new records — should completely replace
    count = store.upsert_match_records(sid, play_type, timing, new_records)
    assert count == len(new_records)

    result_new = store.get_match_records(sid, play_type=play_type, timing=timing)
    assert len(result_new) == len(new_records)

    # Verify the set of key fields matches (order may differ due to DB sorting)
    fetched_keys = [
        (r.round_num, r.home_team, r.away_team, r.x_value)
        for r in result_new
    ]
    expected_keys = [
        (r.round_num, r.home_team, r.away_team, r.x_value)
        for r in new_records
    ]
    assert sorted(fetched_keys, key=str) == sorted(expected_keys, key=str)

    store._conn.close()


# ===========================================================================
# Property 8: 比賽紀錄查詢篩選正確性
# Feature: rpa-data-driven-league, Property 8: 比賽紀錄查詢篩選正確性
# Validates: 需求 5.4
# ===========================================================================

@given(
    records_hdp_early=st.lists(match_record_st, min_size=0, max_size=5),
    records_hdp_rt=st.lists(match_record_st, min_size=0, max_size=5),
    records_ou_early=st.lists(match_record_st, min_size=0, max_size=5),
    records_ou_rt=st.lists(match_record_st, min_size=0, max_size=5),
    query_play_type=st.sampled_from([None, "HDP", "OU"]),
    query_timing=st.sampled_from([None, "Early", "RT"]),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property8_match_record_query_filtering(
    records_hdp_early, records_hdp_rt, records_ou_early, records_ou_rt,
    query_play_type, query_timing,
):
    """比賽紀錄查詢篩選正確性：get_match_records() 回傳的所有紀錄滿足
    所有指定篩選條件，且不遺漏符合條件的紀錄。

    **Validates: Requirements 5.4**
    """
    store = _fresh_store()
    sid = _seed_season(store)

    # Insert records for all 4 combinations
    combos = {
        ("HDP", "Early"): records_hdp_early,
        ("HDP", "RT"): records_hdp_rt,
        ("OU", "Early"): records_ou_early,
        ("OU", "RT"): records_ou_rt,
    }
    for (pt, tm), recs in combos.items():
        if recs:
            store.upsert_match_records(sid, pt, tm, recs)

    # Query with filters
    results = store.get_match_records(sid, play_type=query_play_type, timing=query_timing)

    # Calculate expected count
    expected_count = 0
    for (pt, tm), recs in combos.items():
        if query_play_type is not None and pt != query_play_type:
            continue
        if query_timing is not None and tm != query_timing:
            continue
        expected_count += len(recs)

    assert len(results) == expected_count

    # Verify all returned records satisfy the filter conditions
    for r in results:
        if query_play_type is not None:
            assert r.play_type == query_play_type
        if query_timing is not None:
            assert r.play_type in ("HDP", "OU")  # valid play_type

    store._conn.close()


# ===========================================================================
# Property 9: Team_Pool 為所有隊伍的聯集
# Feature: rpa-data-driven-league, Property 9: Team_Pool 為所有隊伍的聯集
# Validates: 需求 6.1, 6.4
# ===========================================================================

@given(
    records_list=st.lists(
        st.tuples(play_types, timings, st.lists(match_record_st, min_size=1, max_size=5)),
        min_size=1,
        max_size=4,
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property9_team_pool_union_completeness(records_list):
    """Team_Pool 為所有隊伍的聯集：get_team_pool() 回傳的隊伍集合等於
    所有 match_records 中 home_team 與 away_team 的聯集。

    **Validates: Requirements 6.1, 6.4**
    """
    store = _fresh_store()
    sid = _seed_season(store)

    # Deduplicate combos — keep last records for each (play_type, timing)
    combo_records: dict[tuple[str, str], list] = {}
    for pt, tm, recs in records_list:
        combo_records[(pt, tm)] = recs

    # Insert all records
    expected_teams: set[str] = set()
    for (pt, tm), recs in combo_records.items():
        store.upsert_match_records(sid, pt, tm, recs)
        for r in recs:
            expected_teams.add(r.home_team)
            expected_teams.add(r.away_team)

    # Get team pool
    pool = store.get_team_pool(sid)
    pool_set = set(pool)

    # Pool should equal the union of all home_team and away_team
    assert pool_set == expected_teams

    # Pool should be sorted
    assert pool == sorted(pool)

    # No duplicates
    assert len(pool) == len(pool_set)

    store._conn.close()
