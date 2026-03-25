"""隊伍分組管理頁面（全域分組架構）。

功能：
- 全域分組名稱管理（新增/刪除）
- 選擇聯賽後，每個分組顯示本季/上季隊伍的編輯介面
- 支援從 Team Pool 勾選或手動輸入隊伍

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3
"""

import streamlit as st

from app import get_store

store = get_store()

st.title("👥 隊伍分組管理")

# ===========================================================================
# Section 1: 全域分組名稱管理
# ===========================================================================

st.header("全域分組名稱管理")

global_groups = store.list_global_groups()

# --- 顯示現有分組 + 刪除按鈕 ---
if global_groups:
    for gg in global_groups:
        col_name, col_display, col_del = st.columns([3, 3, 1])
        with col_name:
            st.text(f"📂 {gg.name}")
        with col_display:
            st.text(gg.display_name or "（無顯示名稱）")
        with col_del:
            if st.button("🗑️", key=f"del_gg_{gg.id}", help=f"刪除分組 {gg.name}"):
                store.delete_global_group(gg.id)
                st.success(f"已刪除分組「{gg.name}」")
                st.rerun()
else:
    st.info("尚無全域分組，請先新增。")

# --- 新增分組表單 ---
with st.form("add_global_group_form", clear_on_submit=True):
    st.subheader("➕ 新增分組")
    col_n, col_d = st.columns(2)
    with col_n:
        new_name = st.text_input("分組名稱", placeholder="例如：Top")
    with col_d:
        new_display = st.text_input("顯示名稱（選填）", placeholder="例如：強隊組")

    if st.form_submit_button("新增分組"):
        if not new_name.strip():
            st.error("請輸入分組名稱。")
        else:
            try:
                store.create_global_group(
                    name=new_name.strip(),
                    display_name=new_display.strip() or None,
                )
                st.success(f"已新增分組「{new_name.strip()}」")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

st.markdown("---")

# ===========================================================================
# Section 2: 聯賽隊伍配置
# ===========================================================================

st.header("聯賽隊伍配置")

# 重新讀取分組（可能剛新增/刪除過）
global_groups = store.list_global_groups()

if not global_groups:
    st.warning("請先在上方新增全域分組，才能配置聯賽隊伍。")
    st.stop()

leagues = store.list_leagues(active_only=False)
if not leagues:
    st.warning("尚無聯賽資料，請先至「聯賽管理」頁面新增。")
    st.stop()

league_options = {f"{lg.code} - {lg.name_zh}": lg for lg in leagues}
selected_league_key = st.selectbox("選擇聯賽", list(league_options.keys()))
league = league_options[selected_league_key]

# 取得 Team Pool
team_pool = store.get_league_team_pool(league.id)
if not team_pool:
    st.info("此聯賽尚無比賽紀錄，Team Pool 為空。可使用手動輸入方式新增隊伍。")

# --- 每個全域分組一個 expander ---
for gg in global_groups:
    display_label = gg.display_name or gg.name
    current_teams = store.get_league_group_teams(league.id, gg.id, "current")
    previous_teams = store.get_league_group_teams(league.id, gg.id, "previous")
    team_count = len(current_teams) + len(previous_teams)

    with st.expander(f"📋 {display_label}（{gg.name}）— 共 {team_count} 隊配置"):
        with st.form(f"league_group_{league.id}_{gg.id}"):
            for role, role_label in [("current", "本季隊伍"), ("previous", "上季隊伍")]:
                st.subheader(role_label)
                existing = store.get_league_group_teams(league.id, gg.id, role)

                if team_pool:
                    # multiselect 從 Team Pool 選擇
                    pool_selected = st.multiselect(
                        f"從 Team Pool 選擇（{role_label}）",
                        options=sorted(team_pool),
                        default=sorted([t for t in existing if t in team_pool]),
                        key=f"ms_{league.id}_{gg.id}_{role}",
                    )
                    # 顯示不在 pool 中的既有隊伍
                    extra = [t for t in existing if t not in team_pool]
                    if extra:
                        st.caption(f"⚠️ 以下隊伍不在 Team Pool 中：{', '.join(extra)}")
                else:
                    pool_selected = []

                # 手動輸入
                manual_default = ", ".join(
                    t for t in existing if t not in team_pool
                ) if team_pool else ", ".join(existing)
                st.text_input(
                    f"手動輸入隊伍（逗號分隔）（{role_label}）",
                    value=manual_default,
                    key=f"manual_{league.id}_{gg.id}_{role}",
                )

            if st.form_submit_button("💾 儲存"):
                changes_summary = []
                for role in ("current", "previous"):
                    pool_key = f"ms_{league.id}_{gg.id}_{role}"
                    manual_key = f"manual_{league.id}_{gg.id}_{role}"

                    final_teams: list[str] = []
                    if team_pool:
                        final_teams = list(st.session_state.get(pool_key, []))
                    manual_val = st.session_state.get(manual_key, "")
                    if manual_val.strip():
                        for t in manual_val.split(","):
                            t = t.strip()
                            if t and t not in final_teams:
                                final_teams.append(t)

                    # 差異比對
                    old_teams = set(store.get_league_group_teams(league.id, gg.id, role))
                    new_teams = set(final_teams)
                    added = new_teams - old_teams
                    removed = old_teams - new_teams
                    if added or removed:
                        role_label = "本季" if role == "current" else "上季"
                        if added:
                            changes_summary.append(f"{role_label} 新增：{', '.join(sorted(added))}")
                        if removed:
                            changes_summary.append(f"{role_label} 移除：{', '.join(sorted(removed))}")

                    store.set_league_group_teams(league.id, gg.id, role, final_teams)

                if changes_summary:
                    st.success(f"已儲存「{display_label}」— " + "；".join(changes_summary))
                else:
                    st.success(f"已儲存「{display_label}」（無變更）")
                st.rerun()
