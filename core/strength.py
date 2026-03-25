"""StrengthUpgrader：強度升級判定。

護級=2 且 MAX(上季贏, 上季輸) / MIN(上季贏, 上季輸) >= multiplier 時，
強度升級為 4；否則強度等於護級值。

重要：使用上季數據（非跨賽季總和，設計決策 4）。
"""

import logging

logger = logging.getLogger(__name__)


class StrengthUpgrader:
    """強度升級器。"""

    def upgrade(
        self,
        guard_level: int,
        prev_win: float,
        prev_lose: float,
        multiplier: float = 2.0,
    ) -> int:
        """判定強度值。

        Args:
            guard_level: 護級值（0~3）。
            prev_win: 上季贏類總和。
            prev_lose: 上季輸類總和。
            multiplier: 升級倍數門檻。

        Returns:
            強度值（等於護級值，或升級為 4）。
        """
        if guard_level != 2:
            return guard_level

        max_val = max(prev_win, prev_lose)
        min_val = min(prev_win, prev_lose)

        if min_val == 0.0:
            # min 為 0 且 max > 0 → 比值無限大 → 升級
            if max_val > 0.0:
                return 4
            return guard_level

        ratio = max_val / min_val
        if ratio >= multiplier:
            return 4

        return guard_level
