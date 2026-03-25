"""SignalGenerator：決策訊號產生。

訊號格式：方向字母 + 數值，例如 'A2', 'B0.5', ''。

方向判定（固定邏輯）：
  Home 方向（direction_logic='greater'）：上季贏 > 輸 → A，上季輸 > 贏 → B
  Away 方向（direction_logic='less'）：上季贏 < 輸 → A，上季輸 < 贏 → B

注意：direction_logic 不是 per-group 設定，而是固定的 Home/Away 方向邏輯。
Pipeline 呼叫時，Home 方向固定傳 'greater'，Away 方向固定傳 'less'。

訊號值：
  strength=4         → 2
  guard=2 且 ratio > threshold → 1
  guard=2 且 ratio ≤ threshold → 0.5
  guard=1            → 0.2
  guard=0 或 3       → '' (空字串)
"""

import logging

logger = logging.getLogger(__name__)


class SignalGenerator:
    """決策訊號產生器。"""

    def generate(
        self,
        guard: int,
        strength: int,
        prev_win: float,
        prev_lose: float,
        ratio_threshold: float = 1.4,
        direction_logic: str = "greater",
    ) -> str:
        """產生訊號字串。

        Args:
            guard: 護級值（0~3）。
            strength: 強度值。
            prev_win: 上季贏類總和（用於方向判定）。
            prev_lose: 上季輸類總和（用於方向判定）。
            ratio_threshold: 贏輸比值門檻。
            direction_logic: 'greater'（Home 方向）或 'less'（Away 方向）。

        Returns:
            訊號字串，如 'A2', 'B0.5', ''。
        """
        # 護級 0 或 3 → 空白訊號
        if guard in (0, 3):
            return ""

        # 方向字母判定
        if direction_logic == "greater":
            # Home 方向：贏 > 輸 → A，輸 > 贏 → B
            letter = "A" if prev_win > prev_lose else "B"
        else:
            # Away 方向：贏 < 輸 → A，輸 < 贏 → B
            letter = "A" if prev_win < prev_lose else "B"

        # 訊號數值判定
        if strength == 4:
            value = 2
        elif guard == 2:
            max_val = max(prev_win, prev_lose)
            min_val = min(prev_win, prev_lose)
            ratio = max_val / min_val if min_val > 0 else float("inf")
            value = 1 if ratio > ratio_threshold else 0.5
        elif guard == 1:
            value = 0.2
        else:
            return ""

        # 格式化：整數不帶小數點
        if value == int(value):
            return f"{letter}{int(value)}"
        return f"{letter}{value}"
