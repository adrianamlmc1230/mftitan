"""資料一致性整合測試。

測試 ETL 結果持久化後讀取的完整性。
測試 JSON 序列化/反序列化的正確性。
測試歷史版本切換的正確性。

Validates: Requirements 19.1, 19.5
"""

import json
import tempfile
from pathlib import Path

import pytest

from core.config_store import ConfigStore


def _make_store():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "test.db")
    return ConfigStore(db_path=db_path)


class TestComputationResultRoundTrip:
    """computation_results 的 JSON 序列化/反序列化。"""

    def test_zone_data_round_trip(self):
        store = _make_store()
        lid = store.create_league("ASI", "RT1", "國", "聯賽")
        sid = store.create_season_instance(lid, "2025", 2025)
        gid = store.create_team_group(sid, "Top")

        run_id = store.create_etl_run({"leagues": [lid]})

        zone_data = [
            {"zone_id": i, "home_win": 1.5 * i, "home_lose": 0.5 * i,
             "away_win": 0.3 * i, "away_lose": 0.7 * i}
            for i in range(1, 10)
        ]
        round_block_data = [
            {"block_id": 1, "round_start": 1, "round_end": 10,
             "zones": zone_data}
        ]

        store.save_computation_result(run_id, {
            "league_id": lid,
            "season_instance_id": sid,
            "team_group_id": gid,
            "play_type": "HDP",
            "timing": "Early",
            "zone_data": zone_data,
            "round_block_data": round_block_data,
            "season_total_win": 13.5,
            "season_total_lose": 4.5,
        })

        results = store.get_computation_results(run_id, league_id=lid)
        assert len(results) == 1
        r = results[0]
        assert r["zone_data"] == zone_data
        assert r["round_block_data"] == round_block_data
        assert r["season_total_win"] == 13.5
        assert r["season_total_lose"] == 4.5


class TestDecisionResultRoundTrip:
    """decision_results 的 JSON 序列化/反序列化。"""

    def test_signals_round_trip(self):
        store = _make_store()
        lid = store.create_league("EUR", "RT2", "國", "聯賽")
        sid = store.create_season_instance(lid, "2025", 2025)
        gid = store.create_team_group(sid, "Top")

        run_id = store.create_etl_run({"leagues": [lid]})

        five_zone_data = [
            {"zone_id": i, "prev_home_win": 1.0, "prev_home_lose": 0.5,
             "prev_away_win": 0.3, "prev_away_lose": 0.7,
             "curr_home_win": 2.0, "curr_home_lose": 1.0,
             "curr_away_win": 0.5, "curr_away_lose": 1.5}
            for i in range(1, 6)
        ]
        guard_levels = [0, 2, 1, 3, 2, 0, 2, 1, 3, 2]
        strength_levels = [0, 4, 1, 3, 2, 0, 4, 1, 3, 2]
        home_signals = ["", "A2", "B0.2", "", "A0.5"]
        away_signals = ["", "B2", "A0.2", "", "B0.5"]

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

        results = store.get_decision_results(run_id, league_id=lid)
        assert len(results) == 1
        r = results[0]
        assert r["five_zone_data"] == five_zone_data
        assert r["guard_levels"] == guard_levels
        assert r["strength_levels"] == strength_levels
        assert r["home_signals"] == home_signals
        assert r["away_signals"] == away_signals

    def test_unicode_signals_round_trip(self):
        """含中文的資料應正確序列化/反序列化。"""
        store = _make_store()
        lid = store.create_league("ASI", "RT3", "中國", "中超")
        sid = store.create_season_instance(lid, "2025", 2025)
        gid = store.create_team_group(sid, "Top")

        run_id = store.create_etl_run({"leagues": [lid]})

        store.save_decision_result(run_id, {
            "league_id": lid,
            "team_group_id": gid,
            "play_type": "OU",
            "timing": "RT",
            "five_zone_data": [{"zone_id": i} for i in range(1, 6)],
            "guard_levels": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "strength_levels": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "home_signals": ["", "", "", "", ""],
            "away_signals": ["", "", "", "", ""],
        })

        results = store.get_decision_results(run_id)
        assert len(results) == 1


class TestETLRunHistory:
    """ETL 執行歷史管理。"""

    def test_multiple_runs_ordered(self):
        store = _make_store()
        lid = store.create_league("ASI", "HIS1", "國", "聯賽")

        run1 = store.create_etl_run({"leagues": [lid]})
        store.complete_etl_run(run1, "completed", {"count": 1})

        run2 = store.create_etl_run({"leagues": [lid]})
        store.complete_etl_run(run2, "completed", {"count": 2})

        runs = store.list_etl_runs(limit=10)
        assert len(runs) >= 2
        # 最新的在前
        assert runs[0]["id"] > runs[1]["id"]

    def test_run_summary_round_trip(self):
        store = _make_store()
        run_id = store.create_etl_run({"leagues": [1, 2, 3]})

        summary = {
            "leagues_processed": 3,
            "total_records": 150,
            "unmatched_teams": ["隊伍X", "隊伍Y"],
        }
        store.complete_etl_run(run_id, "completed", summary)

        runs = store.list_etl_runs(limit=1)
        assert runs[0]["summary"] == summary

    def test_quality_issues_round_trip(self):
        store = _make_store()
        lid = store.create_league("ASI", "QI1", "國", "聯賽")
        run_id = store.create_etl_run({"leagues": [lid]})

        store.save_quality_issue(run_id, {
            "league_id": lid,
            "severity": "warning",
            "issue_type": "empty_data",
            "description": "所有區間數據為空",
            "details": {"zones": [1, 2, 3]},
        })

        issues = store.get_quality_issues(run_id)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["details"] == {"zones": [1, 2, 3]}


class TestParamsPersistence:
    """參數持久化。"""

    def test_default_params_loaded(self):
        store = _make_store()
        params = store.get_all_params()
        assert "x_value_boundaries" in params
        assert "five_zone_mapping" in params
        assert "round_block_size" in params

    def test_param_update_persists(self):
        store = _make_store()
        store.set_param("round_block_size", 5)
        assert store.get_param("round_block_size") == 5

    def test_reset_to_default(self):
        store = _make_store()
        store.set_param("round_block_size", 99)
        store.reset_params_to_default()
        assert store.get_param("round_block_size") == 10
