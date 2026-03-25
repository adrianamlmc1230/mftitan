"""FilenameParser 屬性測試：使用 Hypothesis 驗證檔名解析的正確性屬性。"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.filename_parser import FilenameParser

parser = FilenameParser()

# --- Strategies ---

# 合法的 SUFFIX_MAP keys 與對應的 (timing, play_type)
SUFFIX_KEYS = list(FilenameParser.SUFFIX_MAP.keys())

# 合法的聯賽中文名（完整名稱，不拆分國家）
NAME_ZH_LIST = st.sampled_from([
    "中國中超", "英格蘭英超", "西班牙西甲", "德國德甲", "法國法甲",
    "義大利義甲", "荷蘭荷甲", "葡萄牙葡超", "土耳其土超", "土耳其土甲",
    "韓國韓職聯", "巴西巴甲", "巴西巴乙", "哥倫比亞哥甲", "墨西哥墨超",
    "沙烏地沙職", "日本日職", "澳洲澳超", "美國美職", "加拿大加超",
    "澳大利亞澳超",
])

# 合法的賽季年份
SEASON_YEARS = st.one_of(
    st.integers(min_value=2020, max_value=2030).map(str),
    st.integers(min_value=2020, max_value=2029).map(lambda y: f"{y}-{y + 1}"),
)

# 合法的階段（可選）
PHASES = st.one_of(
    st.just(""),
    st.sampled_from(["第一階段", "第二階段", "第三階段", "第四階段", "第五階段"]),
)


@st.composite
def valid_filenames(draw):
    """生成合法的 RPA Excel 檔名。"""
    name_zh = draw(NAME_ZH_LIST)
    season_year = draw(SEASON_YEARS)
    phase = draw(PHASES)
    suffix_key = draw(st.sampled_from(SUFFIX_KEYS))
    filename = f"{name_zh}{season_year}{phase}{suffix_key}.xlsx"
    return filename


# Feature: rpa-data-driven-league, Property 1: 檔名解析往返一致性
class TestFilenameRoundTrip:
    """Property 1: 檔名解析往返一致性。"""

    @given(filename=valid_filenames())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_reconstruct_roundtrip(self, filename: str):
        """parse() → reconstruct() + '.xlsx' 應等於原始檔名。"""
        parsed = parser.parse(filename)
        reconstructed = parser.reconstruct(parsed) + ".xlsx"
        assert reconstructed == filename, (
            f"往返不一致: {filename!r} -> {reconstructed!r}"
        )


# Feature: rpa-data-driven-league, Property 2: 無效檔名產生描述性錯誤
class TestInvalidFilenameError:
    """Property 2: 無效檔名產生描述性錯誤。"""

    KNOWN_ERROR_FRAGMENTS = [
        "檔名必須以 .xlsx 結尾",
        "無法識別時機與玩法尾碼",
        "無法識別賽季年份",
        "無法識別聯賽名稱",
    ]

    @given(random_str=st.text(min_size=1, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_filename_raises_descriptive_error(self, random_str: str):
        """不符合預期模式的字串應拋出包含描述性訊息的 ValueError。"""
        try:
            parser.parse(random_str)
        except ValueError as e:
            error_msg = str(e)
            assert any(
                frag in error_msg for frag in self.KNOWN_ERROR_FRAGMENTS
            ), f"錯誤訊息不夠描述性: {error_msg!r}"
        else:
            pass
