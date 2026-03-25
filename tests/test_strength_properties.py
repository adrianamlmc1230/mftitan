"""StrengthUpgrader 屬性測試。"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from core.strength import StrengthUpgrader


# Feature: football-quant-v2-refactor, Property 21: 強度升級正確性
@given(
    guard=st.integers(min_value=0, max_value=3),
    pw=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    pl=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    m=st.floats(min_value=1.01, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_property21_strength_upgrade_correctness(guard, pw, pl, m):
    """強度升級正確性：
    (a) g != 2 → strength == g
    (b) g == 2 且 MAX(pw,pl)/MIN(pw,pl) >= m → strength == 4
    (c) g == 2 且 MAX(pw,pl)/MIN(pw,pl) < m → strength == 2
    """
    upgrader = StrengthUpgrader()
    result = upgrader.upgrade(guard, pw, pl, m)

    if guard != 2:
        assert result == guard, f"guard={guard} 時 strength 應等於 guard，得到 {result}"
    else:
        max_val = max(pw, pl)
        min_val = min(pw, pl)
        if min_val == 0.0:
            if max_val > 0.0:
                assert result == 4, f"min=0, max>0 時應升級為 4，得到 {result}"
            else:
                assert result == 2, f"min=0, max=0 時應保持 2，得到 {result}"
        else:
            ratio = max_val / min_val
            if ratio >= m:
                assert result == 4, f"ratio={ratio} >= m={m} 時應升級為 4，得到 {result}"
            else:
                assert result == 2, f"ratio={ratio} < m={m} 時應保持 2，得到 {result}"
