"""RawDataPreprocessor 屬性測試：冪等性與清理統計正確性。"""

import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.preprocessor import RawDataPreprocessor


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Simplified Chinese chars that CHAR_MAP or OpenCC should convert
_SIMPLIFIED_CHARS = ['赢', '输', '赢半', '输半']

# Pre-defined team name bases (fast, no text generation overhead)
_TEAM_BASES = st.sampled_from([
    '甲隊', '乙隊', '丙隊', '丁隊', '戊隊',
    'TeamA', 'TeamB', 'TeamC', 'TeamD', 'TeamE',
])

# Generate a cell value that optionally contains simplified chars
_simplified_fragment = st.sampled_from(_SIMPLIFIED_CHARS)

# Pre-defined bracket texts (fast)
_bracket_text = st.sampled_from(['[中]', '[超]', '[甲]', '[乙]', '[U23]'])

# Generate digit suffix (1-9)
_digit_suffix = st.sampled_from(['1', '2', '3', '4', '5'])

# Settlement values (mix of simplified and traditional)
_SETTLEMENT_VALUES = [
    '主赢', '主赢半', '主输半', '主输',
    '客赢', '客赢半', '客输半', '客输',
    '主贏', '主贏半', '主輸半', '主輸',
    '不适用', '不适用(平)', '不適用', '不適用(平)',
]


@st.composite
def _team_name_cell(draw):
    """Compose a team name with optional bracket, simplified char, digit suffix."""
    name = draw(_TEAM_BASES)
    if draw(st.booleans()):
        name = draw(_simplified_fragment) + name
    if draw(st.booleans()):
        name = name + draw(_bracket_text)
    if draw(st.booleans()):
        name = name + draw(_digit_suffix)
    return name


@st.composite
def _dataframe_strategy(draw):
    """Generate a DataFrame with 1-15 rows matching RPA Excel format."""
    n_rows = draw(st.integers(min_value=1, max_value=15))
    rows = []
    for _ in range(n_rows):
        rows.append((
            draw(st.integers(min_value=1, max_value=60)),
            draw(_team_name_cell()),
            '1-0',
            draw(_team_name_cell()),
            draw(st.floats(min_value=-1.0, max_value=1.0,
                           allow_nan=False, allow_infinity=False)),
            draw(st.sampled_from(_SETTLEMENT_VALUES)),
        ))
    return pd.DataFrame(rows, columns=[0, 1, 2, 3, 4, 5])


# ---------------------------------------------------------------------------
# Property 11: Preprocessing idempotency
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 11: 前處理冪等性
# Validates: Requirements 6.1, 6.2, 6.3
@given(df=_dataframe_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property11_preprocessing_idempotency(df: pd.DataFrame) -> None:
    """對任意 RPA Excel DataFrame，執行前處理兩次的結果應與執行一次的結果完全相同。

    簡繁轉換、方括號移除、數字後綴移除都是冪等操作。
    """
    preprocessor = RawDataPreprocessor()

    # First pass
    result_once, _stats1 = preprocessor.process(df)

    # Second pass on the already-processed result
    result_twice, _stats2 = preprocessor.process(result_once)

    # The two results must be identical
    pd.testing.assert_frame_equal(result_once, result_twice)


# ---------------------------------------------------------------------------
# Property 12: Cleaning statistics correctness
# ---------------------------------------------------------------------------

# Strategy that generates DataFrames with *known* counts of each artifact type.
# We build rows where we explicitly control how many simplified chars, brackets,
# and digit suffixes appear.

@st.composite
def _dataframe_with_known_counts(draw):
    """Generate a DataFrame along with known lower-bound counts of artifacts."""
    n_rows = draw(st.integers(min_value=1, max_value=15))

    known_simplified = 0
    known_brackets = 0
    known_digits = 0

    rows = []
    for _ in range(n_rows):
        round_num = draw(st.integers(min_value=1, max_value=60))
        score = '1-0'
        x_val = draw(st.floats(min_value=-1.0, max_value=1.0,
                               allow_nan=False, allow_infinity=False))

        # Home team (column B, index 1)
        home = draw(_TEAM_BASES)
        home_has_simplified = draw(st.booleans())
        home_has_bracket = draw(st.booleans())
        home_has_digit = draw(st.booleans())

        if home_has_simplified:
            simp = draw(_simplified_fragment)
            home = simp + home
            known_simplified += 1
        if home_has_bracket:
            bracket = draw(_bracket_text)
            home = home + bracket
            known_brackets += 1
        if home_has_digit:
            digit = draw(_digit_suffix)
            home = home + digit
            known_digits += 1

        # Away team (column D, index 3)
        away = draw(_TEAM_BASES)
        away_has_simplified = draw(st.booleans())
        away_has_bracket = draw(st.booleans())
        away_has_digit = draw(st.booleans())

        if away_has_simplified:
            simp = draw(_simplified_fragment)
            away = simp + away
            known_simplified += 1
        if away_has_bracket:
            bracket = draw(_bracket_text)
            away = away + bracket
            known_brackets += 1
        if away_has_digit:
            digit = draw(_digit_suffix)
            away = away + digit
            known_digits += 1

        # Settlement (column F) - may also contain simplified chars
        settlement = draw(st.sampled_from(_SETTLEMENT_VALUES))

        rows.append((round_num, home, score, away, x_val, settlement))

    df = pd.DataFrame(rows, columns=[0, 1, 2, 3, 4, 5])
    return df, known_simplified, known_brackets, known_digits


# Feature: football-quant-v2-refactor, Property 12: 清理統計正確性
# Validates: Requirements 6.5
@given(data=_dataframe_with_known_counts())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property12_cleaning_statistics_correctness(data) -> None:
    """對任意包含 S 個已知簡體字、B 個方括號標記、D 個數字後綴的 DataFrame，
    前處理後的統計摘要中：
    - simplified_replaced 應 ≥ S
    - brackets_removed 應 ≥ B
    - digits_removed 應 ≥ D
    """
    df, known_simplified, known_brackets, known_digits = data

    preprocessor = RawDataPreprocessor()
    _result, stats = preprocessor.process(df)

    # Stats should be at least as large as our known counts.
    # They can be larger because:
    # - OpenCC may find additional simplified chars we didn't explicitly inject
    # - Settlement column may also contain simplified chars
    # - A single cell may match multiple CHAR_MAP entries
    assert stats['simplified_replaced'] >= known_simplified, (
        f"simplified_replaced={stats['simplified_replaced']} < known={known_simplified}"
    )
    assert stats['brackets_removed'] >= known_brackets, (
        f"brackets_removed={stats['brackets_removed']} < known={known_brackets}"
    )
    assert stats['digits_removed'] >= known_digits, (
        f"digits_removed={stats['digits_removed']} < known={known_digits}"
    )
