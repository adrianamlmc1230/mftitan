"""League_Resolver：聯賽識別與建立模組。

根據 RPA 檔名解析結果，識別既有聯賽或建立新聯賽與賽季。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from core.config_store import ConfigStore
from core.models import ParsedFilename

logger = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    """聯賽解析結果。"""

    league_id: int
    season_instance_id: int
    is_new_league: bool
    is_new_season: bool


@dataclass
class PendingLeague:
    """待建立的新聯賽（等待使用者輸入 code）。"""

    name_zh: str            # 完整中文名如「澳大利亞澳超」
    phase: str | None


class LeagueResolver:
    """聯賽識別與建立。"""

    def __init__(self, config_store: ConfigStore):
        self.store = config_store

    def resolve(self, parsed: ParsedFilename) -> ResolveResult | PendingLeague:
        """識別或建立聯賽與賽季。

        Returns:
            ResolveResult: 聯賽已存在，已關聯賽季
            PendingLeague: 需要使用者輸入 code 才能建立新聯賽
        """
        phase = parsed.phase if parsed.phase else None

        league = self.store.find_league_by_identity(
            name_zh=parsed.name_zh,
            phase=phase,
        )

        if league is not None:
            season_id, is_new_season = self.ensure_season(league.id, parsed)
            return ResolveResult(
                league_id=league.id,
                season_instance_id=season_id,
                is_new_league=False,
                is_new_season=is_new_season,
            )

        # 聯賽不存在 → 回傳 PendingLeague
        return PendingLeague(
            name_zh=parsed.name_zh,
            phase=phase,
        )

    def create_league_with_code(
        self, pending: PendingLeague, code: str, continent: str = "",
    ) -> int:
        """使用者輸入 code 後建立新聯賽。

        Args:
            pending: 待建立的聯賽資訊
            code: 使用者輸入的唯一 code
            continent: 洲別（使用者手動設定，預設空字串）

        Returns:
            新建聯賽的 league_id

        Raises:
            ValueError: code 已存在
        """
        all_leagues = self.store.list_leagues()
        for league in all_leagues:
            if league.code == code:
                raise ValueError(f"code '{code}' 已存在，請輸入不同的 code")

        league_id = self.store.create_league(
            continent=continent,
            code=code,
            name_zh=pending.name_zh,
            phase=pending.phase,
        )
        return league_id

    def ensure_season(
        self, league_id: int, parsed: ParsedFilename
    ) -> tuple[int, bool]:
        """確保賽季存在，不存在則建立。

        Args:
            league_id: 聯賽 ID
            parsed: 解析後的檔名資訊

        Returns:
            (season_instance_id, is_new) 元組
        """
        label = self._build_season_label(parsed)
        year_start, year_end = self._parse_season_years(parsed.season_year)
        phase = parsed.phase if parsed.phase else None

        seasons = self.store.list_season_instances(league_id)
        for season in seasons:
            if season.label == label:
                return (season.id, False)

        season_id = self.store.create_season_instance(
            league_id=league_id,
            label=label,
            year_start=year_start,
            year_end=year_end,
            phase=phase,
        )

        self.recalculate_roles(league_id)
        return (season_id, True)

    def recalculate_roles(self, league_id: int) -> None:
        """重新計算聯賽所有賽季的 current/previous 角色。"""
        seasons = self.store.list_season_instances(league_id)
        if not seasons:
            return

        sorted_seasons = sorted(seasons, key=lambda s: s.year_start, reverse=True)

        for i, season in enumerate(sorted_seasons):
            if i == 0:
                role = "current"
            elif i == 1:
                role = "previous"
            else:
                role = None
            self.store.set_season_role(season.id, role)

    @staticmethod
    def _build_season_label(parsed: ParsedFilename) -> str:
        """建立賽季 label。格式：{season_year} 或 {season_year}{phase}"""
        phase_part = parsed.phase if parsed.phase else ""
        return f"{parsed.season_year}{phase_part}"

    @staticmethod
    def _parse_season_years(season_year: str) -> tuple[int, int | None]:
        """解析賽季年份字串。"""
        if "-" in season_year:
            parts = season_year.split("-")
            return (int(parts[0]), int(parts[1]))
        return (int(season_year), None)
