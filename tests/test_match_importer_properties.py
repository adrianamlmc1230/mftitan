"""Match_Importer 屬性測試。

Property 7: 匯入資料前處理與結算完整性
Property 11: 批量匯入錯誤隔離
"""

import os
import re
import tempfile

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.config_store import ConfigStore
from core.match_importer import ImportResult, MatchImporter
from core.models import MatchRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_store() -> ConfigStore:
    """Create a ConfigStore backed by a temporary file."""
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")
    return ConfigStore(db_path=db_path)


def _seed_season(store: ConfigStore) -> int:
    """Create a league + season and return season_instance_id."""
    lid = store.create_league(
        continent="EUR",
        code="TST" + os.urandom(4).hex(),
        name_zh="Test",
    )
    sid = store.create_season_instance(league_id=lid, label="2025", year_start=2025)
    return sid


def _create_test_excel(
    rows: list[list],
    metadata_row: list | None = None,
) -> str:
    """Create a test Excel file and return its path.

    Args:
        rows: Data rows (each is a list of 7 values: round, home, score, away, x, settlement, link).
        metadata_row: Optional Row 1 metadata (4 values: country, league, season, play_type).

    Returns:
        Path to the created xlsx file.
    """
    all_rows = []
    if metadata_row is not None:
        # Pad metadata to 7 columns
        padded = metadata_row + [None] * (7 - len(metadata_row))
        all_rows.append(padded)
    else:
        all_rows.append(["中國", "中超", "2025", "亞讓", None, None, None])

    all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(path, index=False, header=False, engine="openpyxl")
    return path


# ---------------------------------------------------------------------------
# Simplified Chinese characters for testing
# ---------------------------------------------------------------------------

_SIMPLIFIED_CHARS = list("赢输队员场")
_TRADITIONAL_MAP = {"赢": "贏", "输": "輸", "队": "隊", "员": "員", "场": "場"}

# Bracket patterns
_BRACKET_EXAMPLES = ["[中]", "[降]", "[升]", "[新]"]

# Digit suffix examples
_DIGIT_SUFFIXES = ["1", "2", "12", "99"]

# Valid HDP settlement texts
_VALID_HDP_SETTLEMENTS = [
    "主贏", "主贏半", "主輸半", "主輸",
    "客贏", "客贏半", "客輸半", "客輸",
]

# Valid OU settlement texts
_VALID_OU_SETTLEMENTS = [
    "大贏", "大贏半", "大輸半", "大輸",
    "小贏", "小贏半", "小輸半", "小輸",
]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate team names that may contain simplified chars, brackets, digit suffixes
team_name_base = st.text(
    alphabet=st.sampled_from(list("甲乙丙丁戊己庚辛壬癸天地人和")),
    min_size=1,
    max_size=3,
)

simplified_prefix = st.sampled_from([""] + _SIMPLIFIED_CHARS)
bracket_suffix = st.sampled_from([""] + _BRACKET_EXAMPLES)
digit_suffix = st.sampled_from([""] + _DIGIT_SUFFIXES)


@st.composite
def dirty_team_name(draw):
    """Generate a team name that may have simplified chars, brackets, digit suffixes."""
    base = draw(team_name_base)
    sc = draw(simplified_prefix)
    br = draw(bracket_suffix)
    ds = draw(digit_suffix)
    return sc + base + br + ds


@st.composite
def match_row_st(draw, play_type="HDP"):
    """Generate a single match data row (7 columns)."""
    round_num = draw(st.integers(min_value=1, max_value=50))
    home = draw(dirty_team_name())
    away = draw(dirty_team_name())
    score = draw(st.sampled_from(["1:0", "2:1", "0:0", "3:2", ""]))
    x_value = draw(st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False))
    x_value = round(x_value, 2)

    if play_type == "HDP":
        settlement = draw(st.sampled_from(_VALID_HDP_SETTLEMENTS + ["不適用", ""]))
    else:
        settlement = draw(st.sampled_from(_VALID_OU_SETTLEMENTS + ["不適用", ""]))

    link = draw(st.sampled_from(["https://example.com", "", "http://test.com/match"]))
    return [round_num, home, score, away, x_value, settlement, link]


play_types = st.sampled_from(["HDP", "OU"])
timings = st.sampled_from(["Early", "RT"])


# Regex patterns for validation
_BRACKET_RE = re.compile(r"\[.*?\]")
_DIGIT_SUFFIX_RE = re.compile(r"\d+$")


def _has_simplified_chinese(text: str) -> bool:
    """Check if text contains known simplified Chinese characters."""
    for sc in _SIMPLIFIED_CHARS:
        if sc in text:
            return True
    return False


# ===========================================================================
# Property 7: 匯入資料前處理與結算完整性
# Feature: rpa-data-driven-league, Property 7: 匯入資料前處理與結算完整性
# Validates: 需求 4.7, 4.8
# ===========================================================================

