# 足球賠率量化分析系統 V2 — 邏輯手冊

技術棧：Python 3.13 / Streamlit / Pandas / SQLite / Docker (port 8501)

---

## 一、資料匯入流程

使用者上傳 RPA Excel 檔案，系統自動完成解析、識別、前處理、結算、入庫。

### 1.1 檔名解析（FilenameParser）

從右到左剝離檔名，例如 `中國中超2025第一階段早亞讓.xlsx`：

```
原始檔名: 中國中超2025第一階段早亞讓.xlsx
  ↓ 移除 .xlsx
  ↓ 匹配尾碼（先長後短）:
      「即+早亞讓」→ RT + HDP
      「早亞讓」   → Early + HDP    ← 命中
      「即+早總進球」→ RT + OU
      「早總進球」  → Early + OU
  ↓ 匹配階段: 「第一階段」
  ↓ 匹配年份: 「2025」
  ↓ 剩餘 = name_zh: 「中國中超」（完整中文名，不拆分國家和聯賽）

結果: name_zh=中國中超, season_year=2025, phase=第一階段, timing=Early, play_type=HDP
```

### 1.2 聯賽識別（LeagueResolver）

```
用 (name_zh, phase) 查詢 leagues 表
  → 找到: 關聯既有聯賽
  → 沒找到: 回傳 PendingLeague，等使用者輸入唯一 code 後建立

注意: 不同階段視為獨立聯賽（如「哥斯甲第一階段」和「哥斯甲第四階段」是兩個聯賽）
```

### 1.3 賽季管理

```
用 season_year + phase 組成 label（如「2025第一階段」）
查詢該聯賽是否已有此 label 的賽季
  → 沒有: 建立新賽季，然後 recalculate_roles()
  → 已有: 直接使用

recalculate_roles():
  取該聯賽所有賽季，按 year_start 降序排列
  第 1 個 → role = current
  第 2 個 → role = previous
  其餘   → role = None
  每個聯賽最多一個 current + 一個 previous
```

### 1.4 資料匯入（MatchImporter）

```
讀取 Excel → DataFrame
  ↓
前處理（在記憶體中，不改原始檔案）:
  1. 簡繁轉換: 赢→贏, 输→輸, 不适用(平)→不適用(平) ...
  2. 方括號清除: [任意內容] → 空白
  3. 數字後綴清除: 主隊欄(B)和客隊欄(D)的尾部數字移除
  ↓
提取 MatchRecord（從 Row 2 開始，Row 1 是 metadata）:
  每列: 輪次(A), 主隊(B), 比分(C), 客隊(D), X值(E), 模擬結果(F), 連結(G)
  跳過: 輪次無效、主隊空、客隊空、X值非數字的列
  ↓
結算計算（為每筆紀錄填入 4 個欄位）:
  解析模擬結果文字的第一個字（前綴）和後續部分（後綴）:

  前綴 → home_away_direction:
    HDP: 「主」→ home,「客」→ away
    OU:  「大」→ home,「小」→ away

  後綴 → settlement_value + settlement_direction:
    包含「贏」→ direction = win
    包含「輸」→ direction = lose
    包含「半」→ value = 0.5，否則 value = 1.0

  target_team:
    home → 取 home_team（B欄）
    away → 取 away_team（D欄）

  有效結算文字（共 16 種）:
    HDP: 主贏, 主贏半, 主輸半, 主輸, 客贏, 客贏半, 客輸半, 客輸
    OU:  大贏, 大贏半, 大輸半, 大輸, 小贏, 小贏半, 小輸半, 小輸

  無效值（跳過）: 不適用, 不適用(平), 空字串
  ↓
UPSERT 至 match_records 表:
  先 DELETE 該 (season_instance_id, play_type, timing) 的舊資料
  再批量 INSERT 新資料
  整個操作在單一 transaction 中
```

---

## 二、ETL 計算流程

ETL 從 match_records 表讀取已處理的資料（不再讀 Excel）。
對每個啟用的聯賽執行以下流程。

### 2.1 整體編排（_process_league）

```
取得聯賽的 current 賽季和 previous 賽季
取得所有全域分組（global_groups 表）

對每個全域分組:
  取得該聯賽的 current 隊伍和 previous 隊伍（league_group_teams 表）
  如果本季和上季隊伍都為空 → 跳過此分組

從 match_records 讀取本季紀錄，按 (play_type, timing) 分組
從 match_records 讀取上季紀錄，按 (play_type, timing) 分組

--- 本季計算 ---
對每個 (play_type, timing):
  用本季 TeamGroup 列表拆分紀錄（Splitter）
  對每個分組:
    _process_team_group() → 分類 → 匯總 → 儲存 computation_result

--- 上季計算 ---
對每個 (play_type, timing):
  用上季 TeamGroup 列表拆分紀錄（Splitter）
  對每個分組:
    _process_team_group() → 分類 → 匯總 → 儲存 computation_result

--- 跨賽季決策 ---
_generate_decisions() → 五大區間 → 護級 → 強度 → 訊號 → 儲存 decision_result
```

