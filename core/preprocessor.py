"""原始數據前處理：簡繁轉換、方括號清除、B/D 欄數字清除。"""

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

# OpenCC fallback：嘗試匯入，不可用時設為 None
try:
    from opencc import OpenCC
    _opencc_converter = OpenCC('s2t')
except ImportError:
    _opencc_converter = None
    logger.warning("OpenCC 未安裝，簡繁轉換將僅使用內建對照表")


class RawDataPreprocessor:
    """原始數據前處理：簡繁轉換、方括號清除、B/D 欄數字清除。"""

    # 簡繁對照表（高頻字優先，OpenCC 作為 fallback）
    CHAR_MAP: dict[str, str] = {
        '赢': '贏',
        '输': '輸',
        '不适用': '不適用',
    }

    # 方括號匹配模式
    _BRACKET_PATTERN = re.compile(r'\[.*?\]')

    # 數字後綴匹配模式
    _DIGIT_SUFFIX_PATTERN = re.compile(r'\d+$')

    def process(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """
        處理 DataFrame，回傳 (清理後的 df, 統計摘要 dict)。

        統計摘要包含：
        - simplified_replaced: 簡繁轉換替換次數
        - brackets_removed: 方括號移除次數
        - digits_removed: B/D 欄數字後綴移除次數

        所有操作在 DataFrame 副本上執行，不修改原始資料。
        """
        result = df.copy()

        simplified_replaced = self._convert_simplified_to_traditional(result)
        brackets_removed = self._remove_brackets(result)
        digits_removed = self._remove_digit_suffix_bd(result)

        stats = {
            'simplified_replaced': simplified_replaced,
            'brackets_removed': brackets_removed,
            'digits_removed': digits_removed,
        }

        logger.info(
            "前處理完成：簡繁轉換 %d 筆、方括號移除 %d 筆、數字後綴移除 %d 筆",
            simplified_replaced, brackets_removed, digits_removed,
        )

        return result, stats

    def _convert_simplified_to_traditional(self, df: pd.DataFrame) -> int:
        """簡繁轉換：優先使用內建對照表，fallback 使用 OpenCC。回傳替換次數。"""
        total_replaced = 0

        # 找出所有 object（字串）型別的欄位
        str_cols = df.select_dtypes(include=['object']).columns

        # 第一步：使用內建對照表進行高頻字替換
        for old, new in self.CHAR_MAP.items():
            for col in str_cols:
                mask = df[col].astype(str).str.contains(old, na=False, regex=False)
                count = mask.sum()
                if count > 0:
                    df[col] = df[col].astype(str).str.replace(old, new, regex=False)
                    total_replaced += count

        # 第二步：OpenCC fallback（處理內建對照表未涵蓋的簡體字）
        if _opencc_converter is not None:
            for col in str_cols:
                before = df[col].astype(str)
                after = before.apply(
                    lambda x: _opencc_converter.convert(x) if isinstance(x, str) and x != 'nan' else x
                )
                diff_mask = before != after
                count = diff_mask.sum()
                if count > 0:
                    df[col] = after
                    total_replaced += count

        return total_replaced

    def _remove_brackets(self, df: pd.DataFrame) -> int:
        """移除所有方括號標記 [任意內容]。回傳移除次數。"""
        total_removed = 0

        str_cols = df.select_dtypes(include=['object']).columns

        for col in str_cols:
            series = df[col].astype(str)
            # 計算含有方括號的儲存格數量
            mask = series.str.contains(r'\[.*?\]', na=False, regex=True)
            count = mask.sum()
            if count > 0:
                df[col] = series.str.replace(r'\[.*?\]', '', regex=True)
                total_removed += count

        return total_removed

    def _remove_digit_suffix_bd(self, df: pd.DataFrame) -> int:
        """移除 B 欄與 D 欄中的數字後綴。回傳移除次數。

        B/D 欄為 0-indexed 的 column 1 和 column 3。
        DataFrame 的欄位可能是位置索引（0,1,2,3,...）或名稱。
        """
        total_removed = 0

        # 取得 B 欄（index 1）和 D 欄（index 3）
        cols = df.columns.tolist()
        target_indices = [1, 3]

        for idx in target_indices:
            if idx >= len(cols):
                continue

            col = cols[idx]
            series = df[col].astype(str)

            # 計算含有數字後綴的儲存格數量
            mask = series.str.contains(r'\d+$', na=False, regex=True)
            count = mask.sum()
            if count > 0:
                df[col] = series.str.replace(r'\d+$', '', regex=True)
                total_removed += count

        return total_removed
