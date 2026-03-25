"""RPA JSON 生成正確性屬性測試。

# Feature: football-quant-v2-refactor, Property 28: RPA JSON 生成正確性
# Validates: Requirements 21.2, 21.3, 21.4, 21.5
"""

from __future__ import annotations

import os
import re
import tempfile

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.config_store import ConfigStore
from utils.rpa_json_generator import RpaJsonGenerator


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


_URL_RE = re.compile(
    r"^https://zq\.titan007\.com/big/(League|SubLeague)/[\d\-]+/\d+\.html$"
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def leagues_with_url(draw):
    """Generate a list of leagues with URL info, inserted into a ConfigStore."""
    store, db_path = _make_store()

    num = draw(st.integers(min_value=1, max_value=5))
    league_ids = []

    for i in range(num):
        continent = draw(st.sampled_from(["ASI", "AFR", "AME", "EUR"]))
        code = f"TST{i + 1}"
        # 使用索引確保 name_zh 唯一
        name_zh = f"聯賽{i + 1}" + draw(st.text(min_size=1, max_size=2,
                                alphabet=st.characters(whitelist_categories=("L",))))
        url_id = str(draw(st.integers(min_value=1, max_value=9999)))
        url_type = draw(st.sampled_from(["League", "SubLeague"]))

        lid = store.create_league(
            continent=continent, code=code, name_zh=name_zh,
            league_url_id=url_id, league_url_type=url_type,
        )

        year_start = draw(st.integers(min_value=2020, max_value=2030))
        has_year_end = draw(st.booleans())
        year_end = year_start + 1 if has_year_end else None
        phase = draw(st.sampled_from([None, "第一階段", "第二階段"]))

        label = f"{year_start}-{year_end}" if year_end else str(year_start)
        sid = store.create_season_instance(
            league_id=lid, label=label,
            year_start=year_start, year_end=year_end, phase=phase,
        )
        store.set_season_role(sid, "current")

        league_ids.append(lid)

    leagues = store.list_leagues(active_only=True)
    return store, db_path, leagues


# ---------------------------------------------------------------------------
# Property 28: RPA JSON 生成正確性
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 28: RPA JSON 生成正確性
# Validates: Requirements 21.2, 21.3, 21.4, 21.5

@given(data=leagues_with_url())
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property28_rpa_json_correctness(data):
    """RPA JSON 生成正確性。

    驗證：
    (a) 每筆紀錄為長度 6 的陣列
    (b) URL 格式正確
    (c) Active 版每聯賽 2 筆（亞讓+總進球，時段=即+早）
    (d) Full 版每聯賽 4 筆（2 玩法 × 2 時段）
    """
    store, db_path, leagues = data
    try:
        gen = RpaJsonGenerator(store)

        # --- Active 版 ---
        active = gen.generate_active(leagues)

        # (a) 每筆長度 6
        for row in active:
            assert len(row) == 6, f"Active 紀錄長度應為 6，實際 {len(row)}: {row}"

        # (b) URL 格式
        for row in active:
            url = row[2]
            assert _URL_RE.match(url), f"URL 格式不正確：{url}"

        # (c) Active 版每聯賽 2 筆
        assert len(active) == len(leagues) * 2, (
            f"Active 版應有 {len(leagues) * 2} 筆，實際 {len(active)}"
        )

        # 驗證時段都是「即+早」
        for row in active:
            assert row[4] == "即+早", f"Active 版時段應為「即+早」，實際 {row[4]}"

        # 驗證玩法覆蓋
        play_types_per_league: dict[str, set[str]] = {}
        for row in active:
            key = row[0]  # 聯賽名
            play_types_per_league.setdefault(key, set()).add(row[5])
        for name, plays in play_types_per_league.items():
            assert plays == {"亞讓", "總進球"}, (
                f"聯賽 {name} Active 版玩法應為 {{亞讓, 總進球}}，實際 {plays}"
            )

        # --- Full 版 ---
        full = gen.generate_full(leagues)

        # (a) 每筆長度 6
        for row in full:
            assert len(row) == 6, f"Full 紀錄長度應為 6，實際 {len(row)}: {row}"

        # (b) URL 格式
        for row in full:
            url = row[2]
            assert _URL_RE.match(url), f"URL 格式不正確：{url}"

        # (d) Full 版每聯賽 4 筆
        assert len(full) == len(leagues) * 4, (
            f"Full 版應有 {len(leagues) * 4} 筆，實際 {len(full)}"
        )

        # 驗證時段和玩法的完整組合
        combos_per_league: dict[str, set[tuple[str, str]]] = {}
        for row in full:
            key = row[0]
            combos_per_league.setdefault(key, set()).add((row[4], row[5]))
        expected_combos = {
            ("早", "亞讓"), ("早", "總進球"),
            ("即+早", "亞讓"), ("即+早", "總進球"),
        }
        for name, combos in combos_per_league.items():
            assert combos == expected_combos, (
                f"聯賽 {name} Full 版組合應為 {expected_combos}，實際 {combos}"
            )

        # --- 額外驗證：年份字串出現在 URL 中 ---
        for row in active + full:
            year_str = row[1]
            url = row[2]
            assert year_str in url, (
                f"年份 {year_str} 應出現在 URL {url} 中"
            )

    finally:
        _close_store(store, db_path)
