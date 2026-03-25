"""FiveZoneGrouper：將 9 個 X 值區間合併為 5 大區間。

預設 mapping: [[1], [2,3,4], [5,6], [7,8], [9]]

每個大區間分別計算 Home 方向和 Away 方向的贏/輸值（設計決策 1）。
回傳格式為 list[tuple[float, float, float, float]]，
每個 tuple 為 (home_win, home_lose, away_win, away_lose)。
"""

import logging
from core.models import ZoneStats

logger = logging.getLogger(__name__)

DEFAULT_MAPPING = [[1], [2, 3, 4], [5, 6], [7, 8], [9]]


def validate_five_zone_mapping(mapping: list[list[int]], num_zones: int = 9) -> None:
    """驗證五大區間分組：所有 zone_id 必須被涵蓋且不重複。"""
    all_ids = sorted(zid for group in mapping for zid in group)
    expected = list(range(1, num_zones + 1))
    if all_ids != expected:
        raise ValueError(
            f"分組必須涵蓋所有區間：期望 {expected}，實際 {all_ids}"
        )


class FiveZoneGrouper:
    """五大區間分組器（支援 Home/Away 方向拆分）。"""

    def group(
        self,
        zones: list[ZoneStats],
        mapping: list[list[int]] | None = None,
    ) -> list[tuple[float, float, float, float]]:
        """將 9 區間合併為 5 大區間。

        Args:
            zones: 9 個 ZoneStats（zone_id 1~9）。
            mapping: 5 組 zone_id 列表，預設 [[1],[2,3,4],[5,6],[7,8],[9]]。

        Returns:
            5 個 (home_win, home_lose, away_win, away_lose) tuple。
        """
        if mapping is None:
            mapping = DEFAULT_MAPPING

        validate_five_zone_mapping(mapping)

        zone_map: dict[int, ZoneStats] = {z.zone_id: z for z in zones}

        result: list[tuple[float, float, float, float]] = []
        for group_ids in mapping:
            hw = 0.0
            hl = 0.0
            aw = 0.0
            al = 0.0
            for zid in group_ids:
                zs = zone_map.get(zid)
                if zs:
                    hw += zs.home_win
                    hl += zs.home_lose
                    aw += zs.away_win
                    al += zs.away_lose
            result.append((hw, hl, aw, al))

        logger.info("五大區間分組完成：%d 組", len(result))
        return result
