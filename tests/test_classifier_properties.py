"""XValueClassifier 屬性測試：X 值區間分類正確性。"""

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from core.models import MatchRecord
from core.classifier import XValueClassifier


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate valid X values
x_values = st.floats(
    min_value=-1.0, max_value=1.0,
    allow_nan=False, allow_infinity=False,
)

# Generate sorted boundary lists (ascending, unique)
boundaries_strategy = st.lists(
    st.floats(min_value=-1.0, max_value=1.0,
              allow_nan=False, allow_infinity=False),
    min_size=1, max_size=20,
    unique=True,
).map(sorted)


# ---------------------------------------------------------------------------
# Property 16: X 值區間分類正確性
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 16: X 值區間分類正確性
# Validates: Requirements 9.1, 9.3
@given(x_val=x_values, bounds=boundaries_strategy)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property16_x_value_zone_classification(x_val: float, bounds: list[float]) -> None:
    """對任意 X 值和排序的分界點列表，分類結果的 zone_id 應滿足：
    X 值落在該 zone_id 對應的區間範圍內。

    zone 1: X ≤ boundaries[0]
    zone N (last): X > boundaries[-1]
    zone k (middle): boundaries[k-2] < X ≤ boundaries[k-1]
    """
    # Skip degenerate cases where boundaries have duplicates after sorting
    # (floats can be very close but unique)
    for i in range(1, len(bounds)):
        assume(bounds[i] > bounds[i - 1])

    rec = MatchRecord(
        round_num=1,
        home_team="A",
        away_team="B",
        x_value=x_val,
        settlement="主贏",
        play_type="HDP",
    )

    classifier = XValueClassifier()
    result = classifier.classify([rec], boundaries=bounds)

    # Find which zone the record was placed in
    num_zones = len(bounds) + 1
    assigned_zone = None
    for zone_id in range(1, num_zones + 1):
        if rec in result.get(zone_id, []):
            assigned_zone = zone_id
            break

    assert assigned_zone is not None, (
        f"紀錄未被分配至任何區間，x_value={x_val}, boundaries={bounds}"
    )

    # Verify the zone assignment is correct
    if assigned_zone == 1:
        # zone 1: X ≤ boundaries[0]
        assert x_val <= bounds[0], (
            f"zone 1 但 x_value={x_val} > boundaries[0]={bounds[0]}"
        )
    elif assigned_zone == num_zones:
        # zone N (last): X > boundaries[-1]
        assert x_val > bounds[-1], (
            f"zone {num_zones} 但 x_value={x_val} <= boundaries[-1]={bounds[-1]}"
        )
    else:
        # zone k (middle): boundaries[k-2] < X ≤ boundaries[k-1]
        lower = bounds[assigned_zone - 2]
        upper = bounds[assigned_zone - 1]
        assert lower < x_val <= upper, (
            f"zone {assigned_zone} 但 x_value={x_val} 不在 ({lower}, {upper}] 範圍內"
        )
