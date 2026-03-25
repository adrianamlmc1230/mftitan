"""賽季生命週期管理屬性測試。

# Feature: football-quant-v2-refactor, Property 6: 賽季生命週期管理
# Feature: football-quant-v2-refactor, Property 7: 上季資料唯讀性
# Feature: football-quant-v2-refactor, Property 8: 本季資料全量替換
"""

from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.config_store import ConfigStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = ConfigStore(db_path=path)
    s.init_db()
    return s, path


def _close_store(store, path):
    store._conn.close()
    try:
        os.unlink(path)
    except PermissionError:
        pass


def _setup_league_with_season(store, teams_top=None, teams_weak=None):
    """建立一個聯賽 + current 賽季 + Top/Weak 分組。"""
    lid = store.create_league(
        continent="ASI", code="TST1", name_zh="測試聯賽",
    )
    sid = store.create_season_instance(
        league_id=lid, label="2025", year_start=2025,
    )
    store.set_season_role(sid, "current")

    top_gid = store.create_team_group(
        season_instance_id=sid, name="Top",
    )
    weak_gid = store.create_team_group(
        season_instance_id=sid, name="Weak",
    )

    if teams_top:
        store.set_teams(top_gid, teams_top)
    if teams_weak:
        store.set_teams(weak_gid, teams_weak)

    return lid, sid


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

team_names = st.lists(
    st.text(min_size=2, max_size=6,
            alphabet=st.characters(whitelist_categories=("L",))),
    min_size=1, max_size=6, unique=True,
)


# ---------------------------------------------------------------------------
# Property 6: 賽季生命週期管理
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 6: 賽季生命週期管理
# Validates: Requirements 3.5, 3.6

@given(top_teams=team_names, weak_teams=team_names)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property6_season_lifecycle(top_teams, weak_teams):
    """賽季轉換後：
    (a) 原本季 role 變為 previous
    (b) 新建 role=current 的 Season
    (c) 新本季的 TeamGroup 名稱和隊伍清單與原本季一致
    """
    store, db_path = _make_store()
    try:
        lid, old_sid = _setup_league_with_season(store, top_teams, weak_teams)

        # 執行賽季轉換
        new_sid, needs_confirm = store.rotate_season(
            lid, "2026", year_start=2026,
        )

        assert not needs_confirm
        assert new_sid > 0

        # (a) 原本季 role 變為 previous
        seasons = store.list_season_instances(lid)
        old_season = next(s for s in seasons if s.id == old_sid)
        assert old_season.role == "previous"

        # (b) 新建 role=current
        new_season = next(s for s in seasons if s.id == new_sid)
        assert new_season.role == "current"
        assert new_season.label == "2026"

        # (c) 新本季的 TeamGroup 與原本季一致
        old_groups = store.list_team_groups(old_sid)
        new_groups = store.list_team_groups(new_sid)

        old_names = {g.name for g in old_groups}
        new_names = {g.name for g in new_groups}
        assert old_names == new_names

        for og in old_groups:
            ng = next(g for g in new_groups if g.name == og.name)
            old_t = store.list_teams(og.id)
            new_t = store.list_teams(ng.id)
            assert old_t == new_t, (
                f"分組 {og.name} 隊伍不一致：原 {old_t}，新 {new_t}"
            )
    finally:
        _close_store(store, db_path)


# ---------------------------------------------------------------------------
# Property 7: 上季資料唯讀性
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 7: 上季資料唯讀性
# Validates: Requirements 3.3

@given(top_teams=team_names)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property7_previous_season_not_readonly(top_teams):
    """所有賽季（含 previous）皆可編輯，is_season_readonly 永遠回傳 False。"""
    store, db_path = _make_store()
    try:
        lid, old_sid = _setup_league_with_season(store, top_teams)

        # 轉換前：current 不是唯讀
        assert not store.is_season_readonly(old_sid)

        # 執行賽季轉換
        store.rotate_season(lid, "2026", year_start=2026)

        # 轉換後：原本季（現在是 previous）也不是唯讀
        assert not store.is_season_readonly(old_sid)
    finally:
        _close_store(store, db_path)


# ---------------------------------------------------------------------------
# Property 8: 本季資料全量替換
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 8: 本季資料全量替換
# Validates: Requirements 3.4, 5.5

@given(
    old_path=st.text(min_size=5, max_size=20,
                     alphabet=st.characters(whitelist_categories=("L", "N"))),
    new_path=st.text(min_size=5, max_size=20,
                     alphabet=st.characters(whitelist_categories=("L", "N"))),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property8_current_season_full_replace(old_path, new_path):
    """role=current 的 Season 重新指定檔案路徑後，舊資料被完全替換。"""
    store, db_path = _make_store()
    try:
        lid, sid = _setup_league_with_season(store)

        # 設定舊路徑
        store.set_file_path(sid, "HDP", "Early", old_path)
        fps = store.get_file_paths(sid)
        assert len(fps) == 1
        assert fps[0].file_path == old_path

        # 替換為新路徑
        store.set_file_path(sid, "HDP", "Early", new_path)
        fps = store.get_file_paths(sid)
        assert len(fps) == 1
        assert fps[0].file_path == new_path

        # 舊路徑不應存在
        all_paths = [fp.file_path for fp in fps]
        if old_path != new_path:
            assert old_path not in all_paths
    finally:
        _close_store(store, db_path)


# ---------------------------------------------------------------------------
# 額外：賽季轉換覆蓋確認
# ---------------------------------------------------------------------------

def test_rotate_season_overwrite_confirmation():
    """已有上季時，rotate_season 應要求確認。"""
    store, db_path = _make_store()
    try:
        lid, sid = _setup_league_with_season(store, ["TeamA"])

        # 第一次轉換
        new_sid1, confirm1 = store.rotate_season(lid, "2026", year_start=2026)
        assert not confirm1
        assert new_sid1 > 0

        # 第二次轉換：應要求確認
        new_sid2, confirm2 = store.rotate_season(lid, "2027", year_start=2027)
        assert confirm2
        assert new_sid2 == 0

        # 強制覆蓋
        new_sid3, confirm3 = store.rotate_season(
            lid, "2027", year_start=2027, force_overwrite=True,
        )
        assert not confirm3
        assert new_sid3 > 0

        # 驗證只有 current 和 previous 兩個賽季
        seasons = store.list_season_instances(lid)
        roles = [s.role for s in seasons]
        assert roles.count("current") == 1
        assert roles.count("previous") == 1
    finally:
        _close_store(store, db_path)
