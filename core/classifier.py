"""XValueClassifier：將比賽紀錄依 X 值分類至 9 個區間。

使用 np.digitize() 進行向量化區間分類。
boundaries 為 8 個分界點，產生 9 個區間（zone_id 1~9）。

區間定義（使用預設分界點）：
  zone 1: X ≤ -0.24
  zone 2: -0.24 < X ≤ -0.22
  zone 3: -0.22 < X ≤ -0.15
  zone 4: -0.15 < X ≤ -0.08
  zone 5: -0.08 < X ≤ -0.03
  zone 6: -0.03 < X ≤ +0.07
  zone 7: +0.07 < X ≤ +0.15
  zone 8: +0.15 < X ≤ +0.23
  zone 9: X > +0.23
"""

import logging
import numpy as np
from core.models import MatchRecord

logger = logging.getLogger(__name__)


class XValueClassifier:
    """X 值區間分類器。"""

    DEFAULT_BOUNDARIES = [-0.24, -0.22, -0.15, -0.08, -0.03, 0.07, 0.15, 0.23]

    def classify(
        self,
        records: list[MatchRecord],
        boundaries: list[float] | None = None,
    ) -> dict[int, list[MatchRecord]]:
        """使用 np.digitize 將紀錄分至 9 個區間（zone_id 1~9）。

        區間規則：
          zone 1: X ≤ boundaries[0]
          zone k (2 ≤ k ≤ N): boundaries[k-2] < X ≤ boundaries[k-1]
          zone N+1: X > boundaries[-1]

        Args:
            records: 已計算結算值的比賽紀錄。
            boundaries: 分界點列表（升序），預設使用 DEFAULT_BOUNDARIES。

        Returns:
            dict[zone_id, list[MatchRecord]]，zone_id 為 1 ~ len(boundaries)+1。

        Raises:
            ValueError: 分界點未升序排列。
        """
        if boundaries is None:
            boundaries = self.DEFAULT_BOUNDARIES

        # Validate ascending order
        for i in range(1, len(boundaries)):
            if boundaries[i] <= boundaries[i - 1]:
                raise ValueError(
                    f"分界點必須升序排列：{boundaries[i - 1]} >= {boundaries[i]}"
                )

        num_zones = len(boundaries) + 1
        result: dict[int, list[MatchRecord]] = {i: [] for i in range(1, num_zones + 1)}

        if not records:
            return result

        x_values = np.array([rec.x_value for rec in records])
        # np.digitize with right=True:
        #   returns 0 for x <= boundaries[0]
        #   returns k for boundaries[k-1] < x <= boundaries[k]
        #   returns len(boundaries) for x > boundaries[-1]
        # We add 1 to convert to 1-based zone_id.
        zones = np.digitize(x_values, boundaries, right=True)
        zone_ids = zones + 1

        for rec, zid in zip(records, zone_ids):
            result[int(zid)].append(rec)

        for zid in range(1, num_zones + 1):
            count = len(result[zid])
            if count > 0:
                logger.debug("區間 %d：%d 筆紀錄", zid, count)

        logger.info("X 值分類完成：%d 筆紀錄分至 %d 個區間", len(records), num_zones)
        return result
