"""演算法參數設定頁面。

功能：
- 顯示所有可設定參數及當前值
- 允許修改參數值，提供說明與預設值參考
- 「恢復預設值」按鈕
- 參數驗證（分界點升序、mapping 完整性）

Validates: Requirements 17.1, 17.2, 17.3, 17.4
"""

import json

import streamlit as st

from app import get_store

store = get_store()

# 參數說明對照表
_PARAM_DESC = {
    "x_value_boundaries": "X 值 9 區間的 8 個分界點（升序浮點數列表）",
    "five_zone_mapping": "9 區間→5 大區間的分組方式（二維陣列，每個子陣列為一個大區間包含的 zone_id）",
    "round_block_size": "每個輪次區段包含的輪數",
    "guard_ratio_threshold": "訊號數值判定的贏輸比值門檻",
    "strength_upgrade_multiplier": "護級=2 時 MAX/MIN 達此倍數則升級為 4",
    "settlement_values": "各結算結果對應的累加數值（JSON 物件）",
}


def _validate_boundaries(boundaries: list) -> str | None:
    """驗證分界點：必須為升序浮點數列表。回傳錯誤訊息或 None。"""
    if not isinstance(boundaries, list) or len(boundaries) == 0:
        return "分界點必須為非空列表"
    for v in boundaries:
        if not isinstance(v, (int, float)):
            return f"分界點必須為數字，發現：{v}"
    for i in range(1, len(boundaries)):
        if boundaries[i] <= boundaries[i - 1]:
            return f"分界點必須升序排列：{boundaries[i - 1]} >= {boundaries[i]}"
    return None


def _validate_five_zone_mapping(mapping: list, num_zones: int = 9) -> str | None:
    """驗證五大區間分組：所有 zone_id 必須被涵蓋且不重複。"""
    if not isinstance(mapping, list) or len(mapping) == 0:
        return "分組必須為非空二維陣列"
    all_ids = []
    for group in mapping:
        if not isinstance(group, list):
            return f"每個分組必須為陣列，發現：{group}"
        for zid in group:
            if not isinstance(zid, int):
                return f"zone_id 必須為整數，發現：{zid}"
            all_ids.append(zid)
    expected = list(range(1, num_zones + 1))
    if sorted(all_ids) != expected:
        return f"分組必須涵蓋所有區間 {expected}，實際 {sorted(all_ids)}"
    return None


def _validate_param(key: str, value) -> str | None:
    """根據參數類型進行驗證。"""
    if key == "x_value_boundaries":
        return _validate_boundaries(value)
    if key == "five_zone_mapping":
        return _validate_five_zone_mapping(value)
    if key in ("round_block_size",):
        if not isinstance(value, int) or value < 1:
            return f"{key} 必須為正整數"
    if key in ("guard_ratio_threshold", "strength_upgrade_multiplier"):
        if not isinstance(value, (int, float)) or value <= 0:
            return f"{key} 必須為正數"
    if key == "settlement_values":
        if not isinstance(value, dict):
            return "settlement_values 必須為 JSON 物件"
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

st.title("⚙️ 演算法參數設定")

# 恢復預設值按鈕
col_reset, _ = st.columns([1, 3])
with col_reset:
    if st.button("🔄 恢復所有預設值"):
        store.reset_params_to_default()
        st.success("已恢復所有參數為預設值")
        st.rerun()

st.markdown("---")

# 讀取當前參數
params = store.get_all_params()

# 讀取預設值作為參考
import json as _json
from pathlib import Path as _Path

_defaults_path = _Path(__file__).resolve().parent.parent / "config" / "default_params.json"
with open(_defaults_path, encoding="utf-8") as _f:
    _defaults = _json.load(_f)

# 逐一顯示參數
for key in _PARAM_DESC:
    current_value = params.get(key)
    default_value = _defaults.get(key)
    desc = _PARAM_DESC[key]

    with st.expander(f"📌 {key}", expanded=False):
        st.caption(desc)
        st.markdown(f"**預設值：** `{json.dumps(default_value, ensure_ascii=False)}`")

        # 根據參數類型選擇不同的編輯方式
        if key in ("round_block_size",):
            new_val = st.number_input(
                f"{key} 值",
                value=int(current_value) if current_value is not None else int(default_value),
                min_value=1,
                step=1,
                key=f"input_{key}",
            )
            if st.button("儲存", key=f"save_{key}"):
                err = _validate_param(key, int(new_val))
                if err:
                    st.error(err)
                else:
                    store.set_param(key, int(new_val))
                    st.success(f"已儲存 {key} = {int(new_val)}")

        elif key in ("guard_ratio_threshold", "strength_upgrade_multiplier"):
            new_val = st.number_input(
                f"{key} 值",
                value=float(current_value) if current_value is not None else float(default_value),
                min_value=0.01,
                step=0.1,
                format="%.2f",
                key=f"input_{key}",
            )
            if st.button("儲存", key=f"save_{key}"):
                err = _validate_param(key, float(new_val))
                if err:
                    st.error(err)
                else:
                    store.set_param(key, float(new_val))
                    st.success(f"已儲存 {key} = {float(new_val)}")

        else:
            # JSON 編輯模式
            current_json = json.dumps(
                current_value if current_value is not None else default_value,
                ensure_ascii=False, indent=2,
            )
            new_json = st.text_area(
                f"{key} (JSON)",
                value=current_json,
                height=120 if key in ("settlement_values", "five_zone_mapping") else 80,
                key=f"input_{key}",
            )
            if st.button("儲存", key=f"save_{key}"):
                try:
                    parsed = json.loads(new_json)
                except json.JSONDecodeError as e:
                    st.error(f"JSON 格式錯誤：{e}")
                    parsed = None

                if parsed is not None:
                    err = _validate_param(key, parsed)
                    if err:
                        st.error(err)
                    else:
                        store.set_param(key, parsed)
                        st.success(f"已儲存 {key}")
