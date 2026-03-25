"""SettlementCalculator：為比賽紀錄計算結算值、方向與主客場判定。

結算文字解析邏輯：
  HDP 有效值：主贏, 主贏半, 主輸半, 主輸, 客贏, 客贏半, 客輸半, 客輸
  OU  有效值：大贏, 大贏半, 大輸半, 大輸, 小贏, 小贏半, 小輸半, 小輸

  前綴判定 home_away_direction：
    HDP：「主」→ home，「客」→ away
    OU ：「大」→ home，「小」→ away

  後綴判定 settlement_value + settlement_direction：
    包含「半」→ value=0.5，否則 → value=1.0
    包含「贏」→ direction='win'
    包含「輸」→ direction='lose'

  target_team：
    home → rec.home_team
    away → rec.away_team

  無效值跳過：不適用, 不適用(平), 空字串
"""

import logging
from core.models import MatchRecord

logger = logging.getLogger(__name__)

# Prefixes that map to home_away_direction based on play_type
_HDP_PREFIX_MAP: dict[str, str] = {
    "主": "home",
    "客": "away",
}

_OU_PREFIX_MAP: dict[str, str] = {
    "大": "home",
    "小": "away",
}

# Values to skip entirely
_SKIP_VALUES = frozenset({"不適用", "不適用(平)", ""})

# All 8 valid HDP settlements
_VALID_HDP = frozenset({
    "主贏", "主贏半", "主輸半", "主輸",
    "客贏", "客贏半", "客輸半", "客輸",
})

# All 8 valid OU settlements
_VALID_OU = frozenset({
    "大贏", "大贏半", "大輸半", "大輸",
    "小贏", "小贏半", "小輸半", "小輸",
})


class SettlementCalculator:
    """結算值計算器：解析結算文字，填入 value、direction、home_away_direction、target_team。"""

    def calculate(self, records: list[MatchRecord]) -> list[MatchRecord]:
        """為每筆紀錄填入結算相關欄位。

        每筆 MatchRecord 必須已設定 play_type（'HDP' 或 'OU'），
        calculate 會根據 settlement 文字解析並填入：
          - settlement_value (0.5 or 1.0)
          - settlement_direction ('win' or 'lose')
          - home_away_direction ('home' or 'away')
          - target_team (home_team or away_team)

        無效或不適用的結算文字會被跳過（欄位保持預設空值）。

        Args:
            records: 比賽紀錄列表（需已設定 play_type）。

        Returns:
            填入結算值後的紀錄列表（原地修改並回傳）。
        """
        anomalies = 0

        for rec in records:
            text = rec.settlement.strip()

            # Skip invalid/empty values
            if text in _SKIP_VALUES:
                rec.settlement_value = 0.0
                rec.settlement_direction = ""
                rec.home_away_direction = ""
                rec.target_team = ""
                continue

            # Determine valid set and prefix map based on play_type
            if rec.play_type == "HDP":
                valid_set = _VALID_HDP
                prefix_map = _HDP_PREFIX_MAP
            elif rec.play_type == "OU":
                valid_set = _VALID_OU
                prefix_map = _OU_PREFIX_MAP
            else:
                logger.warning(
                    "未知 play_type：'%s'（主隊=%s vs 客隊=%s）",
                    rec.play_type, rec.home_team, rec.away_team,
                )
                rec.settlement_value = 0.0
                rec.settlement_direction = ""
                rec.home_away_direction = ""
                rec.target_team = ""
                anomalies += 1
                continue

            # Check if settlement text is in the valid set
            if text not in valid_set:
                logger.warning(
                    "異常結算值：'%s'（play_type=%s, 主隊=%s vs 客隊=%s）",
                    text, rec.play_type, rec.home_team, rec.away_team,
                )
                rec.settlement_value = 0.0
                rec.settlement_direction = ""
                rec.home_away_direction = ""
                rec.target_team = ""
                anomalies += 1
                continue

            # Parse prefix (first character) → home_away_direction
            prefix = text[0]
            direction = prefix_map.get(prefix, "")
            if not direction:
                # Should not happen if valid_set is correct, but guard anyway
                logger.warning("無法判定方向前綴：'%s'", text)
                anomalies += 1
                continue

            rec.home_away_direction = direction

            # Parse suffix → settlement_value + settlement_direction
            suffix = text[1:]  # e.g. "贏", "贏半", "輸", "輸半"
            rec.settlement_value = 0.5 if "半" in suffix else 1.0
            rec.settlement_direction = "win" if "贏" in suffix else "lose"

            # Set target_team based on direction
            rec.target_team = rec.home_team if direction == "home" else rec.away_team

        if anomalies:
            logger.warning("共 %d 筆異常結算值", anomalies)

        logger.info("結算計算完成：%d 筆紀錄", len(records))
        return records
