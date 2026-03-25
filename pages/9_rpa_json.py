"""RPA JSON 生成頁面。

功能：
- 顯示所有啟用的聯賽清單
- 生成兩種 JSON：RPA_Active.json（本季版）、RPA_Full.json（完整版）
- 提供下載按鈕

Validates: Requirements 21.1, 21.5, 21.6, 21.7
"""

import json

import streamlit as st

from app import get_store
from utils.rpa_json_generator import RpaJsonGenerator

store = get_store()

st.title("📋 RPA JSON 生成")

# ---------------------------------------------------------------------------
# 聯賽清單
# ---------------------------------------------------------------------------

leagues = store.list_leagues(active_only=True)
valid_leagues = [lg for lg in leagues if lg.league_url_id]

st.subheader(f"啟用的聯賽（{len(valid_leagues)} 個有 URL ID）")

if not valid_leagues:
    st.warning("沒有設定 League URL ID 的啟用聯賽。請先至「聯賽管理」頁面設定。")
    st.stop()

# 顯示聯賽清單
rows = []
for lg in valid_leagues:
    seasons = store.list_season_instances(lg.id)
    current = next((s for s in seasons if s.role == "current"), None)
    phase_display = lg.phase or "—"
    rows.append({
        "洲別": lg.continent,
        "代碼": lg.code,
        "名稱": lg.name_zh,
        "階段": phase_display,
        "URL ID": lg.league_url_id,
        "URL Type": lg.league_url_type,
        "本季": current.label if current else "—",
        "年份": str(current.year_start) if current else "—",
    })

st.dataframe(rows, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 生成 JSON
# ---------------------------------------------------------------------------

st.markdown("---")

generator = RpaJsonGenerator(store)

col1, col2 = st.columns(2)

with col1:
    st.subheader("本季版（Active）")
    st.caption("時段：即+早，每聯賽 2 筆（亞讓 + 總進球）")

    if st.button("生成 RPA_Active.json", key="gen_active"):
        active_data = generator.generate_active(valid_leagues)
        active_json = json.dumps(active_data, ensure_ascii=False, indent=2)

        st.success(f"已生成 {len(active_data)} 筆紀錄")
        st.json(active_data)

        st.download_button(
            "📥 下載 RPA_Active.json",
            data=active_json,
            file_name="RPA_Active.json",
            mime="application/json",
        )

with col2:
    st.subheader("完整版（Full）")
    st.caption("2 玩法 × 2 時段，每聯賽 4 筆")

    if st.button("生成 RPA_Full.json", key="gen_full"):
        full_data = generator.generate_full(valid_leagues)
        full_json = json.dumps(full_data, ensure_ascii=False, indent=2)

        st.success(f"已生成 {len(full_data)} 筆紀錄")
        st.json(full_data)

        st.download_button(
            "📥 下載 RPA_Full.json",
            data=full_json,
            file_name="RPA_Full.json",
            mime="application/json",
        )
