"""不一致隊名偵測與修正模組。

比對 league_group_teams 中的隊名與 Team Pool，
找出不存在於 Team Pool 的隊伍，並提供修正機制。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from core.config_store import ConfigStore
from core.models import GlobalGroup, LeagueGroupTeams

logger = logging.getLogger(__name__)


@dataclass
class MismatchEntry:
    """單筆不一致隊名記錄。"""

    league_id: int              # 聯賽 ID
    league_name: str            # 聯賽顯示名稱（如 "CHN1 - 中國中超"）
    group_name: str             # 全域分組名稱（如 "Top"）
    group_display_name: str | None  # 分組顯示名稱
    global_group_id: int        # 全域分組 ID
    role: str                   # "current" | "previous"
    team_name: str              # 不一致的隊名


@dataclass
class FixAction:
    """單筆修正操作。"""

    league_id: int              # 聯賽 ID
    group_name: str             # 全域分組名稱（用於摘要顯示）
    global_group_id: int        # 全域分組 ID
    role: str                   # "current" | "previous"
    old_team: str               # 要修正的隊名
    action: str                 # "replace" | "delete"
    new_team: str | None        # action="replace" 時的替換目標


def detect_mismatches(
    all_group_teams: list[LeagueGroupTeams],
    team_pool: set[str],
    group_lookup: dict[int, GlobalGroup],
    league_id: int = 0,
    league_name: str = "",
) -> list[MismatchEntry]:
    """比對所有分組隊伍與 Team Pool，回傳不存在於 pool 的隊名清單。

    純函數，無副作用。

    Args:
        all_group_teams: 該聯賽所有 LeagueGroupTeams 記錄
        team_pool: Team Pool 隊名集合（match_records 中出現過的所有隊名）
        group_lookup: 全域分組 ID → GlobalGroup 對照表
        league_id: 聯賽 ID（用於跨聯賽總覽）
        league_name: 聯賽顯示名稱（用於跨聯賽總覽）

    Returns:
        MismatchEntry 列表，每筆包含聯賽、分組資訊、角色、不一致隊名
    """
    entries: list[MismatchEntry] = []
    for lgt in all_group_teams:
        group = group_lookup.get(lgt.global_group_id)
        group_name = group.name if group else f"unknown-{lgt.global_group_id}"
        group_display_name = group.display_name if group else None

        for team in lgt.teams:
            if team not in team_pool:
                entries.append(
                    MismatchEntry(
                        league_id=league_id,
                        league_name=league_name,
                        group_name=group_name,
                        group_display_name=group_display_name,
                        global_group_id=lgt.global_group_id,
                        role=lgt.role,
                        team_name=team,
                    )
                )
    return entries


def validate_fixes(
    fixes: list[FixAction],
    all_group_teams: list[LeagueGroupTeams],
) -> list[str]:
    """驗證修正操作，回傳錯誤訊息列表（空 = 通過）。

    純函數，無副作用。

    檢查項目：
    1. 替換目標是否已存在於同一 (global_group_id, role) 的 group config（防止重複隊名）
    2. 同一 (global_group_id, role, old_team) 是否有重複的修正操作

    Args:
        fixes: 修正操作列表
        all_group_teams: 該聯賽所有 LeagueGroupTeams 記錄

    Returns:
        錯誤訊息列表，空列表表示驗證通過
    """
    errors: list[str] = []

    # Build lookup: (global_group_id, role) -> set of team names
    group_teams_lookup: dict[tuple[int, str], set[str]] = {}
    for lgt in all_group_teams:
        key = (lgt.global_group_id, lgt.role)
        group_teams_lookup[key] = set(lgt.teams)

    # Check 1: duplicate fix operations on the same (global_group_id, role, old_team)
    seen_fix_keys: set[tuple[int, str, str]] = set()
    for fix in fixes:
        fix_key = (fix.global_group_id, fix.role, fix.old_team)
        if fix_key in seen_fix_keys:
            errors.append(
                f"重複的修正操作：分組「{fix.group_name}」角色「{fix.role}」"
                f"中的隊名「{fix.old_team}」有多筆修正"
            )
        seen_fix_keys.add(fix_key)

    # Check 2: replace target already exists in the same group config
    for fix in fixes:
        if fix.action != "replace" or fix.new_team is None:
            continue
        group_key = (fix.global_group_id, fix.role)
        existing_teams = group_teams_lookup.get(group_key, set())
        if fix.new_team in existing_teams and fix.new_team != fix.old_team:
            errors.append(
                f"替換目標重複：分組「{fix.group_name}」角色「{fix.role}」"
                f"中已存在隊名「{fix.new_team}」，無法將「{fix.old_team}」替換為「{fix.new_team}」"
            )

    return errors


def apply_fixes(
    store: ConfigStore,
    league_id: int,
    fixes: list[FixAction],
) -> dict[str, list[str]]:
    """在 transaction 中套用所有修正，回傳變更摘要。

    對每個受影響的 (global_group_id, role) 組合：
    1. 讀取現有隊伍列表
    2. 套用替換/刪除操作
    3. 寫回更新後的隊伍列表

    使用 transaction 確保原子性：全部成功才 commit，任一失敗則 rollback。

    Args:
        store: ConfigStore 實例
        league_id: 聯賽 ID
        fixes: 修正操作列表

    Returns:
        摘要 dict，key 為 "{group_name}/{role}"，value 為變更描述列表

    Raises:
        RuntimeError: 資料庫寫入失敗時拋出，內部已 rollback
    """
    if not fixes:
        return {}

    summary: dict[str, list[str]] = {}

    # Group fixes by (global_group_id, role) to batch process
    grouped: dict[tuple[int, str], list[FixAction]] = {}
    for fix in fixes:
        key = (fix.global_group_id, fix.role)
        grouped.setdefault(key, []).append(fix)

    store.begin_transaction()
    try:
        for (global_group_id, role), group_fixes in grouped.items():
            # Read current teams for this group
            current_teams = store.get_league_group_teams(
                league_id, global_group_id, role
            )
            updated_teams = list(current_teams)
            group_name = group_fixes[0].group_name
            summary_key = f"{group_name}/{role}"
            changes: list[str] = []

            for fix in group_fixes:
                if fix.action == "replace" and fix.new_team is not None:
                    # Replace old_team with new_team, preserving position
                    if fix.old_team in updated_teams:
                        idx = updated_teams.index(fix.old_team)
                        updated_teams[idx] = fix.new_team
                        changes.append(
                            f"替換「{fix.old_team}」→「{fix.new_team}」"
                        )
                        logger.debug(
                            "Replace '%s' -> '%s' in group %s/%s",
                            fix.old_team, fix.new_team, group_name, role,
                        )
                    else:
                        logger.warning(
                            "隊名「%s」不存在於分組 %s/%s，跳過替換",
                            fix.old_team, group_name, role,
                        )
                elif fix.action == "delete":
                    if fix.old_team in updated_teams:
                        updated_teams.remove(fix.old_team)
                        changes.append(f"刪除「{fix.old_team}」")
                        logger.debug(
                            "Delete '%s' from group %s/%s",
                            fix.old_team, group_name, role,
                        )
                    else:
                        logger.warning(
                            "隊名「%s」不存在於分組 %s/%s，跳過刪除",
                            fix.old_team, group_name, role,
                        )

            if changes:
                summary[summary_key] = changes
                # Write back using raw SQL to avoid premature commit
                # (set_league_group_teams calls conn.commit() directly,
                #  which would break our transaction atomicity)
                teams_json = json.dumps(updated_teams, ensure_ascii=False)
                store._conn.execute(
                    "INSERT INTO league_group_teams "
                    "(league_id, global_group_id, role, teams_json, updated_at) "
                    "VALUES (?, ?, ?, ?, datetime('now')) "
                    "ON CONFLICT(league_id, global_group_id, role) "
                    "DO UPDATE SET teams_json = excluded.teams_json, "
                    "updated_at = excluded.updated_at",
                    (league_id, global_group_id, role, teams_json),
                )

        # Record audit log within the same transaction
        details = json.dumps(
            {"league_id": league_id, "changes": summary},
            ensure_ascii=False,
        )
        store._conn.execute(
            "INSERT INTO audit_logs (action, entity_type, entity_id, details) "
            "VALUES (?, ?, ?, ?)",
            ("fix_team_names", "league", league_id, details),
        )

        store.commit_transaction()
    except Exception as exc:
        store.rollback_transaction()
        raise RuntimeError(f"修正操作失敗，已回滾所有變更：{exc}") from exc

    return summary
