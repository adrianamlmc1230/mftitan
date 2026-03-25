"""FiveZoneGrouper 屬性測試。"""

from hypothesis import given, settings
from hypothesis import strategies as st

from core.models import ZoneStats
from core.five_zone import FiveZoneGrouper, DEFAULT_MAPPING


# 生成 9 個 ZoneStats 的完整集合
@st.composite
def nine_zone_stats(draw):
    zones = []
    for i in range(1, 10):
        zones.append(ZoneStats(
            zone_id=i,
            home_win=draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)),
            home_lose=draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)),
            away_win=draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)),
            away_lose=draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)),
        ))
    return zones


# Feature: football-quant-v2-refactor, Property 19: 五大區間合併守恆
@given(zones=nine_zone_stats())
@settings(max_examples=100)
def test_property19_five_zone_merge_conservation(zones):
    """五大區間合併守恆：
    合併後 5 大區間的 home_win 總和應等於 9 區間的 home_win 總和，
    home_lose、away_win、away_lose 同理。
    每個大區間的值應等於其包含的小區間值之和。
    """
    grouper = FiveZoneGrouper()
    result = grouper.group(zones, mapping=DEFAULT_MAPPING)

    zone_map = {z.zone_id: z for z in zones}

    # 總量守恆
    total_hw_9 = sum(z.home_win for z in zones)
    total_hl_9 = sum(z.home_lose for z in zones)
    total_aw_9 = sum(z.away_win for z in zones)
    total_al_9 = sum(z.away_lose for z in zones)

    total_hw_5 = sum(r[0] for r in result)
    total_hl_5 = sum(r[1] for r in result)
    total_aw_5 = sum(r[2] for r in result)
    total_al_5 = sum(r[3] for r in result)

    assert abs(total_hw_9 - total_hw_5) < 1e-9
    assert abs(total_hl_9 - total_hl_5) < 1e-9
    assert abs(total_aw_9 - total_aw_5) < 1e-9
    assert abs(total_al_9 - total_al_5) < 1e-9

    # 每個大區間 = 其包含的小區間之和
    for i, group_ids in enumerate(DEFAULT_MAPPING):
        expected_hw = sum(zone_map[zid].home_win for zid in group_ids)
        expected_hl = sum(zone_map[zid].home_lose for zid in group_ids)
        expected_aw = sum(zone_map[zid].away_win for zid in group_ids)
        expected_al = sum(zone_map[zid].away_lose for zid in group_ids)
        assert abs(result[i][0] - expected_hw) < 1e-9
        assert abs(result[i][1] - expected_hl) < 1e-9
        assert abs(result[i][2] - expected_aw) < 1e-9
        assert abs(result[i][3] - expected_al) < 1e-9
