"""SeasonAggregator：合併當季與上季的區間統計（支援 Home/Away 方向拆分）。"""

import logging
from core.models import ZoneStats

logger = logging.getLogger(__name__)


def _empty_zones() -> list[ZoneStats]:
    """產生 9 個空的 ZoneStats。"""
    return [ZoneStats(zone_id=i) for i in range(1, 10)]


class SeasonAggregator:
    """賽季層級匯總器。"""

    def aggregate(
        self,
        current_zones: list[ZoneStats] | None,
        previous_zones: list[ZoneStats] | None,
    ) -> tuple[list[ZoneStats], list[ZoneStats], list[ZoneStats]]:
        """合併當季與上季統計，計算跨賽季匯總。

        Args:
            current_zones: 當季 9 區間統計（None 時全部為 0）。
            previous_zones: 上季 9 區間統計（None 時全部為 0）。

        Returns:
            (previous, current, cross_season) 三組 ZoneStats 列表。
        """
        prev = previous_zones if previous_zones else _empty_zones()
        curr = current_zones if current_zones else _empty_zones()

        cross: list[ZoneStats] = []
        for p, c in zip(prev, curr):
            cross.append(ZoneStats(
                zone_id=p.zone_id,
                home_win=p.home_win + c.home_win,
                home_lose=p.home_lose + c.home_lose,
                away_win=p.away_win + c.away_win,
                away_lose=p.away_lose + c.away_lose,
            ))

        return prev, curr, cross
