"""RPA 爬蟲 JSON 設定檔生成器。

根據 ConfigStore 中啟用的聯賽生成 RPA 爬蟲所需的 JSON 設定檔。

- generate_active(): 本季版（RPA_Active.json），時段=即+早，每聯賽 2 筆
- generate_full(): 完整版（RPA_Full.json），2 玩法 × 2 時段，每聯賽 4 筆

Validates: Requirements 21.1, 21.2, 21.3, 21.4, 21.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_store import ConfigStore
    from core.models import League, SeasonInstance

# 玩法對照：內部代碼 → RPA 中文名稱
_PLAY_TYPE_ZH = {"HDP": "亞讓", "OU": "總進球"}

# 時段對照：內部代碼 → RPA 中文名稱
_TIMING_ZH = {"Early": "早", "RT": "即+早"}

_BASE_URL = "https://zq.titan007.com/big"


class RpaJsonGenerator:
    """RPA JSON 設定檔生成器。"""

    def __init__(self, config_store: ConfigStore):
        self.store = config_store

    def generate_active(
        self, leagues: list[League] | None = None,
    ) -> list[list[str]]:
        """生成本季版 JSON（RPA_Active.json）。

        時段=即+早，每聯賽 2 筆（亞讓 + 總進球）。
        """
        if leagues is None:
            leagues = self.store.list_leagues(active_only=True)

        result: list[list[str]] = []
        for league in leagues:
            if not league.league_url_id:
                continue

            season = self._get_current_season(league.id)
            if not season:
                continue

            year_str = self._season_year_str(season)
            url = self._build_url(league, year_str)
            phase = league.phase or "第一階段"

            # 2 筆：HDP + OU，時段固定為 RT（即+早）
            for play_type in ("HDP", "OU"):
                result.append([
                    league.name_zh,
                    year_str,
                    url,
                    phase,
                    _TIMING_ZH["RT"],
                    _PLAY_TYPE_ZH[play_type],
                ])

        return result

    def generate_full(
        self, leagues: list[League] | None = None,
    ) -> list[list[str]]:
        """生成完整版 JSON（RPA_Full.json）。

        2 玩法 × 2 時段，每聯賽 4 筆。
        """
        if leagues is None:
            leagues = self.store.list_leagues(active_only=True)

        result: list[list[str]] = []
        for league in leagues:
            if not league.league_url_id:
                continue

            season = self._get_current_season(league.id)
            if not season:
                continue

            year_str = self._season_year_str(season)
            url = self._build_url(league, year_str)
            phase = league.phase or "第一階段"

            # 4 筆：2 玩法 × 2 時段
            for play_type in ("HDP", "OU"):
                for timing in ("Early", "RT"):
                    result.append([
                        league.name_zh,
                        year_str,
                        url,
                        phase,
                        _TIMING_ZH[timing],
                        _PLAY_TYPE_ZH[play_type],
                    ])

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_current_season(self, league_id: int) -> SeasonInstance | None:
        """取得聯賽的 current 賽季。"""
        seasons = self.store.list_season_instances(league_id)
        return next((s for s in seasons if s.role == "current"), None)

    @staticmethod
    def _season_year_str(season: SeasonInstance) -> str:
        """從賽季實例取得年份字串。"""
        if season.year_end and season.year_end != season.year_start:
            return f"{season.year_start}-{season.year_end}"
        return str(season.year_start)

    @staticmethod
    def _build_url(league: League, season_year: str) -> str:
        """根據 League_URL_Type 和 League_URL_ID 生成 URL。"""
        url_type = league.league_url_type or "League"
        return f"{_BASE_URL}/{url_type}/{season_year}/{league.league_url_id}.html"
