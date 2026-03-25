"""RoundBlockAggregator：按輪次區段匯總各 X 值區間的贏/輸結算值。

統計矩陣維度：輪次 × 9 區間 × Home/Away × Win/Lose

匯總邏輯：
  對每筆 MatchRecord，根據 home_away_direction 和 settlement_direction 組合，
  將 settlement_value 累加至對應的 ZoneStats 欄位：
    home + win  → home_win
    home + lose → home_lose
    away + win  → away_win
    away + lose → away_lose
  settlement_direction 為 'draw' 或空字串時跳過。
"""

import logging
from core.models import MatchRecord, ZoneStats, RoundBlockStats

logger = logging.getLogger(__name__)


class RoundBlockAggregator:
    """輪次區段匯總器（支援 Home/Away 方向拆分）。"""

    def aggregate(
        self,
        classified: dict[int, list[MatchRecord]],
        block_size: int = 10,
        max_blocks: int | None = None,
    ) -> list[RoundBlockStats]:
        """按輪次區段匯總 9 個區間的 Home/Away 贏/輸結算值。

        Args:
            classified: {zone_id: [MatchRecord]} 已分類的紀錄。
            block_size: 每個區段包含的輪次數。
            max_blocks: 最大區段數。None 表示自動根據資料決定。

        Returns:
            RoundBlockStats 列表。
        """
        # 自動計算需要的區段數
        if max_blocks is None:
            max_round = 0
            for recs in classified.values():
                for rec in recs:
                    if rec.round_num > max_round:
                        max_round = rec.round_num
            max_blocks = max(1, (max_round + block_size - 1) // block_size) if max_round > 0 else 1

        blocks: list[RoundBlockStats] = []

        for block_id in range(1, max_blocks + 1):
            round_start = (block_id - 1) * block_size + 1
            round_end = block_id * block_size

            zones: list[ZoneStats] = []
            for zone_id in range(1, 10):
                recs = classified.get(zone_id, [])
                home_win = 0.0
                home_lose = 0.0
                away_win = 0.0
                away_lose = 0.0

                for rec in recs:
                    if round_start <= rec.round_num <= round_end:
                        if rec.settlement_direction == "win":
                            if rec.home_away_direction == "home":
                                home_win += rec.settlement_value
                            elif rec.home_away_direction == "away":
                                away_win += rec.settlement_value
                        elif rec.settlement_direction == "lose":
                            if rec.home_away_direction == "home":
                                home_lose += rec.settlement_value
                            elif rec.home_away_direction == "away":
                                away_lose += rec.settlement_value
                        # 'draw' or empty → skip

                zones.append(ZoneStats(
                    zone_id=zone_id,
                    home_win=home_win,
                    home_lose=home_lose,
                    away_win=away_win,
                    away_lose=away_lose,
                ))

            blocks.append(RoundBlockStats(
                block_id=block_id,
                round_start=round_start,
                round_end=round_end,
                zones=zones,
            ))

        logger.info("輪次區段匯總完成：%d 個區段", len(blocks))
        return blocks

    def season_total(self, blocks: list[RoundBlockStats]) -> list[ZoneStats]:
        """計算全季匯總（所有區段加總）。

        Args:
            blocks: 輪次區段統計列表。

        Returns:
            9 個 ZoneStats 的全季匯總。
        """
        totals: dict[int, list[float]] = {}
        for zone_id in range(1, 10):
            totals[zone_id] = [0.0, 0.0, 0.0, 0.0]  # home_win, home_lose, away_win, away_lose

        for block in blocks:
            for zs in block.zones:
                t = totals[zs.zone_id]
                t[0] += zs.home_win
                t[1] += zs.home_lose
                t[2] += zs.away_win
                t[3] += zs.away_lose

        result = [
            ZoneStats(
                zone_id=zid,
                home_win=vals[0],
                home_lose=vals[1],
                away_win=vals[2],
                away_lose=vals[3],
            )
            for zid, vals in sorted(totals.items())
        ]
        return result
