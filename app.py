"""足球賠率量化分析系統 V2 — Streamlit 主入口。"""

import streamlit as st

from core.config_store import ConfigStore

st.set_page_config(
    page_title="足球量化分析",
    page_icon="⚽",
    layout="wide",
)


@st.cache_resource
def get_store() -> ConfigStore:
    """全域共用的 ConfigStore 實例。"""
    return ConfigStore()


def main():
    st.title("⚽ 足球量化分析系統")
    st.caption("系統總覽 — 快速掌握所有聯賽狀態")

    store = get_store()

    # 系統摘要
    leagues = store.list_leagues(active_only=False)
    active_leagues = [lg for lg in leagues if lg.is_active]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("聯賽總數", len(leagues))
    with col2:
        st.metric("啟用中", len(active_leagues))

    # 統計已設定檔案數
    file_count = 0
    for lg in active_leagues:
        seasons = store.list_season_instances(lg.id)
        for s in seasons:
            fps = store.get_file_paths(s.id)
            file_count += len(fps)

    with col3:
        st.metric("已設定檔案", file_count)

    # 最後 ETL 時間
    runs = store.list_etl_runs(limit=1)
    last_etl = runs[0]["completed_at"] if runs else "尚未執行"
    with col4:
        st.metric("最後 ETL", last_etl or "執行中")

    st.markdown("---")

    # 洲別分布
    st.subheader("聯賽洲別分布")
    continent_counts = {}
    for lg in active_leagues:
        continent_counts[lg.continent] = continent_counts.get(lg.continent, 0) + 1

    continent_names = {"ASI": "亞洲", "EUR": "歐洲", "AME": "美洲", "AFR": "非洲"}
    cols = st.columns(4)
    for i, (code, label) in enumerate(continent_names.items()):
        with cols[i]:
            st.metric(label, continent_counts.get(code, 0))

    st.markdown("---")

    # -----------------------------------------------------------------------
    # 聯賽健康診斷
    # -----------------------------------------------------------------------

    with st.expander("🩺 聯賽健康診斷", expanded=False):

        # 取得最新 completed ETL run
        latest_run_id = None
        completed_runs = [r for r in store.list_etl_runs(limit=5) if r["status"] == "completed"]
        if completed_runs:
            latest_run_id = completed_runs[0]["id"]

        global_groups = store.list_global_groups()
        diag_rows = []

        for lg in leagues:
            seasons = store.list_season_instances(lg.id)
            current = next((s for s in seasons if s.role == "current"), None)
            previous = next((s for s in seasons if s.role == "previous"), None)

            # 比賽紀錄數
            curr_records = 0
            prev_records = 0
            if current:
                counts = store.get_match_record_counts(current.id)
                curr_records = sum(counts.values())
            if previous:
                counts = store.get_match_record_counts(previous.id)
                prev_records = sum(counts.values())

            # 分組隊伍配置
            group_status_parts = []
            has_any_group = False
            for gg in global_groups:
                curr_teams = store.get_league_group_teams(lg.id, gg.id, "current")
                prev_teams = store.get_league_group_teams(lg.id, gg.id, "previous")
                if curr_teams or prev_teams:
                    has_any_group = True
                    group_status_parts.append(f"{gg.name}: 本{len(curr_teams)}/上{len(prev_teams)}")

            group_text = "；".join(group_status_parts) if group_status_parts else "❌ 未配置"

            # ETL 決策結果
            decision_count = 0
            if latest_run_id:
                decisions = store.get_decision_results(latest_run_id, league_id=lg.id)
                decision_count = len(decisions)

            # 判斷狀態
            issues = []
            if not lg.is_active:
                issues.append("已停用")
            if not current:
                issues.append("無本季")
            elif curr_records == 0:
                issues.append("本季無紀錄")
            if not previous:
                issues.append("無上季")
            elif prev_records == 0:
                issues.append("上季無紀錄")
            if not has_any_group:
                issues.append("未配置分組")
            if decision_count == 0 and lg.is_active and current and curr_records > 0:
                issues.append("無決策結果")
            if not lg.continent:
                issues.append("未設洲別")

            if not issues:
                status = "✅ 正常"
            elif "已停用" in issues:
                status = "⏸️ 停用"
            elif any(x in issues for x in ["無本季", "本季無紀錄", "未配置分組"]):
                status = "❌ 不可用"
            else:
                status = "⚠️ 部分"

            diag_rows.append({
                "狀態": status,
                "代碼": lg.code,
                "名稱": lg.name_zh,
                "洲別": lg.continent or "—",
                "本季": f"{current.label} ({curr_records}筆)" if current else "—",
                "上季": f"{previous.label} ({prev_records}筆)" if previous else "—",
                "分組": group_text,
                "決策": f"{decision_count}筆" if decision_count > 0 else "—",
                "問題": "、".join(issues) if issues else "—",
            })

        # 摘要指標
        ok_count = sum(1 for r in diag_rows if r["狀態"] == "✅ 正常")
        warn_count = sum(1 for r in diag_rows if r["狀態"] == "⚠️ 部分")
        err_count = sum(1 for r in diag_rows if r["狀態"] == "❌ 不可用")

        dc1, dc2, dc3 = st.columns(3)
        dc1.metric("✅ 正常", ok_count)
        dc2.metric("⚠️ 部分", warn_count)
        dc3.metric("❌ 不可用", err_count)

        # 篩選
        fc1, fc2 = st.columns(2)
        with fc1:
            status_filter = st.selectbox("篩選狀態", ["全部", "✅ 正常", "⚠️ 部分", "❌ 不可用", "⏸️ 停用"], key="diag_status")
        with fc2:
            continent_filter_diag = st.selectbox("篩選洲別", ["全部"] + sorted(set(r["洲別"] for r in diag_rows if r["洲別"] != "—")), key="diag_continent")

        filtered_rows = diag_rows
        if status_filter != "全部":
            filtered_rows = [r for r in filtered_rows if r["狀態"] == status_filter]
        if continent_filter_diag != "全部":
            filtered_rows = [r for r in filtered_rows if r["洲別"] == continent_filter_diag]

        st.dataframe(filtered_rows, use_container_width=True, hide_index=True)

    st.markdown("---")

    # -----------------------------------------------------------------------
    # 操作日誌（最近 20 筆）
    # -----------------------------------------------------------------------
    with st.expander("📋 操作日誌（最近 20 筆）"):
        logs = store.list_audit_logs(limit=20)
        if logs:
            log_rows = [{
                "時間": log["created_at"],
                "操作": log["action"],
                "類型": log["entity_type"],
                "ID": log.get("entity_id") or "—",
                "詳情": log.get("details") or "—",
            } for log in logs]
            st.dataframe(log_rows, use_container_width=True, hide_index=True)
        else:
            st.info("尚無操作日誌")

    st.info("請使用左側導航選擇功能頁面。")


if __name__ == "__main__":
    main()