### 2.2 隊名比對與拆分（Splitter）

```
兩種匹配模式:

HDP 用 "target" 模式:
  只看 target_team 是否在分組的隊伍清單中
  （target_team 由結算計算時根據「主/客」前綴決定）

OU 用 "participant" 模式:
  home_team 或 away_team 任一方在分組中即匹配

同一筆紀錄可以被分配到多個分組（如果兩隊分屬不同分組）
不在任何分組中的隊伍記錄為「未匹配」
```

### 2.3 X 值區間分類（Classifier）

```
預設 8 個分界點: [-0.24, -0.22, -0.15, -0.08, -0.03, 0.07, 0.15, 0.23]
產生 9 個區間:

  zone 1: X ≤ -0.24
  zone 2: -0.24 < X ≤ -0.22
  zone 3: -0.22 < X ≤ -0.15
  zone 4: -0.15 < X ≤ -0.08
  zone 5: -0.08 < X ≤ -0.03
  zone 6: -0.03 < X ≤ 0.07
  zone 7:  0.07 < X ≤ 0.15
  zone 8:  0.15 < X ≤ 0.23
  zone 9: X > 0.23

每筆紀錄根據 x_value 被分配到對應的 zone
```

### 2.4 輪次區段匯總（RoundBlockAggregator）

```
每 10 輪為一個區段（可設定），自動根據資料決定區段數

對每個區段、每個 zone (1~9):
  遍歷該區段內的紀錄，根據 (home_away_direction, settlement_direction) 累加:
    home + win  → zone.home_win  += settlement_value
    home + lose → zone.home_lose += settlement_value
    away + win  → zone.away_win  += settlement_value
    away + lose → zone.away_lose += settlement_value
    draw 或空   → 跳過

season_total(): 所有區段的 9 個 zone 逐欄加總
```

### 2.5 五大區間合併（FiveZoneGrouper）

```
預設映射: [[1], [2,3,4], [5,6], [7,8], [9]]

大區間 1 = zone 1 的 (home_win, home_lose, away_win, away_lose)
大區間 2 = zone 2 + zone 3 + zone 4 的四欄分別加總
大區間 3 = zone 5 + zone 6 的四欄分別加總
大區間 4 = zone 7 + zone 8 的四欄分別加總
大區間 5 = zone 9 的 (home_win, home_lose, away_win, away_lose)

輸出: 5 個 (home_win, home_lose, away_win, away_lose) tuple
```

### 2.6 跨賽季匯總（SeasonAggregator）

```
輸入: 本季 9 個 ZoneStats + 上季 9 個 ZoneStats（上季可為 None → 全零）
輸出: (previous, current, cross_season) 三組

cross_season[i] = previous[i] + current[i]（四欄分別加總）

注意: 五大區間合併分別對 previous 和 current 做，不是對 cross_season 做
```

### 2.7 決策流程（_decide_for_unit）

對每個 (聯賽 × 分組 × play_type × timing)，取得本季和上季的 computation_result，然後：

```
season_agg.aggregate(本季zones, 上季zones) → (prev_z, curr_z, cross_z)
five_zone.group(prev_z) → prev_five: 5 個 (p_hw, p_hl, p_aw, p_al)
five_zone.group(curr_z) → curr_five: 5 個 (c_hw, c_hl, c_aw, c_al)

對每個大區間 i (0~4):
  p_hw, p_hl, p_aw, p_al = prev_five[i]   ← 上季五大區間
  c_hw, c_hl, c_aw, c_al = curr_five[i]   ← 本季五大區間

  --- Home 方向 ---
  home_guard    = guard.evaluate(p_hw, p_hl, c_hw, c_hl)
  home_strength = strength.upgrade(home_guard, p_hw, p_hl, multiplier=2.0)
  home_signal   = signal.generate(home_guard, home_strength, p_hw, p_hl,
                                  ratio_threshold=1.4, direction_logic="greater")

  --- Away 方向 ---
  away_guard    = guard.evaluate(p_aw, p_al, c_aw, c_al)
  away_strength = strength.upgrade(away_guard, p_aw, p_al, multiplier=2.0)
  away_signal   = signal.generate(away_guard, away_strength, p_aw, p_al,
                                  ratio_threshold=1.4, direction_logic="less")
```

### 2.8 護級判定（GuardLevelEvaluator）

