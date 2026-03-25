"""舊版 filename_parser 測試（已簡化）。

新版解析器在 core/filename_parser.py，不再拆分國家和聯賽名。
"""

import unittest
from utils.filename_parser import parse_filename


class TestParseFilename(unittest.TestCase):
    """測試舊版 parse_filename 函數。"""

    def test_basic_parse(self):
        result = parse_filename("中國中超2025第一階段早亞讓.xlsx")
        assert result is not None
        assert result.name_zh == "中國中超"
        assert result.season_year == "2025"
        assert result.phase == "第一階段"
        assert result.timing == "Early"
        assert result.play_type == "HDP"

    def test_cross_year(self):
        result = parse_filename("土耳其土甲2025-2026第一階段早亞讓.xlsx")
        assert result is not None
        assert result.name_zh == "土耳其土甲"
        assert result.season_year == "2025-2026"

    def test_with_path(self):
        result = parse_filename("C:/data/E_HDP_RPA/中國中超2025第一階段早亞讓.xlsx")
        assert result is not None
        assert result.name_zh == "中國中超"
        assert result.original_path == "C:/data/E_HDP_RPA/中國中超2025第一階段早亞讓.xlsx"

    def test_invalid_returns_none(self):
        assert parse_filename("invalid.txt") is None
        assert parse_filename("") is None


if __name__ == "__main__":
    unittest.main()
