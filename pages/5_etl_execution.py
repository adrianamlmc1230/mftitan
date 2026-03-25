"""ETL 執行頁面。

功能：
- 顯示有 match_records 資料的聯賽清單，允許勾選
- 點擊「執行 ETL」觸發 pipeline，顯示處理進度
- 完成後顯示結果摘要

Validates: Requirements 9.3, 10.2, 16.1, 16.2, 16.4, 16.5, 16.6
"""

import streamlit as st

from app import get_store
from core.pipeline import ETLPipeline

store = get_store()

st.title("🚀 ETL 執行")

# ---------------------------------------------------------------------------
# 聯賽清單（只顯示有 match_records 的）
# ---------------------------------------------------------------------------

leagues = store.list_leagues(active_only=True)

ready_leagues = []
for lg in leagues:
    seasons = store.list_season_instances(lg.id)
    current = next((s for s in seasons if s.role == "current"), None)
    if not current:
        continue
    counts = store.get_match_record_counts(current.id)
    if counts:
        ready_leagues.append((lg, current, counts))

if not ready_leagues:
    st.warning("沒有已匯入比賽紀錄的聯賽。請先至「RPA 檔案上傳」頁面匯入資料。")
    st.stop()

st.subheader("可執行的聯賽")

selected_ids: list[int] = []
for lg, season, counts in ready_leagues:
    total_records = sum(counts.values())
    detail = ", ".join(f"{pt}-{tm}: {n}筆" for (pt, tm), n in sorted(counts.items()))
    checked = st.checkbox(
        f"{lg.code} - {lg.name_zh}（{season.label}，共 {total_records} 筆：{detail}）",
        value=True,
        key=f"chk_{lg.id}",
    )
    if checked:
        selected_ids.append(lg.id)

# ---------------------------------------------------------------------------
# 彈性賽季選擇（設計決策 6）
# ---------------------------------------------------------------------------

with st.expander("🔧 進階：自訂賽季配對"):
    st.caption("預設使用 role=current/previous。如需指定其他賽季配對，請在此設定。")
    custom_pairs: dict[int, tuple[int, int | None]] = {}

    for lg, season, counts in ready_leagues:
        if lg.id not in selected_ids:
            continue
        all_seasons = store.list_season_instances(lg.id)
        if len(all_seasons) <= 1:
            continue

        # 找出預設的 current/previous
        default_current = next((s for s in all_seasons if s.role == "current"), all_seasons[0])
        default_previous = next((s for s in all_seasons if s.role == "previous"), None)

        st.markdown(f"**{lg.code}**")
        c1, c2 = st.columns(2)
        s_opts = {f"{s.label} (id={s.id})": s.id for s in all_seasons}
        s_keys = list(s_opts.keys())

        # 本季預設選中 role=current 的賽季
        curr_default_key = f"{default_current.label} (id={default_current.id})"
        curr_default_idx = s_keys.index(curr_default_key) if curr_default_key in s_keys else 0

        with c1:
            curr_key = st.selectbox(
                "本季", s_keys,
                index=curr_default_idx,
                key=f"cp_curr_{lg.id}",
            )

        # 上季預設選中 role=previous 的賽季（若有）
        prev_options = ["（無上季）"] + s_keys
        if default_previous:
            prev_default_key = f"{default_previous.label} (id={default_previous.id})"
            prev_default_idx = prev_options.index(prev_default_key) if prev_default_key in prev_options else 0
        else:
            prev_default_idx = 0

        with c2:
            prev_key = st.selectbox(
                "上季", prev_options,
                index=prev_default_idx,
                key=f"cp_prev_{lg.id}",
            )
        curr_id = s_opts[curr_key]
        prev_id = s_opts[prev_key] if prev_key != "（無上季）" else None
        custom_pairs[lg.id] = (curr_id, prev_id)

# ---------------------------------------------------------------------------
# 就緒檢查：全域分組與隊伍配置
# ---------------------------------------------------------------------------

global_groups = store.list_global_groups()
has_groups = len(global_groups) > 0
has_assignment_teams = any(
    store.get_all_league_group_teams(lg.id)
    for lg, _, _ in ready_leagues
)

if not has_groups:
    st.warning("尚未建立任何全域分組。請先至「隊伍分組」頁面新增分組（如 Top、Weak）。")
if has_groups and not has_assignment_teams:
    st.warning("尚未為任何聯賽配置分組隊伍。請先至「隊伍分組」頁面設定各聯賽的隊伍。")

etl_ready = has_groups and has_assignment_teams

# ---------------------------------------------------------------------------
# 執行 ETL
# ---------------------------------------------------------------------------

st.markdown("---")

if st.button("▶️ 執行 ETL", type="primary", disabled=len(selected_ids) == 0 or not etl_ready):
    progress_bar = st.progress(0)
    status_text = st.empty()

    def _progress(current: int, total: int, message: str):
        progress_bar.progress(current / total if total > 0 else 1.0)
        status_text.text(message)

    pipeline = ETLPipeline(store)
    season_pairs = custom_pairs if custom_pairs else None

    with st.spinner("ETL 執行中..."):
        run_id = pipeline.execute(
            league_ids=selected_ids,
            season_pairs=season_pairs,
            progress_callback=_progress,
        )

    progress_bar.progress(1.0)
    status_text.text("完成")

    # 顯示結果摘要
    st.success(f"ETL 執行完成（Run ID: {run_id}）")

    runs = store.list_etl_runs(limit=1)
    if runs:
        run = runs[0]
        st.json(run.get("summary", {}))

    # 品質問題
    issues = store.get_quality_issues(run_id)
    if issues:
        st.subheader("⚠️ 品質問題")
        for iss in issues:
            icon = "❌" if iss["severity"] == "error" else "⚠️"
            st.markdown(f"{icon} **{iss['issue_type']}**：{iss['description']}")

# ---------------------------------------------------------------------------
# 最近執行紀錄
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📋 最近執行紀錄")

recent_runs = store.list_etl_runs(limit=5)
if recent_runs:
    for run in recent_runs:
        status_icon = {"completed": "✅", "failed": "❌", "running": "⏳"}.get(
            run["status"], "❓"
        )
        st.markdown(
            f"{status_icon} **Run #{run['id']}** — {run['started_at']} → "
            f"{run.get('completed_at', '進行中')} — {run['status']}"
        )
else:
    st.info("尚無執行紀錄。")
