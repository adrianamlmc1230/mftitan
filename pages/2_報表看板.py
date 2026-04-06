"""Report 看板頁面。

功能：
- 按分組名稱分頁（Top、Mid、Weak 等）
- 每個分組下列出所有聯賽的 HDP/OU × Early/RT 決策結果
- 按玩法（HDP/OU）、時段（Early/RT）篩選
- 每個聯賽區塊顯示 5 大區間的 Home/Away 訊號
- Early 和 RT 並排呈現
- 訊號顏色標記
- 點擊展開詳細統計
- 匯出 Excel

維度：分組名稱 → 聯賽 × 玩法 × 時段
"""

import io
import json

import pandas as pd
import streamlit as st

from app import get_store
from core.legacy_report import fill_template_report

store = get_store()

st.title("📊 報表看板")
st.caption("查看各聯賽的決策訊號")

# ---------------------------------------------------------------------------
# 選擇 ETL Run（預設最新）
# ---------------------------------------------------------------------------

runs = store.list_etl_runs(limit=20)
if not runs:
    st.warning("尚無 ETL 執行紀錄。請先至「RPA 檔案上傳」頁面上傳資料。")
    st.stop()

completed_runs = [r for r in runs if r["status"] == "completed"]
if not completed_runs:
    st.warning("沒有已完成的 ETL 執行紀錄。")
    st.stop()

# 預設使用最新的 completed run
run_options = {f"Run #{r['id']} — {r['completed_at']}": r["id"] for r in completed_runs}
with st.expander("🔧 切換 ETL 版本", expanded=False):
    selected_run_key = st.selectbox("選擇 ETL 版本", list(run_options.keys()))

run_id = run_options[selected_run_key]

# ---------------------------------------------------------------------------
# 取得決策結果與對照表
# ---------------------------------------------------------------------------

all_decisions = store.get_decision_results(run_id)
all_leagues = {lg.id: lg for lg in store.list_leagues(active_only=False)}

# ---------------------------------------------------------------------------
# 篩選
# ---------------------------------------------------------------------------

col_pt, col_tm, col_cont = st.columns(3)
with col_pt:
    play_filter = st.selectbox("玩法", ["全部", "HDP", "OU"])
with col_tm:
    timing_filter = st.selectbox("時段", ["全部", "Early", "RT"])
with col_cont:
    all_continents = sorted(set(lg.continent for lg in all_leagues.values() if lg.continent))
    continent_filter = st.selectbox("洲別", ["全部"] + all_continents)

# 建立 group_id → (name, display_name) 對照
_group_cache: dict[int, tuple[str, str]] = {}


def _get_group_info(group_id: int) -> tuple[str, str]:
    """回傳 (name, display_label)。name 用於跨聯賽聚合 key，display_label 用於顯示。"""
    if group_id in _group_cache:
        return _group_cache[group_id]
    row = store._conn.execute(
        "SELECT name, display_name FROM global_groups WHERE id = ?", (group_id,)
    ).fetchone()
    if row:
        name = row["name"]
        display = row["display_name"] or row["name"]
    else:
        name = f"Group#{group_id}"
        display = name
    _group_cache[group_id] = (name, display)
    return (name, display)


# ---------------------------------------------------------------------------
# 按分組名稱聚合
# ---------------------------------------------------------------------------

grouped_by_name: dict[str, list[dict]] = {}
for d in all_decisions:
    gid = d.get("global_group_id")
    if not gid:
        continue
    group_name, _ = _get_group_info(gid)
    grouped_by_name.setdefault(group_name, []).append(d)

if not grouped_by_name:
    st.info("此 ETL Run 沒有決策結果。")
    st.stop()

group_names = sorted(grouped_by_name.keys())

# ---------------------------------------------------------------------------
# 訊號顏色
# ---------------------------------------------------------------------------


def _signal_color(signal: str) -> str:
    """根據訊號回傳 CSS 顏色。"""
    if not signal:
        return ""
    letter = signal[0] if signal else ""
    try:
        val = float(signal[1:]) if len(signal) > 1 else 0
    except ValueError:
        val = 0
    if letter == "A":
        intensity = min(int(80 + val * 60), 200)
        return f"background-color: rgba(0, {intensity}, 0, 0.3)"
    elif letter == "B":
        intensity = min(int(80 + val * 60), 200)
        return f"background-color: rgba({intensity}, 0, 0, 0.3)"
    return ""


def _filter_decision(d: dict) -> bool:
    """根據篩選條件判斷是否顯示。"""
    if play_filter != "全部" and d["play_type"] != play_filter:
        return False
    if timing_filter != "全部" and d["timing"] != timing_filter:
        return False
    return True


