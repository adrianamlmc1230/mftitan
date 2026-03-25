"""訊號變化追蹤頁面。

比較兩次 ETL Run 的訊號差異，快速看出哪些聯賽的訊號發生了變化。
"""

import pandas as pd
import streamlit as st

from app import get_store

store = get_store()

st.title("📈 訊號追蹤")
st.caption("比較不同 ETL 版本的訊號變化")

runs = store.list_etl_runs(limit=20)
completed_runs = [r for r in runs if r["status"] == "completed"]

if len(completed_runs) < 2:
    st.warning("需要至少 2 個已完成的 ETL Run 才能比較。")
    st.stop()

run_options = {f"Run #{r['id']} — {r['completed_at']}": r["id"] for r in completed_runs}
run_keys = list(run_options.keys())

col1, col2 = st.columns(2)
with col1:
    old_key = st.selectbox("舊版本", run_keys, index=min(1, len(run_keys) - 1))
with col2:
    new_key = st.selectbox("新版本", run_keys, index=0)

old_run_id = run_options[old_key]
new_run_id = run_options[new_key]

if old_run_id == new_run_id:
    st.info("請選擇不同的版本進行比較。")
    st.stop()

# 取得兩個版本的決策結果
old_decisions = store.get_decision_results(old_run_id)
new_decisions = store.get_decision_results(new_run_id)
all_leagues = {lg.id: lg for lg in store.list_leagues(active_only=False)}

# 建立 key → signals 的對照
def _build_signal_map(decisions):
    m = {}
    for d in decisions:
        key = (d["league_id"], d.get("global_group_id"), d["play_type"], d["timing"])
        m[key] = (d["home_signals"], d["away_signals"])
    return m

old_map = _build_signal_map(old_decisions)
new_map = _build_signal_map(new_decisions)

all_keys = sorted(set(old_map.keys()) | set(new_map.keys()))

# 比較
diff_rows = []
unchanged = 0
new_only = 0
removed = 0

for key in all_keys:
    lid, gid, pt, tm = key
    lg = all_leagues.get(lid)
    lg_name = f"{lg.code}" if lg else f"#{lid}"

    old_sig = old_map.get(key)
    new_sig = new_map.get(key)

    if old_sig is None:
        new_only += 1
        diff_rows.append({
            "聯賽": lg_name,
            "分組": gid,
            "玩法": pt,
            "時段": tm,
            "變化": "🆕 新增",
            "Home (新)": str(new_sig[0]) if new_sig else "",
            "Away (新)": str(new_sig[1]) if new_sig else "",
            "Home (舊)": "",
            "Away (舊)": "",
        })
    elif new_sig is None:
        removed += 1
        diff_rows.append({
            "聯賽": lg_name,
            "分組": gid,
            "玩法": pt,
            "時段": tm,
            "變化": "❌ 移除",
            "Home (新)": "",
            "Away (新)": "",
            "Home (舊)": str(old_sig[0]),
            "Away (舊)": str(old_sig[1]),
        })
    elif old_sig != new_sig:
        # 找出具體哪些 zone 變了
        changed_zones = []
        for i in range(5):
            oh = old_sig[0][i] if i < len(old_sig[0]) else ""
            nh = new_sig[0][i] if i < len(new_sig[0]) else ""
            oa = old_sig[1][i] if i < len(old_sig[1]) else ""
            na = new_sig[1][i] if i < len(new_sig[1]) else ""
            if oh != nh:
                changed_zones.append(f"H-Z{i+1}:{oh}→{nh}")
            if oa != na:
                changed_zones.append(f"A-Z{i+1}:{oa}→{na}")

        diff_rows.append({
            "聯賽": lg_name,
            "分組": gid,
            "玩法": pt,
            "時段": tm,
            "變化": "🔄 " + ", ".join(changed_zones),
            "Home (新)": str(new_sig[0]),
            "Away (新)": str(new_sig[1]),
            "Home (舊)": str(old_sig[0]),
            "Away (舊)": str(old_sig[1]),
        })
    else:
        unchanged += 1

# 摘要
st.markdown("---")
c1, c2, c3, c4 = st.columns(4)
c1.metric("未變化", unchanged)
c2.metric("有變化", len([r for r in diff_rows if r["變化"].startswith("🔄")]))
c3.metric("新增", new_only)
c4.metric("移除", removed)

if diff_rows:
    st.dataframe(diff_rows, use_container_width=True, hide_index=True)
else:
    st.success("兩個版本的訊號完全一致。")
