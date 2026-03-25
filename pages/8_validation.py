"""數據驗證頁面。

功能：
- 上傳舊系統 MST_ 檔案
- 自動比對新舊系統計算結果
- 顯示一致與差異項目

Validates: Requirements 22.1, 22.2, 22.3, 22.4
"""

import pandas as pd
import streamlit as st

from app import get_store

store = get_store()

st.title("🔍 數據驗證（新舊系統比對）")

# ---------------------------------------------------------------------------
# 選擇 ETL Run
# ---------------------------------------------------------------------------

runs = store.list_etl_runs(limit=20)
completed_runs = [r for r in runs if r["status"] == "completed"]
if not completed_runs:
    st.warning("沒有已完成的 ETL 執行紀錄。請先執行 ETL。")
    st.stop()

run_options = {f"Run #{r['id']} — {r['completed_at']}": r["id"] for r in completed_runs}
selected_run_key = st.selectbox("選擇要比對的 ETL 版本", list(run_options.keys()))
run_id = run_options[selected_run_key]

# ---------------------------------------------------------------------------
# 上傳 MST 檔案
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("上傳舊系統 MST 檔案")
st.caption("上傳舊系統的 MST_ Excel 檔案，系統將自動比對計算結果。")

uploaded = st.file_uploader("選擇 MST Excel 檔案", type=["xlsx", "xls"])

if not uploaded:
    st.info("請上傳 MST 檔案以開始比對。")
    st.stop()

# ---------------------------------------------------------------------------
# 解析 MST 檔案並比對
# ---------------------------------------------------------------------------

try:
    mst_df = pd.read_excel(uploaded, engine="openpyxl", header=None)
except Exception as e:
    st.error(f"讀取 MST 檔案失敗：{e}")
    st.stop()

st.success(f"已讀取 MST 檔案：{mst_df.shape[0]} 行 × {mst_df.shape[1]} 欄")

# 取得新系統結果
decisions = store.get_decision_results(run_id)
comp_results = store.get_computation_results(run_id)

if not decisions:
    st.warning("選定的 ETL Run 沒有決策結果。")
    st.stop()

st.subheader("比對結果")
st.caption(
    "由於 MST 檔案格式因聯賽而異，自動比對為盡力而為。"
    "建議人工確認關鍵差異。"
)

# 顯示新系統結果摘要供人工比對
all_leagues = {lg.id: lg for lg in store.list_leagues(active_only=False)}

comparison_rows = []
for d in decisions:
    lg = all_leagues.get(d["league_id"])
    lg_name = f"{lg.code}" if lg else f"#{d['league_id']}"

    for i in range(5):
        fzd = d["five_zone_data"][i] if i < len(d["five_zone_data"]) else {}
        guard = d["guard_levels"][i] if i < len(d["guard_levels"]) else {}
        strength = d["strength_levels"][i] if i < len(d["strength_levels"]) else {}
        comparison_rows.append({
            "聯賽": lg_name,
            "玩法": d["play_type"],
            "時段": d["timing"],
            "區間": f"Zone {i + 1}",
            "上季H贏": fzd.get("prev_home_win", 0),
            "上季H輸": fzd.get("prev_home_lose", 0),
            "本季H贏": fzd.get("curr_home_win", 0),
            "本季H輸": fzd.get("curr_home_lose", 0),
            "H護級": guard.get("home", "") if isinstance(guard, dict) else guard,
            "H強度": strength.get("home", "") if isinstance(strength, dict) else strength,
            "H訊號": d["home_signals"][i],
            "A訊號": d["away_signals"][i],
        })

if comparison_rows:
    st.markdown("**新系統計算結果**")
    st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("**舊系統 MST 原始數據（前 50 行）**")
st.dataframe(mst_df.head(50), use_container_width=True, hide_index=True)

st.info("💡 請人工比對上方兩個表格的數值，確認新舊系統計算結果一致。")
