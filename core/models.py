"""資料模型定義：使用 Python dataclass 定義所有資料傳輸物件。"""

from dataclasses import dataclass, field


@dataclass
class League:
    """聯賽，系統的頂層管理單位。"""

    id: int
    continent: str          # 'AFR','AME','ASI','EUR'
    code: str               # 'ENG1'
    name_zh: str            # '澳大利亞澳超'（完整中文名，不拆分國家）
    phase: str | None       # 聯賽階段（如「第一階段」）
    league_url_id: str | None   # RPA 爬蟲 URL ID
    league_url_type: str | None # 'League' 或 'SubLeague'
    is_active: bool


@dataclass
class SeasonInstance:
    """賽季實例，每個聯賽下的具體賽季。"""

    id: int
    league_id: int
    label: str              # '2025-2026第一階段'
    year_start: int
    year_end: int | None
    phase: str | None
    role: str | None        # 'current', 'previous', None


@dataclass
class TeamGroup:
    """隊伍分組，使用者自訂的計算分組。"""

    id: int
    season_instance_id: int
    name: str               # 'Top', 'Weak', 'Mid'
    display_name: str | None
    teams: list[str] = field(default_factory=list)


@dataclass
class GlobalGroup:
    """全域分組名稱。"""

    id: int
    name: str               # 'Top', 'Weak'
    display_name: str | None
    display_order: int = 0


@dataclass
class LeagueGroupTeams:
    """聯賽 × 分組 × 角色的隊伍配置。"""

    id: int
    league_id: int
    global_group_id: int
    role: str               # 'current' | 'previous'
    teams: list[str] = field(default_factory=list)  # parsed from teams_json


@dataclass
class FilePath:
    """RPA 檔案路徑設定。"""

    id: int
    season_instance_id: int
    play_type: str          # 'HDP' or 'OU'
    timing: str             # 'Early' or 'RT'
    file_path: str
    updated_at: str


@dataclass
class MatchRecord:
    """單場賽事紀錄（前處理後）。"""

    round_num: int          # 輪次（A欄）
    home_team: str          # 主隊（B欄）
    away_team: str          # 客隊（D欄）
    x_value: float          # X 值（E欄）
    settlement: str         # 結算結果文字（F欄）
    score: str = ''         # 比分（C欄）
    link: str = ''          # 連結（G欄）
    play_type: str = ''     # 'HDP' or 'OU'（用於方向判定）
    settlement_value: float = 0.0
    settlement_direction: str = ''   # 'win' or 'lose'
    home_away_direction: str = ''    # 'home' or 'away'（主客場方向）
    target_team: str = ''            # 被處理的隊伍名稱


@dataclass
class ZoneStats:
    """單一 X 值區間的統計（Home/Away 方向拆分）。"""

    zone_id: int            # 1~9
    home_win: float = 0.0   # Home 方向贏類
    home_lose: float = 0.0  # Home 方向輸類
    away_win: float = 0.0   # Away 方向贏類
    away_lose: float = 0.0  # Away 方向輸類


@dataclass
class DecisionZone:
    """單一 5 大區間的決策結果（Home/Away 方向拆分）。"""

    zone_id: int            # 1~5
    prev_home_win: float = 0.0
    prev_home_lose: float = 0.0
    prev_away_win: float = 0.0
    prev_away_lose: float = 0.0
    curr_home_win: float = 0.0
    curr_home_lose: float = 0.0
    curr_away_win: float = 0.0
    curr_away_lose: float = 0.0
    home_guard: int = 0
    away_guard: int = 0
    home_strength: int = 0
    away_strength: int = 0
    home_signal: str = ''
    away_signal: str = ''


@dataclass
class ParsedFilename:
    """從 RPA 檔名解析出的結構化資訊。"""

    name_zh: str            # '中國中超'（年份前完整文字，不拆分國家）
    season_year: str        # '2025'
    phase: str              # '第一階段'
    timing: str             # 'Early' or 'RT'
    play_type: str          # 'HDP' or 'OU'
    original_path: str      # 原始檔案路徑


@dataclass
class ComputationUnit:
    """最小計算粒度 = 聯賽 × 賽季實例 × 隊伍分組 × 玩法 × 時段。"""

    league: League
    season_instance: SeasonInstance
    team_group: TeamGroup
    play_type: str          # 'HDP' or 'OU'
    timing: str             # 'Early' or 'RT'
    records: list[MatchRecord] = field(default_factory=list)


@dataclass
class RoundBlockStats:
    """單一輪次區段的統計。"""

    block_id: int           # 1~6
    round_start: int
    round_end: int
    zones: list[ZoneStats] = field(default_factory=list)
