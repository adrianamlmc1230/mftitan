"""Match_Importer：比賽資料匯入器。

負責讀取 RPA Excel 檔案、前處理、結算計算、寫入 DB。
複用現有 RawDataReader、RawDataPreprocessor、SettlementCalculator。
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field

import pandas as pd

from core.config_store import ConfigStore
from core.models import MatchRecord
from core.preprocessor import RawDataPreprocessor
from core.reader import RawDataReader
from core.settlement import SettlementCalculator

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """單一檔案匯入結果。"""

    success: bool
    records_imported: int
    records_skipped: int
    previous_count: int = 0         # DB 中原有的紀錄數
    diff: int = 0                   # 新 - 舊 的差異
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class MatchImporter:
    """比賽資料匯入器。"""

    def __init__(self, config_store: ConfigStore):
        self.store = config_store
        self.reader = RawDataReader()
        self.preprocessor = RawDataPreprocessor()
        self.settlement = SettlementCalculator()

    def import_file(
        self,
        file_content: bytes | str,
        season_instance_id: int,
        play_type: str,
        timing: str,
    ) -> ImportResult:
        """匯入單一 RPA Excel 檔案。

        流程：
        1. 讀取 Excel → DataFrame
        2. 前處理（簡繁轉換、方括號清除、數字後綴清除）
        3. 提取 MatchRecord 列表
        4. 設定 play_type → 結算計算
        5. 提取 score 與 link
        6. UPSERT 至 match_records 表（先刪後插）

        Args:
            file_content: bytes（Streamlit file_uploader）或 str（檔案路徑）。
            season_instance_id: 賽季實例 ID。
            play_type: 玩法類型（'HDP' 或 'OU'）。
            timing: 時機類型（'Early' 或 'RT'）。

        Returns:
            ImportResult 匯入結果。
        """
        warnings: list[str] = []

        # Step 1: 讀取 Excel → DataFrame
        try:
            df = self._read_file(file_content)
        except Exception as exc:
            return ImportResult(
                success=False,
                records_imported=0,
                records_skipped=0,
                error=f"檔案讀取失敗：{exc}",
            )

        if df.empty:
            return ImportResult(
                success=False,
                records_imported=0,
                records_skipped=0,
                error="檔案讀取失敗：檔案內容為空",
            )

        # Step 2: 前處理（簡繁轉換、方括號清除、數字後綴清除）
        processed_df, _stats = self.preprocessor.process(df)

        # Step 3: 提取 MatchRecord 列表
        records = self.reader.extract_records(processed_df)

        if not records:
            return ImportResult(
                success=False,
                records_imported=0,
                records_skipped=0,
                error="無有效比賽資料",
            )

        # 計算跳過的列數（metadata 列不算）
        total_data_rows = len(df) - 1  # 扣除 metadata row
        records_skipped = total_data_rows - len(records)

        if records_skipped > 0:
            warnings.append(f"跳過 {records_skipped} 列無效資料")

        # Step 4: 設定 play_type → 結算計算
        for rec in records:
            rec.play_type = play_type

        self.settlement.calculate(records)

        # Step 5: 提取 score 與 link
        self._extract_score_and_link(processed_df, records)

        # Step 5.5: 查詢 DB 中原有紀錄數量，用於差異對比
        existing_counts = self.store.get_match_record_counts(season_instance_id)
        previous_count = existing_counts.get((play_type, timing), 0)

        # Step 6: UPSERT 至 match_records 表
        try:
            count = self.store.upsert_match_records(
                season_instance_id, play_type, timing, records,
            )
        except Exception as exc:
            return ImportResult(
                success=False,
                records_imported=0,
                records_skipped=records_skipped,
                warnings=warnings,
                error=f"資料庫寫入失敗：{exc}",
            )

        diff = count - previous_count
        if diff != 0 and previous_count > 0:
            warnings.append(f"紀錄數變化：{previous_count} → {count}（{'+' if diff > 0 else ''}{diff}）")

        return ImportResult(
            success=True,
            records_imported=count,
            records_skipped=records_skipped,
            previous_count=previous_count,
            diff=diff,
            warnings=warnings,
        )

    def cross_validate_metadata(
        self,
        df: pd.DataFrame,
        parsed_name_zh: str,
    ) -> list[str]:
        """Row 1 metadata 與檔名解析結果交叉驗證。

        當不一致時記錄警告，以檔名解析結果為準。

        Args:
            df: 由 reader.read() 回傳的 DataFrame。
            parsed_name_zh: 檔名解析出的聯賽中文名。

        Returns:
            警告訊息列表。
        """
        warnings: list[str] = []

        metadata = self.reader.extract_metadata(df)
        if metadata is None:
            warnings.append("Row 1 metadata 缺失，使用檔名解析結果")
            return warnings

        # metadata 中的 country+league 合併後與 name_zh 比較
        meta_country = metadata.get("country", "")
        meta_league = metadata.get("league_name", "")
        meta_combined = f"{meta_country}{meta_league}"

        if meta_combined and meta_combined != parsed_name_zh:
            warnings.append(
                f"聯賽名不一致：檔名='{parsed_name_zh}'，Row 1='{meta_combined}'，以檔名為準"
            )
            logger.warning(
                "聯賽名不一致：檔名='%s'，Row 1='%s'，以檔名為準",
                parsed_name_zh,
                meta_combined,
            )

        return warnings

    def _read_file(self, file_content: bytes | str) -> pd.DataFrame:
        """讀取檔案內容為 DataFrame。

        Args:
            file_content: bytes（寫入暫存檔後讀取）或 str（直接作為路徑讀取）。

        Returns:
            DataFrame。
        """
        if isinstance(file_content, bytes):
            # 寫入暫存檔後使用 RawDataReader 讀取
            fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
            try:
                os.write(fd, file_content)
                os.close(fd)
                return self.reader.read(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        else:
            # str 路徑，直接讀取
            return self.reader.read(file_content)

    @staticmethod
    def _extract_score_and_link(
        df: pd.DataFrame, records: list[MatchRecord],
    ) -> None:
        """從 DataFrame 提取 score（C 欄, index 2）與 link（G 欄, index 6）。

        從 index 1 開始（跳過 metadata row），對應到 records 列表。
        """
        if df.empty or len(df) < 2:
            return

        cols = df.columns.tolist()
        has_score = len(cols) > 2
        has_link = len(cols) > 6

        # 建立有效資料列的索引映射
        record_idx = 0
        for row_idx in range(1, len(df)):
            if record_idx >= len(records):
                break

            row = df.iloc[row_idx]

            # 檢查此列是否為有效紀錄（與 extract_records 的驗證邏輯一致）
            raw_round = row.iloc[0]
            raw_home = row.iloc[1]
            raw_away = row.iloc[3] if len(cols) > 3 else None
            raw_x = row.iloc[4] if len(cols) > 4 else None

            # 驗證此列是否有效（與 reader.extract_records 一致）
            try:
                int(float(raw_round))
            except (ValueError, TypeError):
                continue

            if pd.isna(raw_home) or str(raw_home).strip() == "":
                continue

            if raw_away is None or pd.isna(raw_away) or str(raw_away).strip() == "":
                continue

            try:
                float(raw_x)
            except (ValueError, TypeError):
                continue

            # 此列有效，提取 score 與 link
            rec = records[record_idx]

            if has_score:
                raw_score = row.iloc[2]
                rec.score = "" if pd.isna(raw_score) else str(raw_score).strip()

            if has_link:
                raw_link = row.iloc[6]
                rec.link = "" if pd.isna(raw_link) else str(raw_link).strip()

            record_idx += 1
