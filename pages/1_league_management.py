"""聯賽管理頁面。

功能：
- 表格顯示所有聯賽（洲別、代碼、國家、名稱、階段、啟用狀態）
- 按洲別篩選
- 新增/編輯/停用/刪除聯賽
- 已移除 Directory.xlsx 匯入（改由 RPA 檔案批量上傳自動建立）

Validates: Requirements 7.1, 7.2, 7.3, 10.1
"""

import streamlit as st

from app import get_store

store = get_store()


def _show_league_table(continent_filter: str | None):
    """顯示聯賽表格。"""
    leagues = store.list_leagues(continent=continent_filter, active_only=False)
    if not leagues:
        st.info("目前沒有聯賽資料。")
        return

    rows = []
    for lg in leagues:
        seasons = store.list_season_instances(lg.id)
        current = next((s for s in seasons if s.role == "current"), None)
        previous = next((s for s in seasons if s.role == "previous"), None)
        rows.append({
            "ID": lg.id,
            "洲別": lg.continent,
            "代碼": lg.code,
            "名稱": lg.name_zh,
            "階段": lg.phase or "—",
            "URL ID": lg.league_url_id or "",
            "URL Type": lg.league_url_type or "",
            "啟用": "✅" if lg.is_active else "❌",
            "本季": current.label if current else "—",
            "上季": previous.label if previous else "—",
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


def _add_league_form():
    """新增聯賽表單。"""
    with st.expander("➕ 新增聯賽"):
        with st.form("add_league_form"):
            c1, c2 = st.columns(2)
            with c1:
                continent = st.selectbox("洲別", ["ASI", "EUR", "AME", "AFR", ""])
                code = st.text_input("聯賽代碼", placeholder="ENG1")
                name_zh = st.text_input("中文名稱", placeholder="英格蘭英超")
            with c2:
                phase = st.text_input("階段（選填）", placeholder="第一階段")
                url_id = st.text_input("League URL ID", placeholder="36")
                url_type = st.selectbox("URL Type", ["League", "SubLeague"])

            if st.form_submit_button("新增"):
                if not code or not name_zh:
                    st.error("代碼、名稱為必填")
                else:
                    try:
                        store.create_league(
                            continent=continent, code=code,
                            name_zh=name_zh,
                            phase=phase.strip() or None,
                            league_url_id=url_id or None,
                            league_url_type=url_type,
                        )
                        st.success(f"已新增聯賽 {code}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗：{e}")


def _edit_league_section():
    """編輯/停用/刪除聯賽。"""
    with st.expander("✏️ 編輯聯賽"):
        leagues = store.list_leagues(active_only=False)
        if not leagues:
            st.info("沒有聯賽可編輯")
            return

        options = {f"{lg.code} - {lg.name_zh}": lg for lg in leagues}
        selected = st.selectbox("選擇聯賽", list(options.keys()), key="edit_league_sel")
        lg = options[selected]

        with st.form("edit_league_form"):
            c1, c2 = st.columns(2)
            continent_options = ["", "ASI", "EUR", "AME", "AFR"]
            continent_idx = continent_options.index(lg.continent) if lg.continent in continent_options else 0
            with c1:
                new_continent = st.selectbox("洲別", continent_options, index=continent_idx, key="edit_continent")
                new_name = st.text_input("中文名稱", value=lg.name_zh)
                new_phase = st.text_input("階段", value=lg.phase or "")
                new_active = st.checkbox("啟用", value=lg.is_active)
            with c2:
                new_url_id = st.text_input("URL ID", value=lg.league_url_id or "")
                new_url_type = st.selectbox(
                    "URL Type",
                    ["League", "SubLeague"],
                    index=0 if lg.league_url_type == "League" else 1,
                )

            col_save, col_del = st.columns(2)
            with col_save:
                if st.form_submit_button("儲存變更"):
                    store.update_league(
                        lg.id,
                        continent=new_continent,
                        name_zh=new_name,
                        phase=new_phase.strip() or None,
                        is_active=1 if new_active else 0,
                        league_url_id=new_url_id or None,
                        league_url_type=new_url_type,
                    )
                    st.success("已更新")
                    st.rerun()

        if st.button(f"🗑️ 刪除 {lg.code}（含所有關聯資料）", key="btn_del_league"):
            store.delete_league(lg.id)
            st.success(f"已刪除 {lg.code}")
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

st.title("🏆 聯賽管理")

# 洲別篩選
filter_options = ["全部", "ASI", "EUR", "AME", "AFR"]
selected_filter = st.selectbox("篩選洲別", filter_options)
continent_filter = None if selected_filter == "全部" else selected_filter

_show_league_table(continent_filter)

st.markdown("---")
_add_league_form()
_edit_league_section()
