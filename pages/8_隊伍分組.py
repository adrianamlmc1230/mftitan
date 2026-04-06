"""隊伍分組管理頁面（全域分組架構）。

佈局：本賽季/上賽季 tab → 洲別 tab → 聯賽列表，各分組並排顯示。
"""

import io
import json

import pandas as pd
import streamlit as st

from app import get_store
from core.mismatch_detector import (
    FixAction,
    MismatchEntry,
    apply_fixes,
    detect_mismatches,
    validate_fixes,
)

store = get_store()

# Remove multiselect height limit so all selected items are visible without scrolling
st.markdown("""
<style>
    div[data-baseweb="select"] > div {
        max-height: none !important;
        overflow: visible !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("👥 隊伍分組")
st.caption("管理全域分組和各聯賽的隊伍配置")

# ===========================================================================
# Section 1: 全域分組名稱管理（收合）
# ===========================================================================

with st.expander("⚙️ 全域分組名稱管理", expanded=False):
    global_groups = store.list_global_groups()

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

    with st.form("add_global_group_form", clear_on_submit=True):
        col_n, col_d = st.columns(2)
        with col_n:
            new_name = st.text_input("分組名稱", placeholder="例如：Top")
        with col_d:
            new_display = st.text_input("顯示名稱（選填）", placeholder="例如：強隊組")
        if st.form_submit_button("➕ 新增分組"):
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

# Reload after possible changes
global_groups = store.list_global_groups()
if not global_groups:
    st.warning("請先新增全域分組。")
    st.stop()

leagues = store.list_leagues(active_only=False)
if not leagues:
    st.warning("尚無聯賽資料。")
    st.stop()

# ===========================================================================
# Section 2: 隊名不一致偵測（收合）
# ===========================================================================

group_lookup = {gg.id: gg for gg in global_groups}

with st.expander("⚠️ 隊名不一致偵測", expanded=False):
    all_mismatches: list[MismatchEntry] = []
    _league_ctx: dict[int, tuple[set[str], list]] = {}

    for lg in leagues:
        pool = store.get_league_team_pool(lg.id)
        if not pool:
            continue
        pool_set = set(pool)
        lgt = store.get_all_league_group_teams(lg.id)
        if not lgt:
            continue
        league_label = f"{lg.code} - {lg.name_zh}"
        ms = detect_mismatches(lgt, pool_set, group_lookup, lg.id, league_label)
        if ms:
            all_mismatches.extend(ms)
            _league_ctx[lg.id] = (pool_set, lgt)

    if not all_mismatches:
        st.success("✅ 所有聯賽的隊名均存在於各自的 Team Pool 中")
    else:
        st.markdown(f"共 {len(all_mismatches)} 筆不一致，涉及 {len(_league_ctx)} 個聯賽")

        if "mismatch_fixes" not in st.session_state:
            st.session_state["mismatch_fixes"] = {}

        _by_league: dict[int, list[MismatchEntry]] = {}
        for m in all_mismatches:
            _by_league.setdefault(m.league_id, []).append(m)

        for lid, entries in _by_league.items():
            pool_set, _ = _league_ctx[lid]
            sorted_pool = sorted(pool_set)
            league_label = entries[0].league_name
            st.markdown(f"**{league_label}**")

            for idx, entry in enumerate(entries):
                role_label = "本季" if entry.role == "current" else "上季"
                display_name = entry.group_display_name or entry.group_name
                col_info, col_action, col_target = st.columns([3, 2, 3])
                with col_info:
                    st.markdown(f"{display_name} · {role_label} · `{entry.team_name}`")
                fix_key = f"fix_{lid}_{entry.global_group_id}_{entry.role}_{idx}"
                delete_key = f"del_{lid}_{entry.global_group_id}_{entry.role}_{idx}"
                with col_action:
                    do_delete = st.checkbox("刪除", key=delete_key)
                with col_target:
                    replace_team = st.selectbox(
                        "替換為", options=["（不替換）"] + sorted_pool,
                        key=fix_key, disabled=do_delete, label_visibility="collapsed",
                    )
                state_key = f"mismatch_action_{lid}_{entry.global_group_id}_{entry.role}_{entry.team_name}"
                if do_delete:
                    st.session_state["mismatch_fixes"][state_key] = FixAction(
                        league_id=lid, group_name=entry.group_name,
                        global_group_id=entry.global_group_id, role=entry.role,
                        old_team=entry.team_name, action="delete", new_team=None,
                    )
                elif replace_team != "（不替換）":
                    st.session_state["mismatch_fixes"][state_key] = FixAction(
                        league_id=lid, group_name=entry.group_name,
                        global_group_id=entry.global_group_id, role=entry.role,
                        old_team=entry.team_name, action="replace", new_team=replace_team,
                    )
                else:
                    st.session_state["mismatch_fixes"].pop(state_key, None)

        pending = st.session_state.get("mismatch_fixes", {})
        if pending:
            st.caption(f"已選擇 {len(pending)} 筆修正操作")
            if st.button("🔧 一鍵套用全部修正", type="primary", key="apply_all_fixes"):
                fixes = list(pending.values())
                all_errors: list[str] = []
                for lid, (_, lgt) in _league_ctx.items():
                    league_fixes = [f for f in fixes if f.league_id == lid]
                    if league_fixes:
                        errs = validate_fixes(league_fixes, lgt)
                        all_errors.extend(errs)
                if all_errors:
                    for err in all_errors:
                        st.error(err)
                else:
                    try:
                        for lid in {f.league_id for f in fixes}:
                            league_fixes = [f for f in fixes if f.league_id == lid]
                            apply_fixes(store, lid, league_fixes)
                        st.success(f"✅ 已套用 {len(fixes)} 筆修正")
                        st.session_state.pop("mismatch_fixes", None)
                        st.rerun()
                    except RuntimeError as exc:
                        st.error(f"修正失敗：{exc}")

st.markdown("---")

# ===========================================================================
# Section 3: 本賽季 / 上賽季 → 洲別 → 聯賽並排編輯
# ===========================================================================

st.header("聯賽隊伍配置")

# Group leagues by continent
_by_continent: dict[str, list] = {}
for lg in leagues:
    cont = lg.continent or "OTHER"
    _by_continent.setdefault(cont, []).append(lg)
for cont in _by_continent:
    _by_continent[cont].sort(key=lambda x: x.code)

continent_order = sorted(_by_continent.keys())
continent_labels = {
    "ASI": "🌏 亞洲", "EUR": "🌍 歐洲", "AME": "🌎 美洲",
    "AFR": "🌍 非洲", "OTHER": "🔹 其他",
}

# Pre-build team pool cache
_pool_cache: dict[int, list[str]] = {}
def _get_pool(league_id: int) -> list[str]:
    if league_id not in _pool_cache:
        _pool_cache[league_id] = store.get_league_team_pool(league_id)
    return _pool_cache[league_id]


def _save_league_group(league_id: int, gg_id: int, role: str, key_prefix: str, pool: list[str]):
    """Collect multiselect + manual input and save."""
    pool_key = f"{key_prefix}_ms"
    manual_key = f"{key_prefix}_manual"

    final_teams: list[str] = []
    if pool:
        final_teams = list(st.session_state.get(pool_key, []))
    manual_val = st.session_state.get(manual_key, "")
    if manual_val and manual_val.strip():
        for t in manual_val.split(","):
            t = t.strip()
            if t and t not in final_teams:
                final_teams.append(t)

    store.set_league_group_teams(league_id, gg_id, role, final_teams)
    return final_teams


def _render_league_row(lg, role: str, gg_list):
    """Render one league row with all groups side-by-side."""
    pool = _get_pool(lg.id)
    sorted_pool = sorted(pool) if pool else []

    # Build columns: one per group
    cols = st.columns(len(gg_list))

    for col, gg in zip(cols, gg_list):
        with col:
            existing = store.get_league_group_teams(lg.id, gg.id, role)
            key_prefix = f"grp_{lg.id}_{gg.id}_{role}"

            if sorted_pool:
                st.multiselect(
                    f"{gg.display_name or gg.name}",
                    options=sorted_pool,
                    default=sorted([t for t in existing if t in pool]),
                    key=f"{key_prefix}_ms",
                    label_visibility="collapsed",
                )
                extra = [t for t in existing if t not in pool]
                manual_default = ", ".join(extra) if extra else ""
            else:
                manual_default = ", ".join(existing)

            st.text_input(
                "手動輸入",
                value=manual_default,
                key=f"{key_prefix}_manual",
                label_visibility="collapsed",
                placeholder="手動輸入（逗號分隔）",
            )


# Role tabs
role_tab_current, role_tab_previous = st.tabs(["📅 本賽季 (current)", "📅 上賽季 (previous)"])

for role_tab, role, role_label in [
    (role_tab_current, "current", "本賽季"),
    (role_tab_previous, "previous", "上賽季"),
]:
    with role_tab:
        # Continent tabs
        cont_tabs = st.tabs([continent_labels.get(c, c) for c in continent_order])

        for cont_tab, cont in zip(cont_tabs, continent_order):
            with cont_tab:
                cont_leagues = _by_continent[cont]
                n_groups = len(global_groups)

                # Build HTML table for display-mode leagues, interleave with edit-mode widgets
                # First, collect all non-editing leagues for the HTML table
                display_leagues = []
                edit_leagues = []
                for lg in cont_leagues:
                    edit_key = f"editing_{lg.id}_{role}"
                    if st.session_state.get(edit_key, False):
                        edit_leagues.append(lg)
                    else:
                        display_leagues.append(lg)

                # Render HTML table for display-mode leagues
                if display_leagues:
                    def _team_cell(teams: list[str], count: int) -> str:
                        """Render a cell with team names and gradient background."""
                        if not teams:
                            return '<td style="padding:6px 10px;color:#666;">—</td>'
                        # Gradient: more teams = slightly deeper background
                        alpha = min(count * 0.02, 0.25)
                        bg = f"rgba(100, 149, 237, {alpha:.2f})"
                        items = "".join(f"<div style='padding:1px 0;'>{t}</div>" for t in teams)
                        return f'<td style="padding:6px 10px;background:{bg};border-radius:4px;">{items}</td>'

                    html_parts = [
                        "<table style='width:100%;border-collapse:collapse;font-size:14px;'>",
                        "<thead><tr style='border-bottom:2px solid #444;'>",
                        "<th style='text-align:left;padding:8px 10px;width:25%;'>聯賽</th>",
                    ]
                    for gg in global_groups:
                        html_parts.append(f"<th style='text-align:left;padding:8px 10px;'>{gg.display_name or gg.name}</th>")
                    html_parts.append("<th style='width:40px;'></th>")
                    html_parts.append("</tr></thead><tbody>")

                    for row_i, lg in enumerate(display_leagues):
                        pool = _get_pool(lg.id)
                        row_bg = "rgba(255,255,255,0.03)" if row_i % 2 == 0 else "rgba(255,255,255,0.07)"
                        html_parts.append(f"<tr style='border-bottom:1px solid #333;background:{row_bg};'>")
                        pool_hint = f" <span style='color:#888;font-size:12px;'>({len(pool)})</span>" if pool else ""
                        html_parts.append(f"<td style='padding:6px 10px;font-weight:600;'>{lg.code} {lg.name_zh}{pool_hint}</td>")

                        for gg in global_groups:
                            teams = store.get_league_group_teams(lg.id, gg.id, role)
                            html_parts.append(_team_cell(teams, len(teams)))

                        html_parts.append(f"<td style='padding:6px 4px;text-align:center;'></td>")
                        html_parts.append("</tr>")

                        # Check collisions
                        _gtm: dict[str, list[str]] = {}
                        for gg in global_groups:
                            for t in store.get_league_group_teams(lg.id, gg.id, role):
                                _gtm.setdefault(t, []).append(gg.display_name or gg.name)
                        collisions = {t: gs for t, gs in _gtm.items() if len(gs) > 1}
                        if collisions:
                            n_cols = n_groups + 2
                            parts_c = [f"<b>{t}</b> → {', '.join(gs)}" for t, gs in sorted(collisions.items())]
                            html_parts.append(
                                f"<tr><td colspan='{n_cols}' style='padding:4px 10px;color:#f0ad4e;font-size:12px;'>"
                                f"⚡ 隊伍碰撞：{'；'.join(parts_c)}</td></tr>"
                            )

                    html_parts.append("</tbody></table>")
                    st.markdown("".join(html_parts), unsafe_allow_html=True)

                    # Edit buttons (need to be Streamlit widgets, rendered after the table)
                    edit_btn_cols = st.columns(len(display_leagues))
                    for i, lg in enumerate(display_leagues):
                        with edit_btn_cols[i] if len(display_leagues) <= 8 else st.container():
                            pass  # handled below

                    # Render edit buttons in a compact row
                    btn_cols = st.columns(min(len(display_leagues), 6))
                    for i, lg in enumerate(display_leagues):
                        col_idx = i % min(len(display_leagues), 6)
                        with btn_cols[col_idx]:
                            if st.button(f"✏️ {lg.code}", key=f"edit_btn_{lg.id}_{role}", help=f"編輯 {lg.code}"):
                                st.session_state[f"editing_{lg.id}_{role}"] = True
                                st.rerun()

                # Render edit-mode leagues with multiselect widgets
                for lg in edit_leagues:
                    pool = _get_pool(lg.id)
                    sorted_pool = sorted(pool) if pool else []

                    st.markdown(f"---")
                    edit_header = st.columns([3] + [4] * n_groups + [1])
                    with edit_header[0]:
                        st.markdown(f"**✏️ {lg.code}** {lg.name_zh}")

                    for gi, gg in enumerate(global_groups):
                        with edit_header[gi + 1]:
                            existing = store.get_league_group_teams(lg.id, gg.id, role)
                            key_prefix = f"grp_{lg.id}_{gg.id}_{role}"
                            if sorted_pool:
                                st.multiselect(
                                    f"{gg.name}",
                                    options=sorted_pool,
                                    default=sorted([t for t in existing if t in pool]),
                                    key=f"{key_prefix}_ms",
                                    label_visibility="collapsed",
                                )
                                extra = [t for t in existing if t not in pool]
                                if extra:
                                    st.caption(f"+{', '.join(extra)}")
                            else:
                                st.text_input(
                                    f"{gg.name}",
                                    value=", ".join(existing),
                                    key=f"{key_prefix}_manual",
                                    label_visibility="collapsed",
                                    placeholder="逗號分隔",
                                )

                    with edit_header[-1]:
                        if st.button("💾", key=f"save_btn_{lg.id}_{role}", help="儲存"):
                            for gg in global_groups:
                                key_prefix = f"grp_{lg.id}_{gg.id}_{role}"
                                _save_league_group(lg.id, gg.id, role, key_prefix, pool)
                            st.session_state[f"editing_{lg.id}_{role}"] = False
                            st.rerun()

                    # Collision detection for editing league
                    _group_teams_map: dict[str, list[str]] = {}
                    for gg in global_groups:
                        key_prefix = f"grp_{lg.id}_{gg.id}_{role}"
                        teams_in_group: set[str] = set()
                        ms_val = st.session_state.get(f"{key_prefix}_ms")
                        if ms_val:
                            teams_in_group.update(ms_val)
                        manual_val = st.session_state.get(f"{key_prefix}_manual", "")
                        if manual_val and manual_val.strip():
                            for t in manual_val.split(","):
                                t = t.strip()
                                if t:
                                    teams_in_group.add(t)
                        if not teams_in_group:
                            existing_db = store.get_league_group_teams(lg.id, gg.id, role)
                            teams_in_group.update(existing_db)
                        for t in teams_in_group:
                            _group_teams_map.setdefault(t, []).append(gg.display_name or gg.name)

                    collisions = {t: gs for t, gs in _group_teams_map.items() if len(gs) > 1}
                    if collisions:
                        parts = [f"`{t}` → {', '.join(gs)}" for t, gs in sorted(collisions.items())]
                        st.warning(f"⚡ 隊伍碰撞：{'；'.join(parts)}")

                # (Individual save buttons are per-league row above)

st.markdown("---")

# ===========================================================================
# Section 4: 匯入/匯出分組配置
# ===========================================================================

with st.expander("📦 匯入/匯出分組配置", expanded=False):
    col_export, col_import = st.columns(2)

    with col_export:
        st.markdown("**📤 匯出**")
        if st.button("匯出全部配置"):
            all_leagues_list = store.list_leagues(active_only=False)
            global_groups_list = store.list_global_groups()
            rows = []
            for lg_item in all_leagues_list:
                for gg in global_groups_list:
                    for r in ("current", "previous"):
                        teams = store.get_league_group_teams(lg_item.id, gg.id, r)
                        if teams:
                            rows.append({
                                "聯賽代碼": lg_item.code,
                                "聯賽名稱": lg_item.name_zh,
                                "分組": gg.name,
                                "角色": r,
                                "隊伍": ", ".join(teams),
                            })
            if rows:
                df_export = pd.DataFrame(rows)
                buf = io.BytesIO()
                df_export.to_excel(buf, index=False, engine="openpyxl")
                st.download_button(
                    "📥 下載 Excel",
                    data=buf.getvalue(),
                    file_name="team_group_config.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success(f"已生成 {len(rows)} 筆配置")
            else:
                st.info("沒有配置可匯出")

    with col_import:
        st.markdown("**📥 匯入**")
        uploaded = st.file_uploader("上傳配置 Excel", type=["xlsx"], key="import_config")
        if uploaded:
            try:
                df_import = pd.read_excel(uploaded, engine="openpyxl")
                required_cols = {"聯賽代碼", "分組", "角色", "隊伍"}
                if not required_cols.issubset(set(df_import.columns)):
                    st.error(f"缺少必要欄位：{required_cols - set(df_import.columns)}")
                else:
                    st.dataframe(df_import, use_container_width=True, hide_index=True)
                    if st.button("確認匯入", type="primary"):
                        all_leagues_map = {lg_item.code: lg_item for lg_item in store.list_leagues(active_only=False)}
                        all_groups_map = {gg.name: gg for gg in store.list_global_groups()}
                        imported = 0
                        errors = []
                        for _, row in df_import.iterrows():
                            code = str(row["聯賽代碼"]).strip()
                            group_name = str(row["分組"]).strip()
                            r = str(row["角色"]).strip()
                            teams_str = str(row["隊伍"]).strip() if pd.notna(row["隊伍"]) else ""
                            teams = [t.strip() for t in teams_str.split(",") if t.strip()] if teams_str else []
                            lg_item = all_leagues_map.get(code)
                            gg = all_groups_map.get(group_name)
                            if not lg_item:
                                errors.append(f"聯賽 {code} 不存在")
                                continue
                            if not gg:
                                errors.append(f"分組 {group_name} 不存在")
                                continue
                            if r not in ("current", "previous"):
                                errors.append(f"角色 {r} 無效")
                                continue
                            store.set_league_group_teams(lg_item.id, gg.id, r, teams)
                            imported += 1
                        store.log_action("import", "team_group_config", details=f"匯入 {imported} 筆")
                        if errors:
                            st.warning(f"匯入完成：{imported} 筆成功，{len(errors)} 筆錯誤")
                            for e in errors[:10]:
                                st.caption(f"⚠️ {e}")
                        else:
                            st.success(f"匯入完成：{imported} 筆")
                        st.rerun()
            except Exception as e:
                st.error(f"讀取失敗：{e}")
