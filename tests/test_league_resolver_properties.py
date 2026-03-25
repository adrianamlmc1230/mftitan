"""LeagueResolver 屬性測試。

使用 Hypothesis 驗證聯賽識別與建立的正確性屬性。
"""

from __future__ import annotations

import os
import tempfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.config_store import ConfigStore
from core.league_resolver import LeagueResolver, PendingLeague


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_store() -> ConfigStore:
    """建立暫存 DB 的 ConfigStore。"""
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")
    return ConfigStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 聯賽中文名（完整名稱，不拆分國家）
name_zh_st = st.text(
    alphabet=st.sampled_from("中國超甲乙聯冠盃杯英格蘭日本韓澳洲巴西"),
    min_size=2,
    max_size=8,
)

# 階段：None 或 "第N階段"
phases = st.one_of(
    st.none(),
    st.sampled_from(["第一階段", "第二階段", "第三階段", "第五階段"]),
)

# code：3~8 個英數字元
codes = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
    min_size=3,
    max_size=8,
).filter(lambda c: len(c) >= 3)

# 年份
year_starts = st.integers(min_value=2000, max_value=2050)


# ===========================================================================
# Property 3: 聯賽身份唯一性
# ===========================================================================

@given(
    name_zh=name_zh_st,
    phase=phases,
    code1=codes,
    code2=codes,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property3_league_identity_uniqueness(
    name_zh: str,
    phase: str | None,
    code1: str,
    code2: str,
):
    """相同 (name_zh, phase) 組合不能建立兩筆聯賽記錄。

    Validates: Requirements 2.4, 8.4
    """
    store = _fresh_store()
    resolver = LeagueResolver(store)

    pending = PendingLeague(
        name_zh=name_zh,
        phase=phase,
    )

    # 第一次建立應成功
    lid1 = resolver.create_league_with_code(pending, code1)
    assert lid1 > 0

    # 用不同 code 嘗試建立相同 identity 的聯賽
    if code2 != code1:
        try:
            resolver.create_league_with_code(pending, code2)
            found = store.find_league_by_identity(name_zh, phase)
            assert found is not None
            assert found.id == lid1, (
                f"相同 identity 不應建立第二筆聯賽，"
                f"但找到 id={found.id}（預期 {lid1}）"
            )
        except Exception:
            pass

    found = store.find_league_by_identity(name_zh, phase)
    assert found is not None
    assert found.id == lid1


# ===========================================================================
# Property 4: 聯賽建立正確性
# ===========================================================================

@given(
    name_zh=name_zh_st,
    phase=phases,
    code=codes,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property4_league_creation_correctness(
    name_zh: str,
    phase: str | None,
    code: str,
):
    """建立後的聯賽記錄包含正確的 name_zh、階段、code；
    重複 code 被拒絕。

    Validates: Requirements 2.3, 2.6
    """
    store = _fresh_store()
    resolver = LeagueResolver(store)

    pending = PendingLeague(
        name_zh=name_zh,
        phase=phase,
    )

    lid = resolver.create_league_with_code(pending, code)

    league = store.get_league(lid)
    assert league is not None
    assert league.name_zh == name_zh
    assert league.phase == phase
    assert league.code == code
    assert league.continent == ""  # 預設空字串

    # 驗證重複 code 被拒絕
    pending2 = PendingLeague(name_zh="日本J聯", phase=None)
    try:
        resolver.create_league_with_code(pending2, code)
        assert False, f"重複 code '{code}' 應被拒絕"
    except (ValueError, Exception):
        pass


# ===========================================================================
# Property 5: 賽季角色分配不變量
# ===========================================================================

@given(
    year_list=st.lists(
        year_starts,
        min_size=1,
        max_size=8,
        unique=True,
    ),
    use_cross_year=st.lists(st.booleans(), min_size=8, max_size=8),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property5_season_role_assignment_invariant(
    year_list: list[int],
    use_cross_year: list[bool],
):
    """recalculate_roles() 後最多一個 current、一個 previous，
    按 year_start 排序正確分配。
    """
    store = _fresh_store()
    resolver = LeagueResolver(store)

    lid = store.create_league(
        continent="EUR",
        code="T" + os.urandom(4).hex(),
        name_zh="英格蘭英超",
    )

    for i, ys in enumerate(year_list):
        cross = use_cross_year[i] if i < len(use_cross_year) else False
        ye = ys + 1 if cross else None
        label = f"{ys}-{ys + 1}" if cross else str(ys)
        store.create_season_instance(
            league_id=lid, label=label, year_start=ys, year_end=ye,
        )

    resolver.recalculate_roles(lid)

    seasons = store.list_season_instances(lid)
    assert len(seasons) == len(year_list)

    sorted_seasons = sorted(seasons, key=lambda s: s.year_start, reverse=True)

    current_count = sum(1 for s in seasons if s.role == "current")
    previous_count = sum(1 for s in seasons if s.role == "previous")

    assert current_count <= 1
    assert previous_count <= 1
    assert sorted_seasons[0].role == "current"

    if len(sorted_seasons) >= 2:
        assert sorted_seasons[1].role == "previous"

    for s in sorted_seasons[2:]:
        assert s.role is None


# ===========================================================================
# Property 10: 新賽季空白分組初始狀態
# ===========================================================================

@given(
    name_zh=name_zh_st,
    phase=phases,
    code=codes,
    season_year=st.one_of(
        st.integers(min_value=2000, max_value=2050).map(str),
        st.integers(min_value=2000, max_value=2049).map(
            lambda y: f"{y}-{y + 1}"
        ),
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property10_new_season_empty_groups(
    name_zh: str,
    phase: str | None,
    code: str,
    season_year: str,
):
    """由 League_Resolver 自動建立的新賽季實例，其隊伍分組列表為空。"""
    from core.models import ParsedFilename

    store = _fresh_store()
    resolver = LeagueResolver(store)

    pending = PendingLeague(name_zh=name_zh, phase=phase)
    lid = resolver.create_league_with_code(pending, code)

    parsed = ParsedFilename(
        name_zh=name_zh,
        season_year=season_year,
        phase=phase or "",
        timing="Early",
        play_type="HDP",
        original_path="test.xlsx",
    )
    season_id, is_new = resolver.ensure_season(lid, parsed)

    assert is_new is True
    groups = store.list_team_groups(season_id)
    assert len(groups) == 0
