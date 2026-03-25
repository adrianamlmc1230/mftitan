"""RecordSplitter：將比賽紀錄按 TeamGroup 拆分。

支援兩種匹配模式：
  - "participant"（預設，用於 OU）：home_team 或 away_team 任一方在分組中即匹配。
  - "target"（用於 HDP）：只有 target_team 在分組中才匹配。
    target_team 由結算方向決定（主→主隊，客→客隊）。
"""

import logging
from core.models import MatchRecord, TeamGroup

logger = logging.getLogger(__name__)


class RecordSplitter:
    """紀錄拆分器：將紀錄按 TeamGroup 分配。"""

    def split(
        self,
        records: list[MatchRecord],
        team_groups: list[TeamGroup],
        match_mode: str = "participant",
    ) -> tuple[dict[int, list[MatchRecord]], set[str]]:
        """將紀錄按隊伍分組拆分。

        Args:
            records: 比賽紀錄列表。
            team_groups: 隊伍分組列表。
            match_mode: 匹配模式。
                "participant"：home 或 away 任一方在分組中即匹配（OU 用）。
                "target"：只有 target_team 在分組中才匹配（HDP 用）。

        Returns:
            (dict[group_id, list[MatchRecord]], unmatched_team_names):
              - dict: 每個分組 ID 對應的匹配紀錄列表
              - set: 紀錄中出現但不在任何分組中的隊伍名稱
        """
        # Build team -> set of group_ids lookup
        team_to_groups: dict[str, set[int]] = {}
        for tg in team_groups:
            for team in tg.teams:
                team_to_groups.setdefault(team, set()).add(tg.id)

        result: dict[int, list[MatchRecord]] = {tg.id: [] for tg in team_groups}
        all_teams: set[str] = set()
        all_known: set[str] = set(team_to_groups.keys())

        for rec in records:
            all_teams.add(rec.home_team)
            all_teams.add(rec.away_team)

            matched_gids: set[int] = set()

            if match_mode == "target":
                # HDP: only match on target_team
                if rec.target_team:
                    gids = team_to_groups.get(rec.target_team)
                    if gids:
                        matched_gids.update(gids)
            else:
                # OU (participant): match on home OR away
                for team in (rec.home_team, rec.away_team):
                    gids = team_to_groups.get(team)
                    if gids:
                        matched_gids.update(gids)

            for gid in matched_gids:
                result[gid].append(rec)

        unmatched = all_teams - all_known

        for tg in team_groups:
            logger.info(
                "分組 '%s' (id=%d, mode=%s)：分配 %d 筆紀錄",
                tg.name, tg.id, match_mode, len(result[tg.id]),
            )
        if unmatched:
            logger.warning("未匹配隊伍 (%d 隊)：%s", len(unmatched), unmatched)

        return result, unmatched
