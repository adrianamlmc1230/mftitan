"""Excel I/O 工具：讀取 RPA 原始 xlsx、匯出計算結果與 Report。"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def read_rpa_excel(filepath: str) -> pd.DataFrame:
    """讀取 RPA 原始 xlsx 檔案。

    Args:
        filepath: xlsx 檔案路徑。

    Returns:
        DataFrame（header=None），錯誤時回傳空 DataFrame。
    """
    path = Path(filepath)
    if not path.exists():
        logger.error("檔案不存在：%s", filepath)
        return pd.DataFrame()
    try:
        return pd.read_excel(filepath, engine="openpyxl", header=None)
    except Exception as exc:
        logger.error("讀取失敗 (%s)：%s", filepath, exc)
        return pd.DataFrame()


def export_results_to_excel(results: list[dict], filepath: str) -> None:
    """將計算結果匯出為 Excel。

    Args:
        results: computation_results 列表（dict 格式）。
        filepath: 輸出檔案路徑。
    """
    rows = []
    for r in results:
        zone_data = json.loads(r.get("zone_data", "[]"))
        for z in zone_data:
            rows.append({
                "league_id": r.get("league_id"),
                "season_instance_id": r.get("season_instance_id"),
                "team_group_id": r.get("team_group_id"),
                "play_type": r.get("play_type"),
                "timing": r.get("timing"),
                "zone_id": z.get("zone_id"),
                "win": z.get("win", 0),
                "lose": z.get("lose", 0),
            })

    df = pd.DataFrame(rows)
    df.to_excel(filepath, index=False, engine="openpyxl")
    logger.info("計算結果已匯出：%s（%d 列）", filepath, len(rows))


def export_report_to_excel(report_data: list[dict], filepath: str) -> None:
    """將 Report 看板匯出為 Excel（與舊 Report.xlsx 相容格式）。

    Args:
        report_data: decision_results 列表（dict 格式）。
        filepath: 輸出檔案路徑。
    """
    rows = []
    for r in report_data:
        signals = json.loads(r.get("signals", "[]"))
        guard_levels = json.loads(r.get("guard_levels", "[]"))
        five_zone_data = json.loads(r.get("five_zone_data", "[]"))

        row = {
            "league_id": r.get("league_id"),
            "team_group_id": r.get("team_group_id"),
            "play_type": r.get("play_type"),
            "timing": r.get("timing"),
        }
        for i in range(5):
            zi = i + 1
            row[f"Z{zi}_signal"] = signals[i] if i < len(signals) else ""
            row[f"Z{zi}_guard"] = guard_levels[i] if i < len(guard_levels) else 0
            if i < len(five_zone_data):
                fz = five_zone_data[i]
                row[f"Z{zi}_prev_win"] = fz.get("prev_win", 0)
                row[f"Z{zi}_prev_lose"] = fz.get("prev_lose", 0)
                row[f"Z{zi}_total_win"] = fz.get("total_win", 0)
                row[f"Z{zi}_total_lose"] = fz.get("total_lose", 0)
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_excel(filepath, index=False, engine="openpyxl")
    logger.info("Report 已匯出：%s（%d 列）", filepath, len(rows))
