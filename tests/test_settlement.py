"""SettlementCalculator 單元測試：驗證結算值、方向判定、主客場方向與 target_team。"""

import pytest
from core.models import MatchRecord
from core.settlement import SettlementCalculator


@pytest.fixture
def calc():
    return SettlementCalculator()


# ---------------------------------------------------------------------------
# HDP 玩法：8 種有效結算值
# ---------------------------------------------------------------------------

class TestHDPSettlement:
    """HDP 玩法的結算計算測試。"""

    def test_hdp_home_win(self, calc):
        """主贏 → value=1.0, direction=win, home_away=home, target=home_team"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "主贏", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_hdp_home_win_half(self, calc):
        """主贏半 → value=0.5, direction=win, home_away=home"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "主贏半", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_hdp_home_lose(self, calc):
        """主輸 → value=1.0, direction=lose, home_away=home"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "主輸", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_hdp_home_lose_half(self, calc):
        """主輸半 → value=0.5, direction=lose, home_away=home"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "主輸半", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_hdp_away_win(self, calc):
        """客贏 → value=1.0, direction=win, home_away=away, target=away_team"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "客贏", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"

    def test_hdp_away_win_half(self, calc):
        """客贏半 → value=0.5, direction=win, home_away=away"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "客贏半", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"

    def test_hdp_away_lose(self, calc):
        """客輸 → value=1.0, direction=lose, home_away=away"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "客輸", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"

    def test_hdp_away_lose_half(self, calc):
        """客輸半 → value=0.5, direction=lose, home_away=away"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "客輸半", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"


# ---------------------------------------------------------------------------
# OU 玩法：8 種有效結算值
# ---------------------------------------------------------------------------

class TestOUSettlement:
    """OU 玩法的結算計算測試。"""

    def test_ou_over_win(self, calc):
        """大贏 → value=1.0, direction=win, home_away=home, target=home_team"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "大贏", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_ou_over_win_half(self, calc):
        """大贏半 → value=0.5, direction=win, home_away=home"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "大贏半", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_ou_over_lose(self, calc):
        """大輸 → value=1.0, direction=lose, home_away=home"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "大輸", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_ou_over_lose_half(self, calc):
        """大輸半 → value=0.5, direction=lose, home_away=home"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "大輸半", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "home"
        assert rec.target_team == "主隊A"

    def test_ou_under_win(self, calc):
        """小贏 → value=1.0, direction=win, home_away=away, target=away_team"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "小贏", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"

    def test_ou_under_win_half(self, calc):
        """小贏半 → value=0.5, direction=win, home_away=away"""
        rec = MatchRecord(1, "主隊A", "客隊B", 0.1, "小贏半", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "win"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"

    def test_ou_under_lose(self, calc):
        """小輸 → value=1.0, direction=lose, home_away=away"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "小輸", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 1.0
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"

    def test_ou_under_lose_half(self, calc):
        """小輸半 → value=0.5, direction=lose, home_away=away"""
        rec = MatchRecord(1, "主隊A", "客隊B", -0.1, "小輸半", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 0.5
        assert rec.settlement_direction == "lose"
        assert rec.home_away_direction == "away"
        assert rec.target_team == "客隊B"


# ---------------------------------------------------------------------------
# 無效值跳過
# ---------------------------------------------------------------------------

class TestSkipInvalid:
    """無效結算值應被跳過（需求 8.4）。"""

    def test_skip_empty(self, calc):
        rec = MatchRecord(1, "A", "B", 0.1, "", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.0
        assert rec.settlement_direction == ""
        assert rec.home_away_direction == ""
        assert rec.target_team == ""

    def test_skip_not_applicable(self, calc):
        rec = MatchRecord(1, "A", "B", 0.1, "不適用", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.0
        assert rec.settlement_direction == ""
        assert rec.home_away_direction == ""
        assert rec.target_team == ""

    def test_skip_not_applicable_draw(self, calc):
        rec = MatchRecord(1, "A", "B", 0.1, "不適用(平)", play_type="OU")
        calc.calculate([rec])
        assert rec.settlement_value == 0.0
        assert rec.settlement_direction == ""
        assert rec.home_away_direction == ""
        assert rec.target_team == ""

    def test_skip_whitespace_only(self, calc):
        rec = MatchRecord(1, "A", "B", 0.1, "   ", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.0
        assert rec.settlement_direction == ""

    def test_unknown_play_type(self, calc):
        """未知 play_type 應被視為異常。"""
        rec = MatchRecord(1, "A", "B", 0.1, "主贏", play_type="UNKNOWN")
        calc.calculate([rec])
        assert rec.settlement_value == 0.0
        assert rec.settlement_direction == ""

    def test_invalid_settlement_text(self, calc):
        """不在有效清單中的結算文字應被記錄為異常。"""
        rec = MatchRecord(1, "A", "B", 0.1, "走水", play_type="HDP")
        calc.calculate([rec])
        assert rec.settlement_value == 0.0
        assert rec.settlement_direction == ""


# ---------------------------------------------------------------------------
# 混合紀錄批次處理
# ---------------------------------------------------------------------------

class TestBatchProcessing:
    """批次處理多筆紀錄。"""

    def test_mixed_records(self, calc):
        """混合有效與無效紀錄的批次處理。"""
        records = [
            MatchRecord(1, "甲隊", "乙隊", 0.1, "主贏", play_type="HDP"),
            MatchRecord(1, "甲隊", "乙隊", 0.1, "不適用", play_type="HDP"),
            MatchRecord(2, "丙隊", "丁隊", -0.2, "小輸半", play_type="OU"),
            MatchRecord(3, "戊隊", "己隊", 0.0, "", play_type="OU"),
        ]
        result = calc.calculate(records)

        # 第 1 筆：主贏
        assert result[0].settlement_value == 1.0
        assert result[0].settlement_direction == "win"
        assert result[0].home_away_direction == "home"
        assert result[0].target_team == "甲隊"

        # 第 2 筆：不適用 → 跳過
        assert result[1].settlement_value == 0.0
        assert result[1].target_team == ""

        # 第 3 筆：小輸半
        assert result[2].settlement_value == 0.5
        assert result[2].settlement_direction == "lose"
        assert result[2].home_away_direction == "away"
        assert result[2].target_team == "丁隊"

        # 第 4 筆：空字串 → 跳過
        assert result[3].settlement_value == 0.0
        assert result[3].target_team == ""

    def test_returns_same_list(self, calc):
        """calculate 應原地修改並回傳同一個列表。"""
        records = [MatchRecord(1, "A", "B", 0.1, "主贏", play_type="HDP")]
        result = calc.calculate(records)
        assert result is records
