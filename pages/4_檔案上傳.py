"""RPA 檔案批量上傳頁面。

功能：
- st.file_uploader 支援多選 xlsx 檔案
- 逐一解析檔名 → 識別聯賽 → 匯入資料
- 遇到新聯賽時顯示輸入 code 的表單
- 顯示每個檔案的處理結果與整體摘要
- 顯示進度指示器

Validates: Requirements 4.1, 4.2, 4.4, 4.5, 4.6, 7.4
"""

import streamlit as st

from app import get_store
from core.filename_parser import FilenameParser
from core.league_resolver import LeagueResolver, PendingLeague, ResolveResult
from core.match_importer import MatchImporter
from core.pipeline import ETLPipeline

store = get_store()
parser = FilenameParser()
resolver = LeagueResolver(store)
importer = MatchImporter(store)

st.title("📁 檔案上傳")
st.caption("上傳 RPA Excel 檔案，系統自動匯入並更新計算結果")

# ---------------------------------------------------------------------------
# 檔案上傳
# ---------------------------------------------------------------------------

uploaded_files = st.file_uploader(
    "選擇 RPA Excel 檔案（可多選）",
    type=["xlsx"],
    accept_multiple_files=True,
    help="支援的檔名格式：{聯賽中文名}{賽季年份}[{階段}]{時機+玩法}.xlsx",
)

if not uploaded_files:
    st.info("請上傳一個或多個 RPA Excel 檔案。")
    st.stop()

# ---------------------------------------------------------------------------
# 初始化 session state
# ---------------------------------------------------------------------------

if "pending_codes" not in st.session_state:
    st.session_state.pending_codes = {}  # {filename: PendingLeague}

if "import_results" not in st.session_state:
    st.session_state.import_results = []  # list of result dicts

if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()

# ---------------------------------------------------------------------------
# Step 1: 解析所有檔名，找出需要輸入 code 的新聯賽
# ---------------------------------------------------------------------------

parse_results = {}  # {filename: ParsedFilename | str(error)}
pending_new = {}    # {filename: PendingLeague}

for f in uploaded_files:
    if f.name in parse_results:
        continue
    try:
        parsed = parser.parse(f.name)
        parse_results[f.name] = parsed

        # 嘗試識別聯賽
        result = resolver.resolve(parsed)
        if isinstance(result, PendingLeague):
            pending_new[f.name] = result
    except ValueError as e:
        parse_results[f.name] = str(e)

# ---------------------------------------------------------------------------
# Step 2: 顯示需要輸入 code 的新聯賽表單
# ---------------------------------------------------------------------------

if pending_new:
    st.markdown("---")
    st.subheader("🆕 偵測到新聯賽，請輸入代碼")

    # 按 (name_zh, phase) 去重
    unique_pending: dict[tuple, tuple[str, PendingLeague]] = {}
    for fname, pending in pending_new.items():
        key = (pending.name_zh, pending.phase)
        if key not in unique_pending:
            unique_pending[key] = (fname, pending)

    with st.form("new_league_codes"):
        code_inputs = {}
        for key, (fname, pending) in unique_pending.items():
            phase_display = f"（{pending.phase}）" if pending.phase else ""
            label = f"{pending.name_zh}{phase_display}"
            code_inputs[key] = st.text_input(
                f"聯賽代碼 — {label}",
                key=f"code_{pending.name_zh}_{pending.phase}",
                placeholder="例：CHN1",
            )

        submit_codes = st.form_submit_button("確認代碼並開始匯入")

    if not submit_codes:
        st.warning("請輸入所有新聯賽的代碼後點擊「確認代碼並開始匯入」。")
        st.stop()

    # 驗證所有 code 都已填寫
    missing = [k for k, v in code_inputs.items() if not v.strip()]
    if missing:
        st.error("所有新聯賽都必須輸入代碼。")
        st.stop()

    # 建立新聯賽
    created_leagues = {}  # {(name_zh, phase): league_id}
    for key, code in code_inputs.items():
        _, pending = unique_pending[key]
        try:
            league_id = resolver.create_league_with_code(pending, code.strip())
            created_leagues[key] = league_id
            st.success(f"✅ 已建立聯賽：{pending.name_zh} → {code.strip()}")
        except ValueError as e:
            st.error(f"❌ 建立失敗：{e}")
            st.stop()

