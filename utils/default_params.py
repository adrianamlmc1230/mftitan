"""預設參數初始化模組。

在系統首次啟動時自動將預設演算法參數寫入 ConfigStore。
實際預設值定義在 config/default_params.json。

ConfigStore.init_db() 已在資料表為空時自動呼叫 reset_params_to_default()，
本模組提供額外的程式化存取介面。

Validates: Requirement 17.4
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULTS_PATH = _PROJECT_ROOT / "config" / "default_params.json"


def load_defaults() -> dict[str, Any]:
    """讀取 config/default_params.json 並回傳預設參數字典。"""
    with open(_DEFAULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def ensure_defaults(config_store) -> None:
    """確保 ConfigStore 中有所有預設參數。

    僅寫入尚未存在的參數，不覆蓋使用者已修改的值。
    """
    defaults = load_defaults()
    existing = config_store.get_all_params()
    for key, value in defaults.items():
        if key not in existing:
            config_store.set_param(key, value)