def _render_league_signals(league_decisions: list[dict]):
    """渲染單一聯賽在某分組下的訊號表格（打直格式，分開 HDP/OU × Early/RT）。"""
    filtered = [d for d in league_decisions if _filter_decision(d)]
    if not filtered:
        return

    zone_labels = ["-50~-24%", "-23~-8%", "-7~+7%", "+8~+23%", "+24~+50%"]
    filtered.sort(key=lambda d: (d["play_type"], d["timing"]))

    for d in filtered:
        label = f"{d['play_type']}-{d['timing']}"
        rows_data = []
        for i in range(5):
            h = d["home_signals"][i] if i < len(d["home_signals"]) else ""
            a = d["away_signals"][i] if i < len(d["away_signals"]) else ""
            rows_data.append({"區間": zone_labels[i], "Home": h, "Away": a})
        st.caption(label)
        st.dataframe(pd.DataFrame(rows_data), use_container_width=True, hide_index=True)


def _render_league_detail(league_decisions: list[dict]):
    """渲染單一聯賽的詳細統計。"""
    filtered = [d for d in league_decisions if _filter_decision(d)]
    for d in filtered:
        label = f"{d['play_type']}-{d['timing']}"
        st.markdown(f"**{label} 詳細**")

        fzd = d["five_zone_data"]
        detail_rows = []
        for i, zone in enumerate(fzd):
            guard = d["guard_levels"][i] if i < len(d["guard_levels"]) else {}
            strength = d["strength_levels"][i] if i < len(d["strength_levels"]) else {}
            detail_rows.append({
                "區間": f"Zone {i + 1}",
                "上季H贏": zone.get("prev_home_win", 0),
                "上季H輸": zone.get("prev_home_lose", 0),
                "上季A贏": zone.get("prev_away_win", 0),
                "上季A輸": zone.get("prev_away_lose", 0),
                "本季H贏": zone.get("curr_home_win", 0),
                "本季H輸": zone.get("curr_home_lose", 0),
                "本季A贏": zone.get("curr_away_win", 0),
                "本季A輸": zone.get("curr_away_lose", 0),
                "H護級": guard.get("home", "") if isinstance(guard, dict) else guard,
                "A護級": guard.get("away", "") if isinstance(guard, dict) else "",
                "H強度": strength.get("home", "") if isinstance(strength, dict) else strength,
                "A強度": strength.get("away", "") if isinstance(strength, dict) else "",
                "H訊號": d["home_signals"][i],
                "A訊號": d["away_signals"][i],
            })
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 按分組名稱分頁渲染
# ---------------------------------------------------------------------------

group_tabs = st.tabs([f"📋 {name}" for name in group_names])

for tab, group_name in zip(group_tabs, group_names):
    with tab:
        decisions = grouped_by_name[group_name]

        # 按聯賽分組
        by_league: dict[int, list[dict]] = {}
        for d in decisions:
            by_league.setdefault(d["league_id"], []).append(d)

        expand_all = st.checkbox("全部展開", key=f"expand_all_{group_name}")

        for league_id, league_decisions in sorted(
            by_league.items(),
            key=lambda x: all_leagues[x[0]].code if x[0] in all_leagues else "",
        ):
            lg = all_leagues.get(league_id)
            if not lg:
                continue
            if continent_filter != "全部" and lg.continent != continent_filter:
                continue

            # Build signal summary for the expander title
            filtered_ld = [d for d in league_decisions if _filter_decision(d)]
            sig_count = sum(
                1 for d in filtered_ld
                for s in d["home_signals"] + d["away_signals"]
                if s
            )
            sig_hint = f" — {sig_count} 個訊號" if sig_count > 0 else ""

            phase_suffix = f"（{lg.phase}）" if lg.phase else ""
            with st.expander(f"🏟️ {lg.code} - {lg.name_zh}{phase_suffix}{sig_hint}", expanded=expand_all):
                _render_league_signals(league_decisions)

                if st.checkbox(
                    "顯示詳細統計",
                    key=f"detail_{group_name}_{league_id}",
                ):
                    _render_league_detail(league_decisions)

# ---------------------------------------------------------------------------
# 匯出 Excel
# ---------------------------------------------------------------------------

st.markdown("---")
if st.button("📥 匯出 Excel"):
    rows = []
    for d in all_decisions:
        lg = all_leagues.get(d["league_id"])
        if not lg:
            continue
        group_name, group_display = _get_group_info(d.get("global_group_id", 0))
        phase_suffix = f"（{lg.phase}）" if lg.phase else ""
        for i in range(5):
            rows.append({
                "分組": group_display,
                "聯賽代碼": lg.code,
                "聯賽名稱": f"{lg.name_zh}{phase_suffix}",
                "洲別": lg.continent,
                "玩法": d["play_type"],
                "時段": d["timing"],
                "區間": f"Zone {i + 1}",
                "Home訊號": d["home_signals"][i],
                "Away訊號": d["away_signals"][i],
            })

    if rows:
        df_export = pd.DataFrame(rows)
        # 按分組排序
        df_export = df_export.sort_values(["分組", "聯賽代碼", "玩法", "時段", "區間"])
        buf = io.BytesIO()
        df_export.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "下載 Excel",
            data=buf.getvalue(),
            file_name=f"report_run_{run_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("沒有資料可匯出。")

