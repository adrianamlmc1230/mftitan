"""RawDataReader 單元測試。"""

import pandas as pd
import pytest
from unittest.mock import patch
from pathlib import Path

from core.reader import RawDataReader


@pytest.fixture
def reader():
    return RawDataReader()


def _make_df(metadata_row=None, data_rows=None):
    """建立測試用 DataFrame。

    Args:
        metadata_row: Row 1 metadata，例如 ["中國", "中超", "2025", "亞讓"]
        data_rows: Row 2+ 資料列，每列為 [輪次, 主隊, C欄, 客隊, X值, 結算]
    """
    rows = []
    if metadata_row is not None:
        rows.append(metadata_row)
    if data_rows is not None:
        rows.extend(data_rows)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


class TestRead:
    """子任務 6.1：使用 openpyxl 讀取 xlsx 檔案為 DataFrame。"""

    def test_file_not_found(self, reader):
        result = reader.read("nonexistent_file.xlsx")
        assert result.empty

    def test_read_valid_xlsx(self, reader, tmp_path):
        # 建立一個真實的 xlsx 檔案
        filepath = tmp_path / "test.xlsx"
        df = pd.DataFrame([[1, "主隊", "data", "客隊", 0.1, "贏"]])
        df.to_excel(filepath, index=False, header=False, engine="openpyxl")

        result = reader.read(str(filepath))
        assert not result.empty
        assert len(result) == 1

    def test_read_corrupted_file(self, reader, tmp_path):
        filepath = tmp_path / "corrupted.xlsx"
        filepath.write_text("this is not a valid xlsx file")
        result = reader.read(str(filepath))
        assert result.empty

    def test_read_empty_xlsx(self, reader, tmp_path):
        """空的 xlsx 檔案（無任何資料列）。"""
        filepath = tmp_path / "empty.xlsx"
        df = pd.DataFrame()
        df.to_excel(filepath, index=False, header=False, engine="openpyxl")
        result = reader.read(str(filepath))
        assert result.empty


class TestExtractMetadata:
    """子任務 6.2：Row 1 metadata 提取與交叉驗證。"""

    def test_valid_metadata(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[[1, "主隊", "data", "客隊", 0.1, "贏"]],
        )
        meta = reader.extract_metadata(df)
        assert meta is not None
        assert meta["country"] == "中國"
        assert meta["league_name"] == "中超"
        assert meta["season"] == "2025"
        assert meta["play_type"] == "亞讓"

    def test_empty_df(self, reader):
        df = pd.DataFrame()
        assert reader.extract_metadata(df) is None

    def test_insufficient_columns(self, reader):
        df = pd.DataFrame([["中國", "中超"]])
        assert reader.extract_metadata(df) is None

    def test_nan_in_metadata(self, reader):
        df = pd.DataFrame([["中國", None, "2025", "亞讓"]])
        assert reader.extract_metadata(df) is None

    def test_empty_string_in_metadata(self, reader):
        df = pd.DataFrame([["中國", "", "2025", "亞讓"]])
        assert reader.extract_metadata(df) is None

    def test_numeric_season(self, reader):
        """賽季欄位為數字時應正確轉為字串。"""
        df = pd.DataFrame([["中國", "中超", 2025, "亞讓"]])
        meta = reader.extract_metadata(df)
        assert meta is not None
        assert meta["season"] == "2025"

    def test_whitespace_trimmed(self, reader):
        df = pd.DataFrame([["  中國  ", " 中超 ", " 2025 ", " 亞讓 "]])
        meta = reader.extract_metadata(df)
        assert meta["country"] == "中國"
        assert meta["league_name"] == "中超"


class TestExtractRecords:
    """子任務 6.3：從清理後的 DataFrame 提取 MatchRecord 列表。"""

    def test_basic_extraction(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "北京國安", "data", "上海申花", 0.15, "贏"],
                [2, "廣州恆大", "data", "山東泰山", -0.08, "輸"],
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 2

        assert records[0].round_num == 1
        assert records[0].home_team == "北京國安"
        assert records[0].away_team == "上海申花"
        assert records[0].x_value == 0.15
        assert records[0].settlement == "贏"
        assert records[0].settlement_value == 0.0  # 預設值
        assert records[0].settlement_direction == ""  # 預設值

        assert records[1].round_num == 2
        assert records[1].settlement == "輸"

    def test_empty_df(self, reader):
        df = pd.DataFrame()
        assert reader.extract_records(df) == []

    def test_only_metadata_row(self, reader):
        df = _make_df(metadata_row=["中國", "中超", "2025", "亞讓"])
        assert reader.extract_records(df) == []

    def test_insufficient_columns(self, reader):
        df = pd.DataFrame([["meta1", "meta2"], [1, "隊伍"]])
        assert reader.extract_records(df) == []

    def test_skip_invalid_round_num(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                ["abc", "主隊", "data", "客隊", 0.1, "贏"],
                [2, "主隊B", "data", "客隊B", 0.2, "輸"],
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 1
        assert records[0].round_num == 2

    def test_skip_nan_round_num(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [None, "主隊", "data", "客隊", 0.1, "贏"],
            ],
        )
        assert reader.extract_records(df) == []

    def test_skip_invalid_x_value(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "主隊", "data", "客隊", "not_a_number", "贏"],
                [2, "主隊B", "data", "客隊B", 0.2, "輸"],
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 1
        assert records[0].round_num == 2

    def test_skip_empty_home_team(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "", "data", "客隊", 0.1, "贏"],
            ],
        )
        assert reader.extract_records(df) == []

    def test_skip_nan_away_team(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "主隊", "data", None, 0.1, "贏"],
            ],
        )
        assert reader.extract_records(df) == []

    def test_nan_settlement_becomes_empty_string(self, reader):
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "主隊", "data", "客隊", 0.1, None],
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 1
        assert records[0].settlement == ""

    def test_float_round_num_converted_to_int(self, reader):
        """輪次為浮點數（如 3.0）時應正確轉為整數。"""
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [3.0, "主隊", "data", "客隊", 0.1, "贏"],
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 1
        assert records[0].round_num == 3

    def test_all_settlement_types(self, reader):
        """驗證各種結算類型都能正確提取。"""
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "A隊", "d", "B隊", 0.1, "贏"],
                [2, "C隊", "d", "D隊", 0.2, "輸"],
                [3, "E隊", "d", "F隊", -0.1, "贏半"],
                [4, "G隊", "d", "H隊", -0.2, "輸半"],
                [5, "I隊", "d", "J隊", 0.0, "走水"],
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 5
        settlements = [r.settlement for r in records]
        assert settlements == ["贏", "輸", "贏半", "輸半", "走水"]

    def test_mixed_valid_and_invalid_rows(self, reader):
        """混合有效與無效資料列，只提取有效的。"""
        df = _make_df(
            metadata_row=["中國", "中超", "2025", "亞讓"],
            data_rows=[
                [1, "主隊A", "d", "客隊A", 0.1, "贏"],       # 有效
                ["x", "主隊B", "d", "客隊B", 0.2, "輸"],     # 無效輪次
                [3, "", "d", "客隊C", 0.3, "贏"],             # 空主隊
                [4, "主隊D", "d", "客隊D", "bad", "輸"],      # 無效 X 值
                [5, "主隊E", "d", "客隊E", -0.05, "走水"],    # 有效
            ],
        )
        records = reader.extract_records(df)
        assert len(records) == 2
        assert records[0].round_num == 1
        assert records[1].round_num == 5
