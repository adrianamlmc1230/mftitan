"""ETL 歷史紀錄頁面。

功能：
- 顯示所有 ETL 執行歷史清單
- 允許選擇歷史版本檢視

Validates: Requirements 19.2, 19.3, 19.4
"""

import json

import streamlit as st

from app import get_store

store = get_store()

st.title("📜 ETL 歷史紀錄")

runs = store.list_etl_runs(limit=50)
if not runs:
    st.info("尚無 ETL 執行紀錄。")
    st.stop()

# ---------------------------------------------------------------------------
# 清理舊紀錄
# ---------------------------------------------------------------------------

col_title, col_cleanup = st.columns([4, 1])
with col_cleanup:
    if st.button("🧹 清理舊紀錄"):
        deleted = store.cleanup_old_etl_runs(keep_recent=10)
        if deleted > 0:
            st.success(f"已清理 {deleted} 筆舊紀錄")
            st.rerun()
        else:
            st.info("無需清理")

# ---------------------------------------------------------------------------
# 歷史清單
# ---------------------------------------------------------------------------

st.subheader("執行紀錄")

for run in runs:
    status_icon = {"completed": "✅", "failed": "❌", "running": "⏳"}.get(
        run["status"], "❓"
    )
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        st.markdown(
            f"{status_icon} **Run #{run['id']}** — {run['started_at']} → "
            f"{run.get('completed_at', '進行中')}"
        )
    with col2:
        st.caption(f"狀態：{run['status']}")
        if run.get("scope_leagues"):
            st.caption(f"範圍：{run['scope_leagues']}")
    with col3:
        if run["status"] == "completed":
            if st.button("檢視", key=f"view_{run['id']}"):
                st.session_state["history_run_id"] = run["id"]
        if st.button("🗑️", key=f"del_{run['id']}", help=f"刪除 Run #{run['id']}"):
            store.delete_etl_run(run["id"])
            st.success(f"已刪除 Run #{run['id']}")
            st.rerun()

    st.markdown("---")

# ---------------------------------------------------------------------------
# 檢視選定的歷史版本
# ---------------------------------------------------------------------------

selected_run_id = st.session_state.get("history_run_id")
if selected_run_id:
    st.subheader(f"Run #{selected_run_id} 詳細")

    # 摘要
    run_data = next((r for r in runs if r["id"] == selected_run_id), None)
    if run_data:
        if run_data.get("summary"):
            st.json(run_data["summary"])

        # 參數快照
        with st.expander("參數快照"):
            if run_data.get("params_snapshot"):
                st.json(run_data["params_snapshot"])

    # 品質問題
    issues = store.get_quality_issues(selected_run_id)
    if issues:
        st.subheader("品質問題")
        for iss in issues:
            icon = "❌" if iss["severity"] == "error" else "⚠️"
            st.markdown(f"{icon} **{iss['issue_type']}**：{iss['description']}")

    # 決策結果摘要
    decisions = store.get_decision_results(selected_run_id)
    if decisions:
        st.subheader(f"決策結果（{len(decisions)} 筆）")
        all_leagues = {lg.id: lg for lg in store.list_leagues(active_only=False)}
        for d in decisions:
            lg = all_leagues.get(d["league_id"])
            lg_name = f"{lg.code} - {lg.name_zh}" if lg else f"League#{d['league_id']}"
            st.caption(
                f"{lg_name} | {d['play_type']}-{d['timing']} | "
                f"Home: {d['home_signals']} | Away: {d['away_signals']}"
            )
    else:
        st.info("此 Run 沒有決策結果。")

    st.markdown("---")
    st.info("💡 如需在看板中檢視此版本，請至「Report 看板」頁面選擇對應的 Run。")
