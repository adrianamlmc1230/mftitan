"""訊號變化追蹤頁面。

比較兩次 ETL Run 的訊號差異。
以 5 大區間表格並排顯示新舊訊號，變化處以背景色標記。
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

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

old_decisions = store.get_decision_results(old_run_id)
new_decisions = store.get_decision_results(new_run_id)
all_leagues = {lg.id: lg for lg in store.list_leagues(active_only=False)}

_group_cache: dict[int, str] = {}
def _group_name(gid: int) -> str:
    if gid in _group_cache:
        return _group_cache[gid]
    row = store._conn.execute(
        "SELECT display_name, name FROM global_groups WHERE id = ?", (gid,)
    ).fetchone()
    name = (row["display_name"] or row["name"]) if row else f"#{gid}"
    _group_cache[gid] = name
    return name

ZONE_LABELS = ["-50~-24%", "-23~-8%", "-7~+7%", "+8~+23%", "+24~+50%"]

def _build_signal_map(decisions):
    m = {}
    for d in decisions:
        key = (d["league_id"], d.get("global_group_id", 0), d["play_type"], d["timing"])
        m[key] = (d["home_signals"], d["away_signals"])
    return m

old_map = _build_signal_map(old_decisions)
new_map = _build_signal_map(new_decisions)
all_keys = sorted(set(old_map.keys()) | set(new_map.keys()))

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

st.markdown("---")
fcol1, fcol2, fcol3, fcol4 = st.columns(4)
with fcol1:
    play_filter = st.selectbox("玩法", ["全部", "HDP", "OU"])
with fcol2:
    timing_filter = st.selectbox("時段", ["全部", "Early", "RT"])
with fcol3:
    # Collect all group names from the data
    _all_group_names = sorted(set(_group_name(k[1]) for k in all_keys))
    group_filter = st.selectbox("分組", ["全部"] + _all_group_names)
with fcol4:
    show_mode = st.selectbox("顯示", ["僅變化", "全部"])

# ---------------------------------------------------------------------------
# Diff — group by (league, group, play_type, timing)
# ---------------------------------------------------------------------------

unchanged = 0
changed_count = 0
new_count = 0
removed_count = 0

# Collect changed items for rendering
changed_items: list[dict] = []

for key in all_keys:
    lid, gid, pt, tm = key
    if play_filter != "全部" and pt != play_filter:
        continue
    if timing_filter != "全部" and tm != timing_filter:
        continue

    lg = all_leagues.get(lid)
    lg_label = f"{lg.code} - {lg.name_zh}" if lg else f"#{lid}"
    group_label = _group_name(gid)

    if group_filter != "全部" and group_label != group_filter:
        continue

    old_sig = old_map.get(key)
    new_sig = new_map.get(key)

    if old_sig is None:
        new_count += 1
        if show_mode == "全部":
            changed_items.append({
                "label": lg_label, "group": group_label, "pt": pt, "tm": tm,
                "old_h": [""] * 5, "old_a": [""] * 5,
                "new_h": list(new_sig[0]) if new_sig else [""] * 5,
                "new_a": list(new_sig[1]) if new_sig else [""] * 5,
                "tag": "🆕",
            })
        continue
    if new_sig is None:
        removed_count += 1
        continue

    # Check if any zone changed
    old_h = list(old_sig[0]) + [""] * (5 - len(old_sig[0]))
    old_a = list(old_sig[1]) + [""] * (5 - len(old_sig[1]))
    new_h = list(new_sig[0]) + [""] * (5 - len(new_sig[0]))
    new_a = list(new_sig[1]) + [""] * (5 - len(new_sig[1]))

    has_diff = old_h[:5] != new_h[:5] or old_a[:5] != new_a[:5]
    if has_diff:
        changed_count += 1
        changed_items.append({
            "label": lg_label, "group": group_label, "pt": pt, "tm": tm,
            "old_h": old_h[:5], "old_a": old_a[:5],
            "new_h": new_h[:5], "new_a": new_a[:5],
            "tag": "🔄",
        })
    else:
        unchanged += 1
        if show_mode == "全部":
            changed_items.append({
                "label": lg_label, "group": group_label, "pt": pt, "tm": tm,
                "old_h": old_h[:5], "old_a": old_a[:5],
                "new_h": new_h[:5], "new_a": new_a[:5],
                "tag": "✓",
            })

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

st.markdown("---")
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("未變化", unchanged)
mc2.metric("有變化", changed_count)
mc3.metric("新增", new_count)
mc4.metric("移除", removed_count)

# ---------------------------------------------------------------------------
# Render — side-by-side 5-zone tables per changed item
# Diff color logic:
#   Green  = signal appeared (old empty → new has value)
#   Red    = signal disappeared (old has value → new empty)
#   Orange = signal changed (both have value but different)
#   Deeper = higher signal numeric value
# ---------------------------------------------------------------------------

def _sig_val(sig: str) -> float:
    if not sig or len(sig) < 2:
        return 0.0
    try:
        return float(sig[1:])
    except ValueError:
        return 0.0


def _diff_bg(old_val: str, new_val: str, side: str) -> str:
    """Return CSS background based on diff semantics.

    Args:
        old_val: signal in old version
        new_val: signal in new version
        side: 'old' or 'new' — which table we're rendering
    """
    if old_val == new_val:
        return ""

    if side == "new":
        # New table: highlight what's new or changed
        if not old_val and new_val:
            # Appeared — green, deeper for stronger signal
            alpha = max(_sig_val(new_val) * 0.15, 0.10)
            return f"background-color: rgba(34, 139, 34, {min(alpha, 0.40):.2f})"
        elif old_val and not new_val:
            # Disappeared — no highlight on new side (it's empty)
            return ""
        else:
            # Changed — orange tint
            alpha = max(_sig_val(new_val) * 0.12, 0.08)
            return f"background-color: rgba(255, 165, 0, {min(alpha, 0.30):.2f})"
    else:
        # Old table: highlight what disappeared
        if old_val and not new_val:
            # Disappeared — red, deeper for stronger signal
            alpha = max(_sig_val(old_val) * 0.15, 0.10)
            return f"background-color: rgba(178, 34, 34, {min(alpha, 0.40):.2f})"
        elif not old_val and new_val:
            # Appeared — no highlight on old side (it's empty)
            return ""
        else:
            # Changed — orange tint
            alpha = max(_sig_val(old_val) * 0.12, 0.08)
            return f"background-color: rgba(255, 165, 0, {min(alpha, 0.30):.2f})"


def _render_signal_table(signals_h, signals_a, other_h, other_a, side: str):
    """Render a 5-zone signal table with diff-semantic coloring.

    Args:
        signals_h/a: the signals for this table (Home/Away)
        other_h/a: the signals from the other version (for comparison)
        side: 'old' or 'new'
    """
    rows = []
    for i in range(5):
        h = signals_h[i] if i < len(signals_h) else ""
        a = signals_a[i] if i < len(signals_a) else ""
        rows.append({"區間": ZONE_LABELS[i], "Home": h, "Away": a})
    df = pd.DataFrame(rows)

    def style_fn(row):
        i = row.name
        styles = [""] * len(row)
        col_list = list(row.index)
        for col, other_list in [("Home", other_h), ("Away", other_a)]:
            if col not in col_list:
                continue
            ci = col_list.index(col)
            this_val = str(row[col]) if row[col] else ""
            other_val = other_list[i] if i < len(other_list) else ""
            styles[ci] = _diff_bg(
                old_val=this_val if side == "old" else other_val,
                new_val=other_val if side == "old" else this_val,
                side=side,
            )
        return styles

    return df.style.apply(style_fn, axis=1)


if not changed_items:
    st.success("✅ 兩個版本的訊號完全一致。")
else:
    for item in changed_items:
        tag = item["tag"]
        header = f"{tag} {item['label']} · {item['group']} · {item['pt']}-{item['tm']}"

        with st.expander(header, expanded=(tag == "🔄")):
            left, right = st.columns(2)

            with left:
                st.caption(f"舊版 (Run #{old_run_id})")
                st.dataframe(
                    _render_signal_table(
                        item["old_h"], item["old_a"],
                        item["new_h"], item["new_a"],
                        side="old",
                    ),
                    use_container_width=True, hide_index=True,
                )

            with right:
                st.caption(f"新版 (Run #{new_run_id})")
                st.dataframe(
                    _render_signal_table(
                        item["new_h"], item["new_a"],
                        item["old_h"], item["old_a"],
                        side="new",
                    ),
                    use_container_width=True, hide_index=True,
                )
