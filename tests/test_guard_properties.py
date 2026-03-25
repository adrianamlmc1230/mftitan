"""GuardLevelEvaluator 屬性測試。"""

from hypothesis import given, settings
from hypothesis import strategies as st

from core.guard import GuardLevelEvaluator


guard_inputs = st.tuples(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)


# Feature: football-quant-v2-refactor, Property 20: 護級判定完整性
@given(inputs=guard_inputs)
@settings(max_examples=200)
def test_property20_guard_level_completeness(inputs):
    """護級判定完整性：
    (a) pw == pl → 護級 0
    (b) pw != pl 且 cw == cl → 護級 1
    (c) pw != pl 且 cw != cl 且方向一致 → 護級 2
    (d) pw != pl 且 cw != cl 且方向相反 → 護級 3
    且結果必定為 0、1、2、3 之一。
    """
    pw, pl, cw, cl = inputs
    evaluator = GuardLevelEvaluator()
    result = evaluator.evaluate(pw, pl, cw, cl)

    # 結果必定為 0~3
    assert result in (0, 1, 2, 3)

    if pw == pl:
        assert result == 0, f"pw==pl 應為護級 0，得到 {result}"
    elif cw == cl:
        assert result == 1, f"pw!=pl 且 cw==cl 應為護級 1，得到 {result}"
    else:
        prev_dir = "win" if pw > pl else "lose"
        curr_dir = "win" if cw > cl else "lose"
        if prev_dir == curr_dir:
            assert result == 2, f"方向一致應為護級 2，得到 {result}"
        else:
            assert result == 3, f"方向相反應為護級 3，得到 {result}"
