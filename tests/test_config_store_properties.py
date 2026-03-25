"""ConfigStore 屬性測試：使用 Hypothesis 驗證 CRUD、篩選、級聯刪除、round-trip 等正確性屬性。"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume, HealthCheck
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

url_types = st.sampled_from(["League", "SubLeague"])

play_types = st.sampled_from(["HDP", "OU"])
timings = st.sampled_from(["Early", "RT"])

file_paths_st = st.text(
    min_size=5, max_size=100,
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
)

json_values = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
    st.text(min_size=0, max_size=50),
    st.lists(st.integers(min_value=-100, max_value=100), max_size=10),
    st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        max_size=10,
    ),
)

# Strategy for name_zh (non-empty text)
names_st = st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",)))

# Strategy for league_url_id (digits as string)
url_id_st = st.integers(min_value=1, max_value=999999).map(str)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_store() -> ConfigStore:
    """Create a fresh ConfigStore backed by a temporary file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # ConfigStore will create it
    return ConfigStore(db_path=path)


# ===========================================================================
# 1.4.1 — 屬性 3：聯賽 CRUD 與 RPA 欄位完整性
# Feature: football-quant-v2-refactor, Property 3: 聯賽 CRUD 與 RPA 欄位完整性
# Validates: Requirements 2.3, 2.4
# ===========================================================================


