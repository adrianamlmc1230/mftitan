"""SettlementCalculator 屬性測試：結算計算與方向判定正確性。"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.models import MatchRecord
from core.settlement import SettlementCalculator


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Valid HDP settlement texts
valid_hdp = st.sampled_from([
    "主贏", "主贏半", "主輸半", "主輸",
    "客贏", "客贏半", "客輸半", "客輸",
])

# Valid OU settlement texts
valid_ou = st.sampled_from([
    "大贏", "大贏半", "大輸半", "大輸",
    "小贏", "小贏半", "小輸半", "小輸",
])

# Combined: (play_type, settlement_text)
valid_settlement = st.one_of(
    valid_hdp.map(lambda s: ("HDP", s)),
    valid_ou.map(lambda s: ("OU", s)),
)


# ---------------------------------------------------------------------------
# Property 13: 結算計算與方向判定正確性
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 13: 結算計算與方向判定正確性
# Validates: Requirements 7.2, 8.1, 8.2, 8.3
@given(data=valid_settlement)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property13_settlement_calculation_correctness(data) -> None:
    """對任意有效的模擬結果文字和玩法類型，結算計算應滿足：
    (a) 包含「半」→ value=0.5，不包含「半」→ value=1.0
    (b) 包含「贏」→ direction=win，包含「輸」→ direction=lose
    (c) HDP 以「主」開頭→ home_direction，以「客」開頭→ away_direction；
        OU 以「大」開頭→ home_direction，以「小」開頭→ away_direction
    (d) home → target_team == home_team，away → target_team == away_team
    """
    play_type, settlement_text = data

    rec = MatchRecord(
        round_num=1,
        home_team="主隊甲",
        away_team="客隊乙",
        x_value=0.05,
        settlement=settlement_text,
        play_type=play_type,
    )

    calc = SettlementCalculator()
    calc.calculate([rec])

    # (a) value: 包含「半」→ 0.5，否則 → 1.0
    if "半" in settlement_text:
        assert rec.settlement_value == 0.5, (
            f"包含「半」但 value={rec.settlement_value}，settlement='{settlement_text}'"
        )
    else:
        assert rec.settlement_value == 1.0, (
            f"不包含「半」但 value={rec.settlement_value}，settlement='{settlement_text}'"
        )

    # (b) direction: 包含「贏」→ win，包含「輸」→ lose
    if "贏" in settlement_text:
        assert rec.settlement_direction == "win", (
            f"包含「贏」但 direction='{rec.settlement_direction}'"
        )
    elif "輸" in settlement_text:
        assert rec.settlement_direction == "lose", (
            f"包含「輸」但 direction='{rec.settlement_direction}'"
        )

    # (c) home_away_direction based on prefix and play_type
    prefix = settlement_text[0]
    if play_type == "HDP":
        if prefix == "主":
            assert rec.home_away_direction == "home", (
                f"HDP 以「主」開頭但 direction='{rec.home_away_direction}'"
            )
        elif prefix == "客":
            assert rec.home_away_direction == "away", (
                f"HDP 以「客」開頭但 direction='{rec.home_away_direction}'"
            )
    elif play_type == "OU":
        if prefix == "大":
            assert rec.home_away_direction == "home", (
                f"OU 以「大」開頭但 direction='{rec.home_away_direction}'"
            )
        elif prefix == "小":
            assert rec.home_away_direction == "away", (
                f"OU 以「小」開頭但 direction='{rec.home_away_direction}'"
            )

    # (d) target_team based on home_away_direction
    if rec.home_away_direction == "home":
        assert rec.target_team == "主隊甲", (
            f"home direction 但 target_team='{rec.target_team}'"
        )
    elif rec.home_away_direction == "away":
        assert rec.target_team == "客隊乙", (
            f"away direction 但 target_team='{rec.target_team}'"
        )
