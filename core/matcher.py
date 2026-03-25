"""TeamMatcher：根據 target_team 與隊伍清單比對，篩選匹配的比賽紀錄。

需求 7.3：對每個 Team_Group，將判定的隊伍名稱（target_team）與該分組的
隊伍清單進行比對，只保留匹配的賽事紀錄。
"""

import logging
from core.models import MatchRecord

logger = logging.getLogger(__name__)


class TeamMatcher:
    """隊名比對器：根據 target_team 篩選比賽紀錄。"""

    def match(
        self,
        records: list[MatchRecord],
        team_names: set[str],
    ) -> tuple[list[MatchRecord], set[str]]:
        """比對紀錄的 target_team 與隊伍名稱集合。

        A record matches if its target_team is in team_names.
        Records with empty target_team (e.g. skipped settlements) are excluded.

        Args:
            records: 比賽紀錄列表（需已設定 target_team）。
            team_names: 隊伍名稱集合。

        Returns:
            (matched_records, unmatched_team_names):
              - matched_records: target_team 在 team_names 中的紀錄
              - unmatched_team_names: 紀錄中出現但不在 team_names 中的隊伍名稱
        """
        matched: list[MatchRecord] = []
        all_target_teams: set[str] = set()

        for rec in records:
            if not rec.target_team:
                continue
            all_target_teams.add(rec.target_team)
            if rec.target_team in team_names:
                matched.append(rec)

        unmatched = all_target_teams - team_names

        logger.info(
            "隊名比對：%d/%d 筆匹配，%d 隊未匹配",
            len(matched), len(records), len(unmatched),
        )
        if unmatched:
            logger.warning("未匹配隊伍：%s", unmatched)

        return matched, unmatched
