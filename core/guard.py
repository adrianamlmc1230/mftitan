"""GuardLevelEvaluator：護級判定（0~3）。

護級邏輯（設計決策 3）：
  0 = 上季走水（prev_win == prev_lose，含兩者皆為 0）
  1 = 本季走水（curr_win == curr_lose）且上季非走水
  2 = 方向一致（上季與本季的贏/輸優勢方向相同）
  3 = 方向逆轉（上季與本季的贏/輸優勢方向相反）

每個 Five_Zone 的 Home 和 Away 方向分別判定。
"""

import logging

logger = logging.getLogger(__name__)


class GuardLevelEvaluator:
    """護級判定器。"""

    def evaluate(
        self,
        prev_win: float,
        prev_lose: float,
        curr_win: float,
        curr_lose: float,
    ) -> int:
        """判定護級 0~3。

        Args:
            prev_win: 上季贏類總和。
            prev_lose: 上季輸類總和。
            curr_win: 本季贏類總和。
            curr_lose: 本季輸類總和。

        Returns:
            護級值 0~3。
        """
        # 護級 0：上季贏 == 上季輸（含兩者皆為 0）
        if prev_win == prev_lose:
            return 0

        # 護級 1：本季贏 == 本季輸，且上季非走水
        if curr_win == curr_lose:
            return 1

        # 判斷方向：贏 > 輸 → "win"，輸 > 贏 → "lose"
        prev_dir = "win" if prev_win > prev_lose else "lose"
        curr_dir = "win" if curr_win > curr_lose else "lose"

        # 護級 2：方向一致
        if prev_dir == curr_dir:
            return 2

        # 護級 3：方向逆轉
        return 3
