"""RPA 檔名解析器：從右到左剝離策略解析 RPA Excel 檔名。

檔名格式：{聯賽中文名}{賽季年份}[{階段}]{時機+玩法尾碼}.xlsx
範例：
  中國中超2025第一階段早亞讓.xlsx
  英格蘭英超2025-2026即+早亞讓.xlsx
  巴西巴甲2025早總進球.xlsx

聯賽中文名 = 年份前面的完整文字（如「澳大利亞澳超」），不拆分國家和聯賽。
"""

import re

from core.models import ParsedFilename


class FilenameParser:
    """RPA 檔名解析器。"""

    # 時機+玩法對照表（key 按長度降序排列以優先匹配較長尾碼）
    SUFFIX_MAP: dict[str, tuple[str, str]] = {
        "即+早亞讓": ("RT", "HDP"),
        "即+早總進球": ("RT", "OU"),
        "早亞讓": ("Early", "HDP"),
        "早總進球": ("Early", "OU"),
    }

    # 階段匹配模式：第N階段
    PHASE_PATTERN = re.compile(r"(第[一二三四五六七八九十\d]+階段)")

    # 賽季年份匹配：YYYY-YYYY 或 YYYY
    YEAR_PATTERN = re.compile(r"(\d{4}(?:-\d{4})?)")

    def parse(self, filename: str) -> ParsedFilename:
        """從檔名解析出結構化資訊。

        Args:
            filename: 檔案名稱（可含路徑），如 "中國中超2026第一階段早亞讓.xlsx"

        Returns:
            ParsedFilename 物件

        Raises:
            ValueError: 檔名格式不符合預期模式
        """
        import os

        basename = os.path.basename(filename)
        original_path = filename

        # Step 1: 移除 .xlsx 副檔名
        if not basename.endswith(".xlsx"):
            raise ValueError("檔名必須以 .xlsx 結尾")
        remaining = basename[: -len(".xlsx")]

        # Step 2: 從尾碼匹配 SUFFIX_MAP
        timing = ""
        play_type = ""
        suffix_matched = False
        for suffix_key, (t, pt) in self.SUFFIX_MAP.items():
            if remaining.endswith(suffix_key):
                timing = t
                play_type = pt
                remaining = remaining[: -len(suffix_key)]
                suffix_matched = True
                break

        if not suffix_matched:
            raise ValueError(f"無法識別時機與玩法尾碼：{remaining}")

        # Step 3: 從剩餘字串匹配階段（可選）
        phase = ""
        phase_match = self.PHASE_PATTERN.search(remaining)
        if phase_match:
            phase = phase_match.group(1)
            remaining = remaining[: phase_match.start()] + remaining[phase_match.end() :]

        # Step 4: 從剩餘字串匹配賽季年份
        year_match = self.YEAR_PATTERN.search(remaining)
        if not year_match:
            raise ValueError("無法識別賽季年份")
        season_year = year_match.group(1)
        remaining = remaining[: year_match.start()] + remaining[year_match.end() :]

        # Step 5: 剩餘文字就是聯賽中文名（不拆分國家和聯賽）
        name_zh = remaining.strip()
        if not name_zh:
            raise ValueError("無法識別聯賽名稱：（空字串）")

        return ParsedFilename(
            name_zh=name_zh,
            season_year=season_year,
            phase=phase,
            timing=timing,
            play_type=play_type,
            original_path=original_path,
        )

    def reconstruct(self, parsed: ParsedFilename) -> str:
        """從 ParsedFilename 還原為檔名（不含副檔名）。"""
        suffix_key = ""
        for key, (t, pt) in self.SUFFIX_MAP.items():
            if t == parsed.timing and pt == parsed.play_type:
                suffix_key = key
                break

        phase_part = parsed.phase if parsed.phase else ""
        return f"{parsed.name_zh}{parsed.season_year}{phase_part}{suffix_key}"
