"""資料庫備份與還原頁面。"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from app import get_store

st.title("💾 資料庫管理")
st.caption("備份下載與還原匯入")

store = get_store()

# ---------------------------------------------------------------------------
# Backup: use sqlite3 backup API to create a consistent copy
# ---------------------------------------------------------------------------
st.subheader("📥 備份下載")
st.markdown("使用 SQLite backup API 產生一致性快照，下載為 `.db` 檔案。")

if st.button("產生備份", key="btn_backup"):
    with st.spinner("正在備份..."):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        dst_conn = sqlite3.connect(tmp.name)
        store._conn.backup(dst_conn)
        dst_conn.close()

        backup_bytes = Path(tmp.name).read_bytes()
        Path(tmp.name).unlink(missing_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label=f"⬇️ 下載備份 ({len(backup_bytes) / 1024:.0f} KB)",
        data=backup_bytes,
        file_name=f"quant_backup_{ts}.db",
        mime="application/octet-stream",
    )
    st.success("備份完成，點擊上方按鈕下載。")

st.markdown("---")

# ---------------------------------------------------------------------------
# Restore: upload a .db file and replace current database
# ---------------------------------------------------------------------------
st.subheader("📤 還原匯入")
st.warning("⚠️ 還原會覆蓋目前所有資料，請確認已備份當前資料庫。")

uploaded = st.file_uploader(
    "上傳備份檔案（.db）",
    type=["db"],
    key="restore_upload",
)

if uploaded is not None:
    st.info(f"已選擇：{uploaded.name}（{uploaded.size / 1024:.0f} KB）")

    # Validate: try opening as sqlite3
    tmp_restore = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_restore.write(uploaded.getvalue())
    tmp_restore.close()

    valid = False
    try:
        test_conn = sqlite3.connect(tmp_restore.name)
        test_conn.execute("SELECT count(*) FROM sqlite_master")
        table_count = test_conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        test_conn.close()
        if table_count > 0:
            valid = True
            st.success(f"✅ 檔案驗證通過，包含 {table_count} 個資料表。")
        else:
            st.error("❌ 檔案不包含任何資料表。")
    except Exception as e:
        st.error(f"❌ 檔案驗證失敗：{e}")

    if valid:
        confirm = st.checkbox("我確認要覆蓋目前的資料庫", key="confirm_restore")
        if confirm and st.button("🔄 執行還原", type="primary", key="btn_restore"):
            with st.spinner("正在還原..."):
                # Use backup API in reverse: uploaded db → current connection
                src_conn = sqlite3.connect(tmp_restore.name)
                src_conn.backup(store._conn)
                src_conn.close()
                # Re-enable pragmas after restore
                store._conn.execute("PRAGMA journal_mode=WAL")
                store._conn.execute("PRAGMA foreign_keys=ON")

            Path(tmp_restore.name).unlink(missing_ok=True)
            st.success("✅ 資料庫還原完成。請重新整理頁面以載入新資料。")
            st.balloons()
    else:
        Path(tmp_restore.name).unlink(missing_ok=True)