```
輸入: prev_win(pw), prev_lose(pl), curr_win(cw), curr_lose(cl)

if pw == pl:           → 護級 0（上季走水，含兩者皆為 0）
if cw == cl:           → 護級 1（本季走水，上季非走水）
if 方向一致:            → 護級 2
  （pw > pl 且 cw > cl）或（pw < pl 且 cl > cw 是錯的，應為 pw < pl 且 cw < cl）
if 方向相反:            → 護級 3

方向判定: win > lose → "win"方向, lose > win → "lose"方向
一致 = 上季方向 == 本季方向
```

### 2.9 強度升級（StrengthUpgrader）

```
輸入: guard_level, prev_win(pw), prev_lose(pl), multiplier(預設 2.0)

if guard != 2:  → strength = guard（直接返回）
if guard == 2:
  max_val = max(pw, pl)
  min_val = min(pw, pl)
  if min_val == 0 且 max_val > 0: → strength = 4（比值無限大）
  if max_val / min_val >= multiplier: → strength = 4
  否則: → strength = 2

注意: 使用上季數據(pw, pl)，不是跨賽季總和
```

### 2.10 訊號產生（SignalGenerator）

```
輸入: guard, strength, prev_win(pw), prev_lose(pl),
      ratio_threshold(預設 1.4), direction_logic("greater" 或 "less")

if guard == 0 或 guard == 3: → 空字串（無訊號）

--- 方向字母 ---
if direction_logic == "greater":  （Home 方向）
  pw > pl → "A",  pw < pl → "B"
if direction_logic == "less":     （Away 方向）
  pw < pl → "A",  pw > pl → "B"

--- 訊號數值 ---
if strength == 4:                              → 2
if guard == 2:
  ratio = max(pw,pl) / min(pw,pl)
  if ratio > ratio_threshold:                  → 1
  else:                                        → 0.5
if guard == 1:                                 → 0.2

--- 組合 ---
輸出: 字母 + 數值，如 "A2", "B0.5", "A0.2"
整數不帶小數點: "A2" 而非 "A2.0"
```

---

## 三、全域分組架構

```
global_groups 表:
  id, name(如 Top/Weak), display_name, display_order

league_group_teams 表:
  league_id × global_group_id × role(current/previous) → teams_json

ETL 流程中:
  本季計算 → 用 role="current" 的隊伍建構 TeamGroup
  上季計算 → 用 role="previous" 的隊伍建構 TeamGroup
  跨賽季決策 → 靠 global_group_id 匹配（不是靠 name 字串匹配）

Report 看板:
  頂層 Tab = 全域分組名稱（Top / Weak / ...）
  每個 Tab 下列出所有聯賽的 HDP/OU × Early/RT 決策結果
```

---

## 四、賽季生命週期

```
每個聯賽最多: 1 個 current + 1 個 previous

current 賽季:
  - 允許重新上傳資料（UPSERT 全量替換）
  - 隊伍分組可編輯

previous 賽季:
  - 唯讀，禁止重新上傳
  - 隊伍分組可編輯（因為是 league_group_teams 表，不綁定賽季）

賽季轉換:
  current → previous（原 previous 被覆蓋）
  建立新的空白 current
  新賽季的隊伍分組為空白，需使用者從 Team Pool 重新勾選
```

---

## 五、可設定參數

```
x_value_boundaries:           [-0.24, -0.22, -0.15, -0.08, -0.03, 0.07, 0.15, 0.23]
five_zone_mapping:            [[1], [2,3,4], [5,6], [7,8], [9]]
round_block_size:             10
guard_ratio_threshold:        1.4
strength_upgrade_multiplier:  2.0
settlement_values:            {贏:1.0, 贏半:0.5, 輸:1.0, 輸半:0.5, 走水:0.0}
```

---

## 六、Streamlit 頁面

```
app.py                  → 首頁：系統總覽、聯賽健康診斷、操作日誌
pages/
  2_報表看板.py          → 按分組 Tab 顯示所有聯賽的 5 大區間訊號（Home + Away）
  3_訊號追蹤.py          → 比較不同 ETL 版本的訊號變化
  4_檔案上傳.py          → 批量上傳 RPA Excel（FilenameParser → LeagueResolver → MatchImporter）
  5_ETL執行.py           → 勾選聯賽執行 ETL，顯示進度和結果摘要
  6_歷史紀錄.py          → ETL 執行歷史，可切換版本檢視
  7_聯賽管理.py          → 聯賽 CRUD、啟用/停用
  8_隊伍分組.py          → 全域分組管理 + 聯賽隊伍配置（從 Team Pool 勾選）
  9_參數設定.py          → 演算法參數調整、恢復預設值
  10_數據驗證.py         → 上傳舊系統 MST 檔案比對新舊結果
```
