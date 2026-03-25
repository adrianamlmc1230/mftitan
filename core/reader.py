"""Raw_Data_Reader：從前處理後的 Excel 賠率數據檔案讀取比賽紀錄。

支援解析 Row 1 metadata 進行交叉驗證，並從 Row 2+ 提取 MatchRecord 列表。
"""

import logging
from pathlib import Path

import pandas as pd

from core.models import MatchRecord

logger = logging.getLogger(__name__)


class RawDataReader:
    """原始數據讀取器：讀取 RPA 產出的 xlsx 檔案並提取比賽紀錄。"""

    def read(self, filepath: str) -> pd.DataFrame:
        """使用 openpyxl 讀取 xlsx 檔案為 DataFrame。

        Args:
            filepath: xlsx 檔案路徑。

        Returns:
            讀取到的 DataFrame（header=None），錯誤時回傳空 DataFrame。
        """
        path = Path(filepath)
        if not path.exists():
            logger.error("檔案不存在：%s", filepath)
            return pd.DataFrame()

        try:
            df = pd.read_excel(filepath, engine="openpyxl", header=None)
        except Exception as exc:
            logger.error("讀取 xlsx 檔案失敗 (%s)：%s", filepath, exc)
            return pd.DataFrame()

        if df.empty:
            logger.warning("檔案內容為空：%s", filepath)
            return pd.DataFrame()

        return df

    def extract_metadata(self, df: pd.DataFrame) -> dict | None:
        """提取 Row 1 metadata 並進行基本驗證。

        Row 1 格式：A1=國家、B1=聯賽名、C1=賽季、D1=玩法。

        Args:
            df: 由 read() 回傳的 DataFrame。

        Returns:
            包含 country、league_name、season、play_type 的 dict，
            metadata 缺失或無效時回傳 None。
        """
        if df.empty or len(df) < 1:
            logger.warning("DataFrame 為空，無法提取 metadata")
            return None

        if len(df.columns) < 4:
            logger.warning("DataFrame 欄位不足 4 欄，無法提取 metadata")
            return None

        row = df.iloc[0]
        country = row.iloc[0]
        league_name = row.iloc[1]
        season = row.iloc[2]
        play_type = row.iloc[3]

        # 檢查是否有 NaN 或空值
        values = [country, league_name, season, play_type]
        if any(pd.isna(v) for v in values):
            logger.warning("metadata 含有空值：%s", values)
            return None

        # 轉為字串
        metadata = {
            "country": str(country).strip(),
            "league_name": str(league_name).strip(),
            "season": str(season).strip(),
            "play_type": str(play_type).strip(),
        }

        # 檢查是否有空字串
        if any(v == "" for v in metadata.values()):
            logger.warning("metadata 含有空字串：%s", metadata)
            return None

        return metadata

    def extract_records(self, df: pd.DataFrame) -> list[MatchRecord]:
        """從清理後的 DataFrame 提取 MatchRecord 列表。

        跳過 Row 1（metadata），從 Row 2（index 1）開始處理。
        欄位對應：A欄=輪次、B欄=主隊、D欄=客隊、E欄=X值、F欄=結算。

        Args:
            df: 由 read() 回傳並經前處理的 DataFrame。

        Returns:
            MatchRecord 列表，跳過無效資料列。
        """
        if df.empty:
            logger.warning("DataFrame 為空，無法提取紀錄")
            return []

        if len(df) < 2:
            logger.warning("DataFrame 只有 metadata 列，無比賽資料")
            return []

        if len(df.columns) < 6:
            logger.warning("DataFrame 欄位不足 6 欄（需要 A~F），無法提取紀錄")
            return []

        records: list[MatchRecord] = []
        skipped = 0

        # 從 index 1 開始（跳過 Row 1 metadata）
        for idx in range(1, len(df)):
            row = df.iloc[idx]

            # 提取原始值
            raw_round = row.iloc[0]
            raw_home = row.iloc[1]
            raw_away = row.iloc[3]
            raw_x = row.iloc[4]
            raw_settlement = row.iloc[5]

            # 驗證輪次：必須是有效數字
            try:
                round_num = int(float(raw_round))
            except (ValueError, TypeError):
                logger.warning("第 %d 列輪次無效（值=%s），跳過", idx + 1, raw_round)
                skipped += 1
                continue

            # 驗證主隊與客隊：不可為空
            if pd.isna(raw_home) or str(raw_home).strip() == "":
                logger.warning("第 %d 列主隊為空，跳過", idx + 1)
                skipped += 1
                continue

            if pd.isna(raw_away) or str(raw_away).strip() == "":
                logger.warning("第 %d 列客隊為空，跳過", idx + 1)
                skipped += 1
                continue

            # 驗證 X 值：必須是有效浮點數
            try:
                x_value = float(raw_x)
            except (ValueError, TypeError):
                logger.warning("第 %d 列 X 值無效（值=%s），跳過", idx + 1, raw_x)
                skipped += 1
                continue

            # 結算欄位：允許為空（某些情況下尚未結算）
            if pd.isna(raw_settlement):
                settlement = ""
            else:
                settlement = str(raw_settlement).strip()

            record = MatchRecord(
                round_num=round_num,
                home_team=str(raw_home).strip(),
                away_team=str(raw_away).strip(),
                x_value=x_value,
                settlement=settlement,
            )
            records.append(record)

        if skipped > 0:
            logger.info("共跳過 %d 列無效資料", skipped)

        logger.info("成功提取 %d 筆比賽紀錄", len(records))
        return records
