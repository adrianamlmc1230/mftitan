"""RoundBlockAggregator 屬性測試。"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.models import MatchRecord
from core.round_aggregator import RoundBlockAggregator


# --- Hypothesis 策略（輕量化） ---

def _rec(round_num, value, direction, ha_dir):
    return MatchRecord(
        round_num=round_num, home_team="A", away_team="B",
        x_value=0.0, settlement="主贏", play_type="HDP",
        settlement_value=value, settlement_direction=direction,
        home_away_direction=ha_dir, target_team="A",
    )


@st.composite
def classified_records(draw):
    """生成 {zone_id: [MatchRecord]} 字典，輕量化版本。"""
    result = {}
    num_zones = draw(st.integers(min_value=0, max_value=9))
    zone_ids = draw(st.lists(
        st.integers(min_value=1, max_value=9),
        min_size=num_zones, max_size=num_zones, unique=True,
    ))
    for zid in zone_ids:
        num_recs = draw(st.integers(min_value=0, max_value=8))
        recs = []
        for _ in range(num_recs):
            recs.append(_rec(
                round_num=draw(st.integers(min_value=1, max_value=60)),
                value=draw(st.sampled_from([0.5, 1.0])),
                direction=draw(st.sampled_from(["win", "lose"])),
                ha_dir=draw(st.sampled_from(["home", "away"])),
            ))
        result[zid] = recs
    return result


# Feature: football-quant-v2-refactor, Property 17: 累加矩陣守恆
@given(classified=classified_records())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property17_accumulation_matrix_conservation(classified):
    """累加矩陣守恆：矩陣中所有儲存格的結算值總和應等於所有輸入紀錄的結算值總和。

    只計算 round_num 在 [1, block_size * max_blocks] 範圍內、且
    settlement_direction 為 win/lose 的紀錄。
    """
    agg = RoundBlockAggregator()
    block_size = 10
    max_blocks = 6
    max_round = block_size * max_blocks

    blocks = agg.aggregate(classified, block_size=block_size, max_blocks=max_blocks)

    # 計算矩陣中所有值的總和
    matrix_total = 0.0
    for block in blocks:
        for zs in block.zones:
            matrix_total += zs.home_win + zs.home_lose + zs.away_win + zs.away_lose

    # 計算輸入紀錄中有效的結算值總和
    input_total = 0.0
    for zone_id, recs in classified.items():
        if 1 <= zone_id <= 9:
            for rec in recs:
                if 1 <= rec.round_num <= max_round and rec.settlement_direction in ("win", "lose"):
                    input_total += rec.settlement_value

    assert abs(matrix_total - input_total) < 1e-9, (
        f"守恆失敗：矩陣總和={matrix_total}, 輸入總和={input_total}"
    )


# Feature: football-quant-v2-refactor, Property 18: 輪次區段匯總正確性
@given(classified=classified_records())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property18_round_block_aggregation_correctness(classified):
    """輪次區段匯總正確性：
    (a) 區段 N 應只包含輪次 [(N-1)*block_size+1, N*block_size] 的資料
    (b) 全季匯總應等於所有區段匯總之和
    """
    agg = RoundBlockAggregator()
    block_size = 10
    max_blocks = 6

    blocks = agg.aggregate(classified, block_size=block_size, max_blocks=max_blocks)

    # (a) 驗證每個區段的輪次範圍正確
    for block in blocks:
        expected_start = (block.block_id - 1) * block_size + 1
        expected_end = block.block_id * block_size
        assert block.round_start == expected_start
        assert block.round_end == expected_end

    # (a) 驗證每個區段只包含對應輪次範圍的資料
    for block in blocks:
        for zone_id in range(1, 10):
            zs = block.zones[zone_id - 1]
            # 手動計算該區段該區間的期望值
            expected_hw = 0.0
            expected_hl = 0.0
            expected_aw = 0.0
            expected_al = 0.0
            for rec in classified.get(zone_id, []):
                if block.round_start <= rec.round_num <= block.round_end:
                    if rec.settlement_direction == "win":
                        if rec.home_away_direction == "home":
                            expected_hw += rec.settlement_value
                        elif rec.home_away_direction == "away":
                            expected_aw += rec.settlement_value
                    elif rec.settlement_direction == "lose":
                        if rec.home_away_direction == "home":
                            expected_hl += rec.settlement_value
                        elif rec.home_away_direction == "away":
                            expected_al += rec.settlement_value
            assert abs(zs.home_win - expected_hw) < 1e-9
            assert abs(zs.home_lose - expected_hl) < 1e-9
            assert abs(zs.away_win - expected_aw) < 1e-9
            assert abs(zs.away_lose - expected_al) < 1e-9

    # (b) 全季匯總 = 所有區段之和
    totals = agg.season_total(blocks)
    for zone_id in range(1, 10):
        sum_hw = sum(b.zones[zone_id - 1].home_win for b in blocks)
        sum_hl = sum(b.zones[zone_id - 1].home_lose for b in blocks)
        sum_aw = sum(b.zones[zone_id - 1].away_win for b in blocks)
        sum_al = sum(b.zones[zone_id - 1].away_lose for b in blocks)
        t = totals[zone_id - 1]
        assert abs(t.home_win - sum_hw) < 1e-9
        assert abs(t.home_lose - sum_hl) < 1e-9
        assert abs(t.away_win - sum_aw) < 1e-9
        assert abs(t.away_lose - sum_al) < 1e-9
