"""QualityChecker：品質檢查，檢測空數據、隊名不一致等問題。"""

import logging
from dataclasses import dataclass, field
from core.models import ZoneStats, TeamGroup

logger = logging.getLogger(__name__)


@dataclass
class QualityIssue:
    """品質問題紀錄。"""
    severity: str           # 'warning' or 'error'
    issue_type: str         # 'empty_data', 'team_mismatch'
    description: str
    details: dict = field(default_factory=dict)


class QualityChecker:
    """品質檢查器。"""

    def check_empty_data(
        self,
        zones: list[ZoneStats],
        league_code: str = "",
        group_name: str = "",
    ) -> list[QualityIssue]:
        """檢查所有區間統計是否全為 0。"""
        issues: list[QualityIssue] = []
        if zones and all(
            z.home_win == 0 and z.home_lose == 0
            and z.away_win == 0 and z.away_lose == 0
            for z in zones
        ):
            issues.append(QualityIssue(
                severity="warning",
                issue_type="empty_data",
                description=f"聯賽 {league_code} 分組 {group_name} 所有區間統計為 0",
                details={"league_code": league_code, "group_name": group_name},
            ))
        return issues

    def check_team_consistency(
        self,
        groups_by_timing: dict[str, list[TeamGroup]],
    ) -> list[QualityIssue]:
        """檢查同聯賽同分組在不同時段的隊名一致性。"""
        issues: list[QualityIssue] = []
        timings = list(groups_by_timing.keys())
        if len(timings) < 2:
            return issues

        base_timing = timings[0]
        base_groups = {g.name: set(g.teams) for g in groups_by_timing[base_timing]}

        for timing in timings[1:]:
            other_groups = {g.name: set(g.teams) for g in groups_by_timing[timing]}
            for name, base_teams in base_groups.items():
                other_teams = other_groups.get(name, set())
                if base_teams != other_teams:
                    diff = base_teams.symmetric_difference(other_teams)
                    issues.append(QualityIssue(
                        severity="warning",
                        issue_type="team_mismatch",
                        description=f"分組 {name} 在 {base_timing} 與 {timing} 的隊名不一致",
                        details={
                            "group_name": name,
                            "timings": [base_timing, timing],
                            "diff_teams": list(diff),
                        },
                    ))
        return issues
