"""RawDataPreprocessor 單元測試。"""

import pandas as pd
import pytest

from core.preprocessor import RawDataPreprocessor


@pytest.fixture
def preprocessor():
    return RawDataPreprocessor()


class TestProcessReturnsCopy:
    """驗收條件 4.4：在 DataFrame 記憶體中完成所有清理操作，不修改原始資料。"""

    def test_original_df_unchanged(self, preprocessor):
        df = pd.DataFrame({0: ["赢"], 1: ["隊伍1"], 2: ["data"], 3: ["客隊2"], 4: [0.1], 5: ["赢"]})
        original_copy = df.copy()
        result, _ = preprocessor.process(df)
        pd.testing.assert_frame_equal(df, original_copy)

    def test_returns_tuple(self, preprocessor):
        df = pd.DataFrame({0: ["a"], 1: ["b"], 2: ["c"], 3: ["d"]})
        result = preprocessor.process(df)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], pd.DataFrame)
        assert isinstance(result[1], dict)


class TestSimplifiedToTraditional:
    """驗收條件 4.1：簡繁轉換，至少包含「赢」→「贏」、「输」→「輸」、「不适用(平)」→「不適用(平)」。"""

    def test_win_conversion(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["主隊"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["赢"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 5] == "贏"
        assert stats['simplified_replaced'] > 0

    def test_lose_conversion(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["主隊"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["输"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 5] == "輸"

    def test_not_applicable_conversion(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["主隊"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["不适用(平)"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 5] == "不適用(平)"

    def test_multiple_rows(self, preprocessor):
        df = pd.DataFrame({
            0: [1, 2, 3],
            1: ["主隊", "主隊", "主隊"],
            2: ["x", "y", "z"],
            3: ["客隊", "客隊", "客隊"],
            4: [0.1, 0.2, 0.3],
            5: ["赢", "输", "赢"],
        })
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 5] == "贏"
        assert result.iloc[1, 5] == "輸"
        assert result.iloc[2, 5] == "贏"

    def test_no_simplified_chars(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["主隊"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 5] == "贏"


class TestBracketRemoval:
    """驗收條件 4.2：移除所有方括號標記。"""

    def test_remove_single_bracket(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["隊伍[中]"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"
        assert stats['brackets_removed'] > 0

    def test_remove_multiple_brackets(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["[前]隊伍[後]"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"

    def test_bracket_with_numbers(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["隊伍[12]"], 2: ["data"], 3: ["客隊[3]"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"
        assert result.iloc[0, 3] == "客隊"

    def test_no_brackets(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["隊伍"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert stats['brackets_removed'] == 0


class TestDigitSuffixRemoval:
    """驗收條件 4.3：移除 B 欄與 D 欄中的數字後綴。"""

    def test_remove_digit_from_col_b(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["隊伍1"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"
        assert stats['digits_removed'] > 0

    def test_remove_digit_from_col_d(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["主隊"], 2: ["data"], 3: ["客隊2"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 3] == "客隊"

    def test_remove_multi_digit_suffix(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["隊伍12"], 2: ["data"], 3: ["客隊345"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"
        assert result.iloc[0, 3] == "客隊"

    def test_no_digit_suffix(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["隊伍"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"
        assert result.iloc[0, 3] == "客隊"

    def test_does_not_affect_other_columns(self, preprocessor):
        """數字後綴清除只影響 B 欄（index 1）和 D 欄（index 3），不影響其他欄位。"""
        df = pd.DataFrame({0: ["10"], 1: ["隊伍1"], 2: ["data2"], 3: ["客隊3"], 4: [0.1], 5: ["贏"]})
        result, _ = preprocessor.process(df)
        # A 欄（index 0）的數字不應被移除
        assert result.iloc[0, 0] == "10"
        # C 欄（index 2）的數字不應被移除
        assert result.iloc[0, 2] == "data2"


class TestStatsDict:
    """驗收條件 4.5：記錄清理統計。"""

    def test_stats_keys(self, preprocessor):
        df = pd.DataFrame({0: [1], 1: ["主隊"], 2: ["data"], 3: ["客隊"], 4: [0.1], 5: ["贏"]})
        _, stats = preprocessor.process(df)
        assert 'simplified_replaced' in stats
        assert 'brackets_removed' in stats
        assert 'digits_removed' in stats

    def test_combined_stats(self, preprocessor):
        df = pd.DataFrame({
            0: [1, 2],
            1: ["隊伍1[中]", "隊伍2"],
            2: ["data", "data"],
            3: ["客隊[後]3", "客隊"],
            4: [0.1, 0.2],
            5: ["赢", "输"],
        })
        result, stats = preprocessor.process(df)
        assert stats['simplified_replaced'] > 0
        assert stats['brackets_removed'] > 0
        assert stats['digits_removed'] > 0


class TestEdgeCases:
    """邊界情況測試。"""

    def test_empty_dataframe(self, preprocessor):
        df = pd.DataFrame()
        result, stats = preprocessor.process(df)
        assert len(result) == 0
        assert stats['simplified_replaced'] == 0
        assert stats['brackets_removed'] == 0
        assert stats['digits_removed'] == 0

    def test_dataframe_with_fewer_than_4_columns(self, preprocessor):
        """少於 4 欄時，數字後綴清除應安全跳過不存在的欄位。"""
        df = pd.DataFrame({0: ["data"], 1: ["隊伍1"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 1] == "隊伍"
        # D 欄不存在，不應報錯

    def test_nan_values(self, preprocessor):
        """含有 NaN 值時不應報錯。"""
        df = pd.DataFrame({0: [1], 1: [None], 2: ["data"], 3: [None], 4: [0.1], 5: ["赢"]})
        result, stats = preprocessor.process(df)
        assert result.iloc[0, 5] == "贏"