@given(
    continent=continents,
    code=league_codes,
    name_zh=names_st,
    url_id=url_id_st,
    url_type=url_types,
    new_name=names_st,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property3_league_crud_rpa_fields(
    continent, code, name_zh, url_id, url_type, new_name,
):
    """建立→讀取→編輯→讀取→停用→active_only 查詢 的完整 round-trip。"""
    store = _make_store()
    try:
        # --- Create ---
        lid = store.create_league(
            continent=continent,
            code=code,
            name_zh=name_zh,
            league_url_id=url_id,
            league_url_type=url_type,
        )

        # --- Read after create ---
        league = store.get_league(lid)
        assert league is not None
        assert league.continent == continent
        assert league.code == code
        assert league.name_zh == name_zh
        assert league.league_url_id == url_id
        assert league.league_url_type == url_type
        assert league.is_active is True

        # --- Update ---
        store.update_league(lid, name_zh=new_name, league_url_type="SubLeague")
        league = store.get_league(lid)
        assert league.name_zh == new_name
        assert league.league_url_type == "SubLeague"

        # --- Deactivate ---
        store.update_league(lid, is_active=0)
        active_leagues = store.list_leagues(active_only=True)
        assert all(l.id != lid for l in active_leagues)

        # Still visible when active_only=False
        all_leagues = store.list_leagues(active_only=False)
        assert any(l.id == lid for l in all_leagues)
    finally:
        store._conn.close()


# ===========================================================================
# 1.4.2 — 屬性 4：洲別篩選正確性
# Feature: football-quant-v2-refactor, Property 4: 洲別篩選正確性
# Validates: Requirements 2.5
# ===========================================================================


@given(
    data=st.data(),
    target_continent=continents,
)
@settings(max_examples=100, deadline=None)
def test_property4_continent_filter(data, target_continent):
    """篩選結果中每筆聯賽的洲別都等於指定洲別，且數量正確。"""
    store = _make_store()
    try:
        # Generate a small set of leagues across continents
        all_continents = ["AFR", "AME", "ASI", "EUR"]
        expected_count = 0
        for i, cont in enumerate(all_continents):
            n = data.draw(st.integers(min_value=0, max_value=3), label=f"count_{cont}")
            for j in range(n):
                code = f"{cont}{i}_{j}"
                store.create_league(cont, code, f"Name_{i}_{j}")
                if cont == target_continent:
                    expected_count += 1

        filtered = store.list_leagues(continent=target_continent, active_only=False)

        # Every result must match the target continent
        for league in filtered:
            assert league.continent == target_continent

        # Count must equal the number we inserted for that continent
        assert len(filtered) == expected_count
    finally:
        store._conn.close()


# ===========================================================================
# 1.4.3 — 屬性 5：級聯刪除完整性
# Feature: football-quant-v2-refactor, Property 5: 級聯刪除完整性
# Validates: Requirements 2.6
# ===========================================================================


@given(
    continent=continents,
    code=league_codes,
    n_seasons=st.integers(min_value=1, max_value=3),
    n_groups=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=100, deadline=None)
def test_property5_cascade_delete(continent, code, n_seasons, n_groups):
    """刪除聯賽後，所有關聯的賽季、分組、隊伍、計算結果都應被同時刪除。"""
    store = _make_store()
    try:
        lid = store.create_league(continent, code, "Name")

        season_ids = []
        group_ids = []
        for s in range(n_seasons):
            sid = store.create_season_instance(lid, f"Season_{s}", 2025 + s)
            season_ids.append(sid)
            for g in range(n_groups):
                gid = store.create_team_group(sid, f"Group_{s}_{g}")
                store.set_teams(gid, [f"Team_{s}_{g}_A", f"Team_{s}_{g}_B"])
                group_ids.append(gid)
            # Add file paths
            store.set_file_path(sid, "HDP", "Early", f"/data/s{s}_hdp_early.xlsx")

        # Create ETL run + computation/decision results
        run_id = store.create_etl_run({"leagues": [lid]})
        for sid in season_ids:
            groups = store.list_team_groups(sid)
            for tg in groups:
                store.save_computation_result(run_id, {
                    "league_id": lid,
                    "season_instance_id": sid,
                    "team_group_id": tg.id,
                    "play_type": "HDP",
                    "timing": "Early",
                    "zone_data": [{"zone_id": 1}],
                    "round_block_data": [],
                    "season_total_win": 1.0,
                    "season_total_lose": 0.5,
                })
                store.save_decision_result(run_id, {
                    "league_id": lid,
                    "team_group_id": tg.id,
                    "play_type": "HDP",
                    "timing": "Early",
                    "five_zone_data": [],
                    "guard_levels": [],
                    "strength_levels": [],
                    "home_signals": [],
                    "away_signals": [],
                })

        # --- Delete league ---
        store.delete_league(lid)

        # Verify everything is gone
        assert store.get_league(lid) is None
        assert len(store.list_season_instances(lid)) == 0
        for sid in season_ids:
            assert len(store.list_team_groups(sid)) == 0
            assert len(store.get_file_paths(sid)) == 0
        for gid in group_ids:
            assert len(store.list_teams(gid)) == 0
        assert len(store.get_computation_results(run_id)) == 0
        assert len(store.get_decision_results(run_id)) == 0
    finally:
        store._conn.close()


# ===========================================================================
# 1.4.4 — 屬性 9：隊伍分組賽季綁定與 CRUD
# Feature: football-quant-v2-refactor, Property 9: 隊伍分組賽季綁定與 CRUD
# Validates: Requirements 4.1, 4.2, 4.3, 4.5
# ===========================================================================


@given(
    teams_a=st.lists(names_st, min_size=1, max_size=5, unique=True),
    teams_b=st.lists(names_st, min_size=1, max_size=5, unique=True),
    extra_group_name=names_st,
)
@settings(max_examples=100, deadline=None)
def test_property9_team_group_season_binding(teams_a, teams_b, extra_group_name):
    """修改一個賽季的 Team_Group 不應影響另一個賽季；新 Season 應自動產生預設分組。"""
    store = _make_store()
    try:
        lid = store.create_league("EUR", "ENG1", "England", "英超")

        # Create two seasons
        sid1 = store.create_season_instance(lid, "Season1", 2024)
        sid2 = store.create_season_instance(lid, "Season2", 2025)

        # Create default groups for both seasons (simulating default_team_groups)
        default_groups = store.get_param("default_team_groups") or ["Top", "Weak"]
        for dg in default_groups:
            store.create_team_group(sid1, dg)
            store.create_team_group(sid2, dg)

        # Verify default groups created
        groups1 = store.list_team_groups(sid1)
        groups2 = store.list_team_groups(sid2)
        assert len(groups1) == len(default_groups)
        assert len(groups2) == len(default_groups)

        # Set teams for season1's first group
        store.set_teams(groups1[0].id, teams_a)

        # Set teams for season2's first group
        store.set_teams(groups2[0].id, teams_b)

        # Verify season isolation: season1's teams unchanged after modifying season2
        s1_teams = store.list_teams(groups1[0].id)
        s2_teams = store.list_teams(groups2[0].id)
        assert s1_teams == teams_a
        assert s2_teams == teams_b

        # Add a custom group to season1 — should not appear in season2
        assume(extra_group_name not in default_groups)
        store.create_team_group(sid1, extra_group_name)
        groups1_after = store.list_team_groups(sid1)
        groups2_after = store.list_team_groups(sid2)
        assert len(groups1_after) == len(default_groups) + 1
        assert len(groups2_after) == len(default_groups)  # unchanged

        # Delete a group from season2 — should not affect season1
        store.delete_team_group(groups2[0].id)
        groups1_final = store.list_team_groups(sid1)
        groups2_final = store.list_team_groups(sid2)
        assert len(groups1_final) == len(default_groups) + 1  # unchanged
        assert len(groups2_final) == len(default_groups) - 1
    finally:
        store._conn.close()


# ===========================================================================
# 1.4.5 — 屬性 10：檔案路徑持久化 round-trip
# Feature: football-quant-v2-refactor, Property 10: 檔案路徑持久化 round-trip
# Validates: Requirements 5.3
# ===========================================================================


@given(
    hdp_early=file_paths_st,
    hdp_rt=file_paths_st,
    ou_early=file_paths_st,
    ou_rt=file_paths_st,
)
@settings(max_examples=100, deadline=None)
def test_property10_file_path_round_trip(hdp_early, hdp_rt, ou_early, ou_rt):
    """儲存 Four_File_Set 路徑後讀取應得到相同的路徑值。"""
    store = _make_store()
    try:
        lid = store.create_league("EUR", "ENG1", "England", "英超")
        sid = store.create_season_instance(lid, "2025", 2025)

        expected = {
            ("HDP", "Early"): hdp_early,
            ("HDP", "RT"): hdp_rt,
            ("OU", "Early"): ou_early,
            ("OU", "RT"): ou_rt,
        }

        for (pt, tm), fp in expected.items():
            store.set_file_path(sid, pt, tm, fp)

        # Read back
        fps = store.get_file_paths(sid)
        assert len(fps) == 4

        actual = {(f.play_type, f.timing): f.file_path for f in fps}
        for key, val in expected.items():
            assert actual[key] == val, f"Mismatch for {key}: {actual[key]} != {val}"
    finally:
        store._conn.close()


# ===========================================================================
# 1.4.6 — 屬性 25：參數持久化 round-trip
# Feature: football-quant-v2-refactor, Property 25: 參數持久化 round-trip
# Validates: Requirements 17.2, 17.3, 17.4
# ===========================================================================


@given(
    key=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    value=json_values,
)
@settings(max_examples=100, deadline=None)
def test_property25_param_round_trip(key, value):
    """儲存參數後讀取應得到等價的值；恢復預設值後應與 default_params.json 一致。"""
    store = _make_store()
    try:
        # --- Save and read back ---
        store.set_param(key, value)
        retrieved = store.get_param(key)

        if isinstance(value, float):
            assert abs(retrieved - value) < 1e-9, f"Float mismatch: {retrieved} != {value}"
        elif isinstance(value, list) and value and isinstance(value[0], float):
            assert len(retrieved) == len(value)
            for a, b in zip(retrieved, value):
                assert abs(a - b) < 1e-9
        else:
            assert retrieved == value, f"Mismatch: {retrieved} != {value}"

        # --- Reset to default ---
        store.reset_params_to_default()

        # Load expected defaults
        import pathlib
        defaults_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "default_params.json"
        with open(defaults_path, encoding="utf-8") as f:
            defaults = json.load(f)

        all_params = store.get_all_params()
        for dk, dv in defaults.items():
            assert dk in all_params, f"Default key '{dk}' missing after reset"
            if isinstance(dv, float):
                assert abs(all_params[dk] - dv) < 1e-9
            else:
                assert all_params[dk] == dv, f"Default mismatch for '{dk}': {all_params[dk]} != {dv}"
    finally:
        store._conn.close()


# ===========================================================================
# 1.4.7 — 屬性 26：ETL 結果持久化 round-trip
# Feature: football-quant-v2-refactor, Property 26: ETL 結果持久化 round-trip
# Validates: Requirements 19.1, 19.5
# ===========================================================================

# Strategies for ETL result data
_zone_data_st = st.lists(
    st.fixed_dictionaries({
        "zone_id": st.integers(min_value=1, max_value=9),
        "home_win": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        "home_lose": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        "away_win": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        "away_lose": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
    }),
    min_size=1,
    max_size=9,
)

_round_block_data_st = st.lists(
    st.fixed_dictionaries({
        "block_id": st.integers(min_value=1, max_value=6),
        "round_start": st.integers(min_value=1, max_value=60),
        "round_end": st.integers(min_value=1, max_value=60),
    }),
    min_size=0,
    max_size=6,
)

_five_zone_data_st = st.lists(
    st.fixed_dictionaries({
        "zone_id": st.integers(min_value=1, max_value=5),
        "prev_win": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        "prev_lose": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        "curr_win": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        "curr_lose": st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
    }),
    min_size=1,
    max_size=5,
)

_guard_levels_st = st.lists(st.integers(min_value=0, max_value=3), min_size=5, max_size=5)
_strength_levels_st = st.lists(st.integers(min_value=0, max_value=4), min_size=5, max_size=5)
_signals_st = st.lists(
    st.sampled_from(["", "A0.2", "A0.5", "A1", "A2", "B0.2", "B0.5", "B1", "B2"]),
    min_size=5,
    max_size=5,
)


@given(
    zone_data=_zone_data_st,
    round_block_data=_round_block_data_st,
    five_zone_data=_five_zone_data_st,
    guard_levels=_guard_levels_st,
    strength_levels=_strength_levels_st,
    home_signals=_signals_st,
    away_signals=_signals_st,
)
@settings(max_examples=100, deadline=None)
def test_property26_etl_result_round_trip(
    zone_data, round_block_data, five_zone_data,
    guard_levels, strength_levels, home_signals, away_signals,
):
    """ETL 計算結果 JSON 序列化→SQLite→讀取→反序列化 應得到等價的資料結構。"""
    store = _make_store()
    try:
        lid = store.create_league("EUR", "ENG1", "England", "英超")
        sid = store.create_season_instance(lid, "2025", 2025)
        gid = store.create_team_group(sid, "Top")

        run_id = store.create_etl_run({"leagues": [lid]})

        # --- Save computation result ---
        store.save_computation_result(run_id, {
            "league_id": lid,
            "season_instance_id": sid,
            "team_group_id": gid,
            "play_type": "HDP",
            "timing": "Early",
            "zone_data": zone_data,
            "round_block_data": round_block_data,
            "season_total_win": 0,
            "season_total_lose": 0,
        })

        # --- Save decision result ---
        store.save_decision_result(run_id, {
            "league_id": lid,
            "team_group_id": gid,
            "play_type": "HDP",
            "timing": "Early",
            "five_zone_data": five_zone_data,
            "guard_levels": guard_levels,
            "strength_levels": strength_levels,
            "home_signals": home_signals,
            "away_signals": away_signals,
        })

        # --- Read back computation result ---
        comp = store.get_computation_results(run_id)
        assert len(comp) == 1
        _assert_json_equal(comp[0]["zone_data"], zone_data)
        _assert_json_equal(comp[0]["round_block_data"], round_block_data)

        # --- Read back decision result ---
        dec = store.get_decision_results(run_id)
        assert len(dec) == 1
        _assert_json_equal(dec[0]["five_zone_data"], five_zone_data)
        assert dec[0]["guard_levels"] == guard_levels
        assert dec[0]["strength_levels"] == strength_levels
        assert dec[0]["home_signals"] == home_signals
        assert dec[0]["away_signals"] == away_signals
    finally:
        store._conn.close()


def _assert_json_equal(actual, expected):
    """Compare two JSON-serializable structures, tolerating float precision."""
    if isinstance(expected, list):
        assert isinstance(actual, list), f"Expected list, got {type(actual)}"
        assert len(actual) == len(expected), f"Length mismatch: {len(actual)} != {len(expected)}"
        for a, e in zip(actual, expected):
            _assert_json_equal(a, e)
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), f"Expected dict, got {type(actual)}"
        assert set(actual.keys()) == set(expected.keys()), (
            f"Key mismatch: {set(actual.keys())} != {set(expected.keys())}"
        )
        for k in expected:
            _assert_json_equal(actual[k], expected[k])
    elif isinstance(expected, float):
        assert isinstance(actual, (int, float)), f"Expected number, got {type(actual)}"
        assert abs(float(actual) - expected) < 1e-9, f"Float mismatch: {actual} != {expected}"
    else:
        assert actual == expected, f"Value mismatch: {actual} != {expected}"