# ---------------------------------------------------------------------------
# Step 3: 執行匯入
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📥 匯入進度")

progress_bar = st.progress(0)
total = len(uploaded_files)
results_summary = {
    "success": 0,
    "failed": 0,
    "skipped": 0,
    "new_leagues": len(pending_new),
    "new_seasons": 0,
    "total_records": 0,
}

result_rows = []

for i, f in enumerate(uploaded_files):
    progress_bar.progress((i + 1) / total)
    parsed = parse_results.get(f.name)

    # 解析失敗的檔案
    if isinstance(parsed, str):
        result_rows.append({
            "檔案": f.name,
            "狀態": "❌ 解析失敗",
            "訊息": parsed,
            "筆數": 0,
        })
        results_summary["failed"] += 1
        continue

    # 重新 resolve（新聯賽已建立）
    resolve_result = resolver.resolve(parsed)
    if isinstance(resolve_result, PendingLeague):
        result_rows.append({
            "檔案": f.name,
            "狀態": "⏭️ 跳過",
            "訊息": "聯賽尚未建立",
            "筆數": 0,
        })
        results_summary["skipped"] += 1
        continue

    if resolve_result.is_new_season:
        results_summary["new_seasons"] += 1

    # 執行匯入
    import_result = importer.import_file(
        file_content=f.getvalue(),
        season_instance_id=resolve_result.season_instance_id,
        play_type=parsed.play_type,
        timing=parsed.timing,
    )

    if import_result.success:
        results_summary["success"] += 1
        results_summary["total_records"] += import_result.records_imported
        warnings_text = "；".join(import_result.warnings) if import_result.warnings else ""
        diff_text = ""
        if import_result.previous_count > 0:
            d = import_result.diff
            diff_text = f"（{import_result.previous_count}→{import_result.records_imported}, {'+' if d > 0 else ''}{d}）"
        elif import_result.previous_count == 0:
            diff_text = "（新匯入）"
        result_rows.append({
            "檔案": f.name,
            "狀態": "✅ 成功",
            "訊息": warnings_text or "匯入完成",
            "筆數": import_result.records_imported,
            "差異": diff_text,
        })
    else:
        results_summary["failed"] += 1
        result_rows.append({
            "檔案": f.name,
            "狀態": "❌ 失敗",
            "訊息": import_result.error or "未知錯誤",
            "筆數": 0,
        })

progress_bar.progress(1.0)

# ---------------------------------------------------------------------------
# Step 4: 顯示匯入摘要
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📊 匯入摘要")

col1, col2, col3, col4 = st.columns(4)
col1.metric("成功", results_summary["success"])
col2.metric("失敗", results_summary["failed"])
col3.metric("新建賽季", results_summary["new_seasons"])
col4.metric("總筆數", results_summary["total_records"])

# 詳細結果表格
if result_rows:
    st.dataframe(result_rows, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Step 5: 自動觸發 ETL 更新結果
# ---------------------------------------------------------------------------

if results_summary["success"] > 0:
    # 收集本次匯入涉及的聯賽 ID
    affected_league_ids: set[int] = set()
    for f in uploaded_files:
        parsed = parse_results.get(f.name)
        if isinstance(parsed, str):
            continue
        resolve_result = resolver.resolve(parsed)
        if isinstance(resolve_result, ResolveResult):
            affected_league_ids.add(resolve_result.league_id)

    if affected_league_ids:
        st.markdown("---")
        st.subheader("⚡ 自動更新計算結果")

        # 檢查是否有分組配置
        has_groups = any(
            store.get_all_league_group_teams(lid)
            for lid in affected_league_ids
        )

        if not has_groups:
            st.warning("涉及的聯賽尚未配置分組隊伍，無法自動執行 ETL。請先至「隊伍分組」頁面設定。")
        else:
            with st.spinner("正在更新計算結果..."):
                pipeline = ETLPipeline(store)
                run_id = pipeline.execute(league_ids=list(affected_league_ids))

            st.success(f"計算完成（Run #{run_id}），Report 看板已更新。")