@given(
    play_type=play_types,
    timing=timings,
    rows=st.lists(match_row_st(play_type="HDP"), min_size=1, max_size=5),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property7_import_preprocessing_and_settlement_completeness(
    play_type, timing, rows,
):
    """匯入資料前處理與結算完整性：匯入後的紀錄不含簡體字、不含方括號、
    不含數字後綴，且結算欄位已正確填入。

    **Validates: Requirements 4.7, 4.8**
    """
    store = _fresh_store()
    sid = _seed_season(store)
    importer = MatchImporter(store)

    # Adjust settlement texts based on actual play_type
    adjusted_rows = []
    for row in rows:
        r = list(row)
        if play_type == "OU":
            # Replace HDP settlements with OU equivalents
            settlement = r[5]
            if settlement in _VALID_HDP_SETTLEMENTS:
                idx = _VALID_HDP_SETTLEMENTS.index(settlement)
                r[5] = _VALID_OU_SETTLEMENTS[idx]
        adjusted_rows.append(r)

    # Create test Excel file
    excel_path = _create_test_excel(adjusted_rows)

    try:
        result = importer.import_file(excel_path, sid, play_type, timing)

        if not result.success:
            # If import failed (e.g., all rows invalid), skip validation
            return

        # Fetch imported records from DB
        records = store.get_match_records(sid, play_type=play_type, timing=timing)

        for rec in records:
            # (a) 隊伍名稱不含簡體字
            assert not _has_simplified_chinese(rec.home_team), (
                f"home_team contains simplified Chinese: {rec.home_team}"
            )
            assert not _has_simplified_chinese(rec.away_team), (
                f"away_team contains simplified Chinese: {rec.away_team}"
            )

            # (b) 不含方括號標記
            assert not _BRACKET_RE.search(rec.home_team), (
                f"home_team contains brackets: {rec.home_team}"
            )
            assert not _BRACKET_RE.search(rec.away_team), (
                f"away_team contains brackets: {rec.away_team}"
            )

            # (c) B/D 欄不含數字後綴
            assert not _DIGIT_SUFFIX_RE.search(rec.home_team), (
                f"home_team has digit suffix: {rec.home_team}"
            )
            assert not _DIGIT_SUFFIX_RE.search(rec.away_team), (
                f"away_team has digit suffix: {rec.away_team}"
            )

            # (d) 具有有效結算文字的紀錄，結算欄位已正確填入
            settlement_text = rec.settlement
            valid_settlements = (
                _VALID_HDP_SETTLEMENTS if play_type == "HDP" else _VALID_OU_SETTLEMENTS
            )
            if settlement_text in valid_settlements:
                assert rec.settlement_value in (0.5, 1.0), (
                    f"settlement_value should be 0.5 or 1.0, got {rec.settlement_value}"
                )
                assert rec.settlement_direction in ("win", "lose"), (
                    f"settlement_direction should be 'win' or 'lose', got '{rec.settlement_direction}'"
                )
                assert rec.home_away_direction in ("home", "away"), (
                    f"home_away_direction should be 'home' or 'away', got '{rec.home_away_direction}'"
                )
                assert rec.target_team != "", (
                    f"target_team should not be empty for valid settlement"
                )
    finally:
        store._conn.close()
        try:
            os.unlink(excel_path)
        except OSError:
            pass



# ===========================================================================
# Property 11: 批量匯入錯誤隔離
# Feature: rpa-data-driven-league, Property 11: 批量匯入錯誤隔離
# Validates: 需求 4.4
# ===========================================================================

@given(
    good_rows=st.lists(match_row_st(play_type="HDP"), min_size=1, max_size=3),
    timing=timings,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_property11_batch_import_error_isolation(good_rows, timing):
    """批量匯入錯誤隔離：某個檔案失敗時，其餘檔案的匯入結果不受影響。

    **Validates: Requirements 4.4**
    """
    store = _fresh_store()
    importer = MatchImporter(store)

    # Create two seasons for two different "files"
    lid = store.create_league(
        continent="EUR",
        code="ISO" + os.urandom(4).hex(),
        name_zh="Test",
    )
    sid1 = store.create_season_instance(league_id=lid, label="2024", year_start=2024)
    sid2 = store.create_season_instance(league_id=lid, label="2025", year_start=2025)

    play_type = "HDP"

    # File 1: valid Excel
    good_path = _create_test_excel(good_rows)

    # File 2: invalid (non-existent path)
    bad_path = os.path.join(tempfile.mkdtemp(), "nonexistent.xlsx")

    try:
        # Import good file first
        result_good = importer.import_file(good_path, sid1, play_type, timing)

        # Import bad file — should fail
        result_bad = importer.import_file(bad_path, sid2, play_type, timing)

        # Bad file should fail
        assert not result_bad.success, "Bad file import should fail"

        # Good file's records should still be intact
        records = store.get_match_records(sid1, play_type=play_type, timing=timing)

        if result_good.success:
            assert len(records) == result_good.records_imported, (
                f"Good file records should be preserved: expected {result_good.records_imported}, "
                f"got {len(records)}"
            )
        else:
            # If good file also failed (e.g., all rows invalid), records should be 0
            assert len(records) == 0

        # Bad file's season should have no records
        bad_records = store.get_match_records(sid2, play_type=play_type, timing=timing)
        assert len(bad_records) == 0, "Bad file should not have any records"

    finally:
        store._conn.close()
        try:
            os.unlink(good_path)
        except OSError:
            pass