# ---------------------------------------------------------------------------
# 舊版格式匯出（模板填充方式）
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📋 舊版格式匯出")
st.caption("以舊版 Report 為模板，填入新系統的訊號。格式、樣式、聯賽順序完全保持一致。")

import os as _os

_APP_DIR = _os.path.dirname(_os.path.dirname(__file__))
# Prefer templates inside repo (works in NAS Docker after git clone)
_REPO_TPL_DIR = _os.path.join(_APP_DIR, "config", "report_templates")
# Fallback: local dev path outside repo
_LOCAL_TPL_DIR = _os.path.join(_os.path.dirname(_APP_DIR), "file", "League_Masters")

def _find_template(play_type: str) -> str | None:
    """找到模板檔案路徑，優先 repo 內，fallback 本地開發路徑。"""
    name = "讓球Report.xlsx" if play_type == "HDP" else "大小Report.xlsx"
    repo_path = _os.path.join(_REPO_TPL_DIR, name)
    if _os.path.exists(repo_path):
        return repo_path
    subdir = "讓球" if play_type == "HDP" else "大小"
    local_path = _os.path.join(_LOCAL_TPL_DIR, subdir, name)
    if _os.path.exists(local_path):
        return local_path
    return None

_HDP_TEMPLATE = _find_template("HDP")
_OU_TEMPLATE = _find_template("OU")
_has_hdp_tpl = _HDP_TEMPLATE is not None
_has_ou_tpl = _OU_TEMPLATE is not None

all_global_groups = store.list_global_groups()
if all_global_groups and all_decisions and (_has_hdp_tpl or _has_ou_tpl):
    _gg_options = {f"{gg.name}（{gg.display_name or gg.name}）": gg for gg in all_global_groups}
    selected_gg_keys = st.multiselect(
        "選擇分組（最多 2 個，依序對應報表中的第一段/第二段）",
        options=list(_gg_options.keys()),
        max_selections=2,
        default=list(_gg_options.keys())[:min(2, len(_gg_options))],
        key="legacy_export_groups",
    )

    if selected_gg_keys and st.button("📥 匯出舊版 Report", key="legacy_export_btn"):
        selected_groups = [_gg_options[k] for k in selected_gg_keys]
        sel_group_ids = [gg.id for gg in selected_groups]

        # Build league_code -> league_id mapping
        _code_to_id = {lg.code: lg.id for lg in all_leagues.values()}

        # Filter decisions for selected groups
        filtered_decisions = [
            d for d in all_decisions
            if d.get("global_group_id") in sel_group_ids
        ]

        if not filtered_decisions:
            st.warning("所選分組沒有決策結果。")
        else:
            hdp_decisions = [d for d in filtered_decisions if d["play_type"] == "HDP"]
            ou_decisions = [d for d in filtered_decisions if d["play_type"] == "OU"]

            col_hdp, col_ou = st.columns(2)

            with col_hdp:
                if _has_hdp_tpl and hdp_decisions:
                    with open(_HDP_TEMPLATE, "rb") as f:
                        tpl_bytes = f.read()
                    result = fill_template_report(tpl_bytes, hdp_decisions, _code_to_id, sel_group_ids)
                    st.download_button(
                        "📥 讓球Report.xlsx",
                        data=result,
                        file_name="讓球Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_hdp_report",
                    )
                elif not _has_hdp_tpl:
                    st.info("找不到讓球 Report 模板")
                else:
                    st.info("無 HDP 決策結果")

            with col_ou:
                if _has_ou_tpl and ou_decisions:
                    with open(_OU_TEMPLATE, "rb") as f:
                        tpl_bytes = f.read()
                    result = fill_template_report(tpl_bytes, ou_decisions, _code_to_id, sel_group_ids)
                    st.download_button(
                        "📥 大小Report.xlsx",
                        data=result,
                        file_name="大小Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_ou_report",
                    )
                elif not _has_ou_tpl:
                    st.info("找不到大小 Report 模板")
                else:
                    st.info("無 OU 決策結果")
else:
    if not all_global_groups:
        st.info("尚無全域分組。")
    elif not all_decisions:
        st.info("此 ETL Run 沒有決策結果。")
    elif not _has_hdp_tpl and not _has_ou_tpl:
        st.warning("找不到舊版 Report 模板檔案（file/League_Masters/讓球/讓球Report.xlsx 和 file/League_Masters/大小/大小Report.xlsx）")
