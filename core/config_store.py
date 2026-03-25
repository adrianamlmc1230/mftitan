"""Config_Store：SQLite CRUD 操作封裝，管理聯賽、賽季、隊伍分組、演算法參數與 ETL 紀錄。"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.models import (
    FilePath,
    GlobalGroup,
    League,
    LeagueGroupTeams,
    MatchRecord,
    SeasonInstance,
    TeamGroup,
)

logger = logging.getLogger(__name__)

# 專案根目錄（football-quant-v2/）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS leagues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    continent     TEXT NOT NULL CHECK(continent IN ('AFR','AME','ASI','EUR','')),
    code          TEXT NOT NULL UNIQUE,
    name_zh       TEXT NOT NULL,
    phase         TEXT,
    league_url_id TEXT,
    league_url_type TEXT DEFAULT 'League' CHECK(league_url_type IN ('League','SubLeague')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS season_instances (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id     INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    year_start    INTEGER,
    year_end      INTEGER,
    phase         TEXT,
    role          TEXT CHECK(role IN ('current','previous',NULL)),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(league_id, label)
);

CREATE TABLE IF NOT EXISTS team_groups (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    display_name        TEXT,
    display_order       INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(season_instance_id, name)
);

CREATE TABLE IF NOT EXISTS teams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    team_group_id   INTEGER NOT NULL REFERENCES team_groups(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    display_order   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(team_group_id, name)
);

CREATE TABLE IF NOT EXISTS file_paths (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
    play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
    timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
    file_path           TEXT NOT NULL,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(season_instance_id, play_type, timing)
);

CREATE TABLE IF NOT EXISTS algo_params (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    param_key     TEXT NOT NULL UNIQUE,
    param_value   TEXT NOT NULL,
    description   TEXT,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS etl_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    status          TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running','completed','failed')),
    scope_leagues   TEXT,
    params_snapshot TEXT NOT NULL,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS computation_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    etl_run_id          INTEGER NOT NULL REFERENCES etl_runs(id) ON DELETE CASCADE,
    league_id           INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
    team_group_id       INTEGER NOT NULL,
    play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
    timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
    zone_data           TEXT NOT NULL,
    round_block_data    TEXT NOT NULL,
    season_total_win    REAL NOT NULL DEFAULT 0,
    season_total_lose   REAL NOT NULL DEFAULT 0,
    global_group_id     INTEGER REFERENCES global_groups(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_comp_results_run ON computation_results(etl_run_id);
CREATE INDEX IF NOT EXISTS idx_comp_results_league ON computation_results(league_id, play_type, timing);

CREATE TABLE IF NOT EXISTS decision_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    etl_run_id          INTEGER NOT NULL REFERENCES etl_runs(id) ON DELETE CASCADE,
    league_id           INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    team_group_id       INTEGER NOT NULL,
    play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
    timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
    five_zone_data      TEXT NOT NULL,
    guard_levels        TEXT NOT NULL,
    strength_levels     TEXT NOT NULL,
    home_signals        TEXT NOT NULL,
    away_signals        TEXT NOT NULL,
    global_group_id     INTEGER REFERENCES global_groups(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decision_run ON decision_results(etl_run_id);

CREATE TABLE IF NOT EXISTS quality_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    etl_run_id      INTEGER NOT NULL REFERENCES etl_runs(id) ON DELETE CASCADE,
    league_id       INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    severity        TEXT NOT NULL CHECK(severity IN ('warning','error')),
    issue_type      TEXT NOT NULL,
    description     TEXT NOT NULL,
    details         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS match_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    season_instance_id  INTEGER NOT NULL REFERENCES season_instances(id) ON DELETE CASCADE,
    play_type           TEXT NOT NULL CHECK(play_type IN ('HDP','OU')),
    timing              TEXT NOT NULL CHECK(timing IN ('Early','RT')),
    round               INTEGER NOT NULL,
    home_team           TEXT NOT NULL,
    score               TEXT,
    away_team           TEXT NOT NULL,
    x_value             REAL NOT NULL,
    sim_result          TEXT,
    link                TEXT,
    settlement_value    REAL NOT NULL DEFAULT 0,
    settlement_direction TEXT NOT NULL DEFAULT '',
    home_away_direction TEXT NOT NULL DEFAULT '',
    target_team         TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_match_records_query
    ON match_records(season_instance_id, play_type, timing);

CREATE TABLE IF NOT EXISTS global_groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    display_name  TEXT,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS league_group_teams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id       INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    global_group_id INTEGER NOT NULL REFERENCES global_groups(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('current','previous')),
    teams_json      TEXT NOT NULL DEFAULT '[]',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(league_id, global_group_id, role)
);

CREATE INDEX IF NOT EXISTS idx_lgt_league ON league_group_teams(league_id);
CREATE INDEX IF NOT EXISTS idx_lgt_group ON league_group_teams(global_group_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   INTEGER,
    details     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_time ON audit_logs(created_at);
"""


class ConfigStore:
    """設定儲存管理器，封裝 SQLite 操作。"""

    def __init__(self, db_path: str = "db/quant.db"):
        # Support both relative (to project root) and absolute paths
        p = Path(db_path)
        if p.is_absolute():
            full_path = p
        else:
            full_path = _PROJECT_ROOT / db_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(full_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._in_transaction = False
        self.init_db()

    def begin_transaction(self) -> None:
        """開始手動 transaction。在此期間 save 方法不會自動 commit。"""
        self._conn.execute("BEGIN")
        self._in_transaction = True

    def commit_transaction(self) -> None:
        """提交手動 transaction。"""
        self._conn.execute("COMMIT")
        self._in_transaction = False

    def rollback_transaction(self) -> None:
        """回滾手動 transaction。"""
        self._conn.execute("ROLLBACK")
        self._in_transaction = False

    def _auto_commit(self) -> None:
        """若非手動 transaction 模式，自動 commit。"""
        if not self._in_transaction:
            self._conn.commit()

    def init_db(self) -> None:
        """建立所有資料表（如不存在），並初始化預設參數與執行 migration。"""
        self._conn.executescript(_CREATE_TABLES_SQL)
        self._conn.commit()
        # Run schema migrations for existing databases
        self._migrate()
        # Auto-load default params if table is empty
        count = self._conn.execute("SELECT COUNT(*) FROM algo_params").fetchone()[0]
        if count == 0:
            self.reset_params_to_default()

    # ------------------------------------------------------------------
    # Schema Migration
    # ------------------------------------------------------------------

    def _get_schema_version(self) -> int:
        """取得目前的 schema 版本號（使用 PRAGMA user_version）。"""
        row = self._conn.execute("PRAGMA user_version").fetchone()
        return row[0] if row else 0

    def _set_schema_version(self, version: int) -> None:
        """設定 schema 版本號。"""
        self._conn.execute(f"PRAGMA user_version = {int(version)}")
        self._conn.commit()

    def _migrate(self) -> None:
        """執行版本化 schema migration。失敗時記錄錯誤，不修改版本號，下次啟動重試。"""
        version = self._get_schema_version()

        if version < 2:
            try:
                # v2: 新增 match_records 表、leagues.phase 欄位與唯一索引
                cols = [
                    row[1]
                    for row in self._conn.execute("PRAGMA table_info(leagues)").fetchall()
                ]
                if "phase" not in cols:
                    self._conn.execute("ALTER TABLE leagues ADD COLUMN phase TEXT")
                self._conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_leagues_identity "
                    "ON leagues(name_zh, COALESCE(phase, ''))"
                )
                self._conn.commit()
                self._set_schema_version(2)
            except Exception:
                logger.error("Schema migration to v2 failed", exc_info=True)

        if version < 3:
            try:
                # v3: 移除 country 欄位，合併 country+name_zh 為新 name_zh
                cols = [
                    row[1]
                    for row in self._conn.execute("PRAGMA table_info(leagues)").fetchall()
                ]
                if "country" in cols:
                    # 重建表以移除 country（SQLite 不支援 DROP COLUMN < 3.35）
                    # 暫時關閉外鍵約束以避免 CASCADE 刪除關聯資料
                    self._conn.execute("PRAGMA foreign_keys=OFF")
                    self._conn.executescript("""
                        DROP INDEX IF EXISTS idx_leagues_identity;
                        ALTER TABLE leagues RENAME TO _leagues_old;
                        CREATE TABLE leagues (
                            id            INTEGER PRIMARY KEY AUTOINCREMENT,
                            continent     TEXT NOT NULL CHECK(continent IN ('AFR','AME','ASI','EUR','')),
                            code          TEXT NOT NULL UNIQUE,
                            name_zh       TEXT NOT NULL,
                            phase         TEXT,
                            league_url_id TEXT,
                            league_url_type TEXT DEFAULT 'League' CHECK(league_url_type IN ('League','SubLeague')),
                            is_active     INTEGER NOT NULL DEFAULT 1,
                            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
                        );
                        INSERT INTO leagues (id, continent, code, name_zh, phase, league_url_id, league_url_type, is_active, created_at, updated_at)
                            SELECT id, continent, code, country || name_zh, phase, league_url_id, league_url_type, is_active, created_at, updated_at
                            FROM _leagues_old;
                        DROP TABLE _leagues_old;
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_leagues_identity
                            ON leagues(name_zh, COALESCE(phase, ''));
                    """)
                    self._conn.execute("PRAGMA foreign_keys=ON")
                else:
                    # country 已不存在，只需確保唯一索引正確
                    self._conn.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_leagues_identity "
                        "ON leagues(name_zh, COALESCE(phase, ''))"
                    )
                self._conn.commit()
                self._set_schema_version(3)
            except Exception:
                logger.error("Schema migration to v3 failed", exc_info=True)

        if version < 4:
            try:
                # v4: 新增 global_groups / league_group_teams 表，
                #     decision_results / computation_results 新增 global_group_id，
                #     從舊 team_groups 遷移資料。

                # 1. 建立 global_groups 表
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS global_groups (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        name          TEXT NOT NULL UNIQUE,
                        display_name  TEXT,
                        display_order INTEGER NOT NULL DEFAULT 0,
                        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)

                # 2. 建立 league_group_teams 表（含索引）
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS league_group_teams (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        league_id       INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
                        global_group_id INTEGER NOT NULL REFERENCES global_groups(id) ON DELETE CASCADE,
                        role            TEXT NOT NULL CHECK(role IN ('current','previous')),
                        teams_json      TEXT NOT NULL DEFAULT '[]',
                        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                        UNIQUE(league_id, global_group_id, role)
                    )
                """)
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lgt_league "
                    "ON league_group_teams(league_id)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_lgt_group "
                    "ON league_group_teams(global_group_id)"
                )

                # 3. decision_results 新增 global_group_id 欄位
                dr_cols = [
                    row[1]
                    for row in self._conn.execute(
                        "PRAGMA table_info(decision_results)"
                    ).fetchall()
                ]
                if "global_group_id" not in dr_cols:
                    self._conn.execute(
                        "ALTER TABLE decision_results "
                        "ADD COLUMN global_group_id INTEGER REFERENCES global_groups(id)"
                    )

                # 4. computation_results 新增 global_group_id 欄位
                cr_cols = [
                    row[1]
                    for row in self._conn.execute(
                        "PRAGMA table_info(computation_results)"
                    ).fetchall()
                ]
                if "global_group_id" not in cr_cols:
                    self._conn.execute(
                        "ALTER TABLE computation_results "
                        "ADD COLUMN global_group_id INTEGER REFERENCES global_groups(id)"
                    )

                # 5. 從舊 team_groups 遷移資料
                old_names = self._conn.execute(
                    "SELECT DISTINCT name FROM team_groups"
                ).fetchall()
                for (name,) in old_names:
                    # 5a. 建立 global_groups 記錄
                    self._conn.execute(
                        "INSERT OR IGNORE INTO global_groups (name) VALUES (?)",
                        (name,),
                    )

                # 取得 global_groups name→id 對照
                gg_map: dict[str, int] = {}
                for row in self._conn.execute(
                    "SELECT id, name FROM global_groups"
                ).fetchall():
                    gg_map[row[1]] = row[0]

                # 5b. 對每個舊 team_group，找到 league_id 和 role，寫入 league_group_teams
                old_groups = self._conn.execute("""
                    SELECT tg.id, tg.name, si.league_id, si.role
                    FROM team_groups tg
                    JOIN season_instances si ON si.id = tg.season_instance_id
                    WHERE si.role IS NOT NULL
                """).fetchall()

                for tg_id, tg_name, league_id, role in old_groups:
                    gg_id = gg_map.get(tg_name)
                    if gg_id is None:
                        continue
                    # 收集該 team_group 的隊伍
                    team_rows = self._conn.execute(
                        "SELECT name FROM teams WHERE team_group_id = ? ORDER BY display_order",
                        (tg_id,),
                    ).fetchall()
                    teams_json = json.dumps([r[0] for r in team_rows], ensure_ascii=False)
                    self._conn.execute(
                        "INSERT OR IGNORE INTO league_group_teams "
                        "(league_id, global_group_id, role, teams_json) "
                        "VALUES (?, ?, ?, ?)",
                        (league_id, gg_id, role, teams_json),
                    )

                # 6. 更新 decision_results / computation_results 的 global_group_id
                self._conn.execute("""
                    UPDATE decision_results
                    SET global_group_id = (
                        SELECT gg.id
                        FROM team_groups tg
                        JOIN global_groups gg ON gg.name = tg.name
                        WHERE tg.id = decision_results.team_group_id
                    )
                    WHERE global_group_id IS NULL
                      AND team_group_id IS NOT NULL
                """)
                self._conn.execute("""
                    UPDATE computation_results
                    SET global_group_id = (
                        SELECT gg.id
                        FROM team_groups tg
                        JOIN global_groups gg ON gg.name = tg.name
                        WHERE tg.id = computation_results.team_group_id
                    )
                    WHERE global_group_id IS NULL
                      AND team_group_id IS NOT NULL
                """)

                self._conn.commit()
                self._set_schema_version(4)
            except Exception:
                logger.error("Schema migration to v4 failed", exc_info=True)

    # ------------------------------------------------------------------
    # 聯賽 CRUD
    # ------------------------------------------------------------------

    def list_leagues(
        self, continent: str | None = None, active_only: bool = True
    ) -> list[League]:
        sql = "SELECT * FROM leagues WHERE 1=1"
        params: list[Any] = []
        if continent:
            sql += " AND continent = ?"
            params.append(continent)
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY continent, code"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_league(r) for r in rows]

    def get_league(self, league_id: int) -> League | None:
        row = self._conn.execute(
            "SELECT * FROM leagues WHERE id = ?", (league_id,)
        ).fetchone()
        return self._row_to_league(row) if row else None

    def create_league(
        self,
        continent: str,
        code: str,
        name_zh: str,
        phase: str | None = None,
        league_url_id: str | None = None,
        league_url_type: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO leagues (continent, code, name_zh, phase, league_url_id, league_url_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (continent, code, name_zh, phase, league_url_id, league_url_type),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_league(self, league_id: int, **kwargs: Any) -> None:
        allowed = {
            "continent", "code", "name_zh", "phase",
            "is_active", "league_url_id", "league_url_type",
        }
        sets = []
        vals: list[Any] = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        sets.append("updated_at = datetime('now')")
        vals.append(league_id)
        self._conn.execute(
            f"UPDATE leagues SET {', '.join(sets)} WHERE id = ?", vals
        )
        self._conn.commit()

    def delete_league(self, league_id: int) -> None:
        self._conn.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
        self._conn.commit()

    @staticmethod
    def _row_to_league(row: sqlite3.Row) -> League:
        return League(
            id=row["id"],
            continent=row["continent"],
            code=row["code"],
            name_zh=row["name_zh"],
            phase=row["phase"],
            league_url_id=row["league_url_id"],
            league_url_type=row["league_url_type"],
            is_active=bool(row["is_active"]),
        )

    # ------------------------------------------------------------------
    # 賽季實例 CRUD
    # ------------------------------------------------------------------

    def list_season_instances(self, league_id: int) -> list[SeasonInstance]:
        rows = self._conn.execute(
            "SELECT * FROM season_instances WHERE league_id = ? ORDER BY id DESC",
            (league_id,),
        ).fetchall()
        return [self._row_to_season(r) for r in rows]

    def create_season_instance(
        self,
        league_id: int,
        label: str,
        year_start: int,
        year_end: int | None = None,
        phase: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO season_instances (league_id, label, year_start, year_end, phase) "
            "VALUES (?, ?, ?, ?, ?)",
            (league_id, label, year_start, year_end, phase),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def set_season_role(self, season_instance_id: int, role: str | None) -> None:
        """設定賽季角色。同一聯賽內同一 role 只能有一個。"""
        row = self._conn.execute(
            "SELECT league_id FROM season_instances WHERE id = ?",
            (season_instance_id,),
        ).fetchone()
        if not row:
            return
        league_id = row["league_id"]
        if role is not None:
            # 清除同聯賽中相同 role 的其他賽季
            self._conn.execute(
                "UPDATE season_instances SET role = NULL, updated_at = datetime('now') "
                "WHERE league_id = ? AND role = ?",
                (league_id, role),
            )
        # 設定目標賽季的 role
        self._conn.execute(
            "UPDATE season_instances SET role = ?, updated_at = datetime('now') WHERE id = ?",
            (role, season_instance_id),
        )
        self._conn.commit()

    def get_current_previous_pair(
        self, league_id: int
    ) -> tuple[SeasonInstance | None, SeasonInstance | None]:
        """回傳 (current, previous) 賽季實例。"""
        current = None
        previous = None
        rows = self._conn.execute(
            "SELECT * FROM season_instances WHERE league_id = ? AND role IN ('current','previous')",
            (league_id,),
        ).fetchall()
        for r in rows:
            si = self._row_to_season(r)
            if si.role == "current":
                current = si
            elif si.role == "previous":
                previous = si
        return current, previous

    def rotate_season(
        self, league_id: int, new_label: str,
        year_start: int, year_end: int | None = None,
        phase: str | None = None,
        force_overwrite: bool = False,
    ) -> tuple[int, bool]:
        """執行賽季轉換：本季→上季，建立新本季。

        流程：
        1. 若已有 previous 且 force_overwrite=False → 回傳 (0, True) 表示需確認
        2. 若已有 previous 且 force_overwrite=True → 封存舊 previous（role=NULL）
        3. 將 current 的 role 改為 previous
        4. 建立新 current Season

        封存的賽季保留 match_records 等資料，以供日後查詢。

        Args:
            league_id: 聯賽 ID。
            new_label: 新賽季標識（如 "2026"）。
            year_start: 新賽季起始年份。
            year_end: 新賽季結束年份（可選）。
            phase: 階段（可選）。
            force_overwrite: 是否強制封存已有的上季。

        Returns:
            (new_season_id, needs_confirm)。
            needs_confirm=True 表示已有上季需確認封存，此時 new_season_id=0。
        """
        current, previous = self.get_current_previous_pair(league_id)

        if not current:
            raise ValueError(f"聯賽 {league_id} 沒有本季賽季，無法轉換")

        # 檢查是否已有上季
        if previous and not force_overwrite:
            return 0, True  # 需要使用者確認

        # 封存舊的 previous（role 設為 NULL，保留所有資料）
        if previous:
            self.set_season_role(previous.id, None)

        # 將 current → previous
        self.set_season_role(current.id, "previous")

        # 建立新 current
        new_sid = self.create_season_instance(
            league_id=league_id,
            label=new_label,
            year_start=year_start,
            year_end=year_end,
            phase=phase,
        )
        self.set_season_role(new_sid, "current")

        self._conn.commit()
        return new_sid, False

    def is_season_readonly(self, season_instance_id: int) -> bool:
        """檢查賽季是否為唯讀。

        目前所有賽季皆可編輯（包含上季），故永遠回傳 False。
        """
        return False

    @staticmethod
    def _row_to_season(row: sqlite3.Row) -> SeasonInstance:
        return SeasonInstance(
            id=row["id"],
            league_id=row["league_id"],
            label=row["label"],
            year_start=row["year_start"],
            year_end=row["year_end"],
            phase=row["phase"],
            role=row["role"],
        )

    # ------------------------------------------------------------------
    # 全域分組 CRUD (global_groups)
    # ------------------------------------------------------------------

    def list_global_groups(self) -> list[GlobalGroup]:
        """列出所有全域分組，按 display_order 排序。"""
        rows = self._conn.execute(
            "SELECT * FROM global_groups ORDER BY display_order, id"
        ).fetchall()
        return [self._row_to_global_group(r) for r in rows]

    def create_global_group(
        self, name: str, display_name: str | None = None
    ) -> int:
        """新增全域分組，回傳 ID。name 必須唯一。"""
        existing = self._conn.execute(
            "SELECT id FROM global_groups WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"全域分組名稱已存在: {name}")
        cur = self._conn.execute(
            "INSERT INTO global_groups (name, display_name) VALUES (?, ?)",
            (name, display_name),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def delete_global_group(self, group_id: int) -> None:
        """刪除全域分組，級聯刪除關聯資料。"""
        self._conn.execute(
            "DELETE FROM computation_results WHERE global_group_id = ?", (group_id,)
        )
        self._conn.execute(
            "DELETE FROM decision_results WHERE global_group_id = ?", (group_id,)
        )
        self._conn.execute(
            "DELETE FROM league_group_teams WHERE global_group_id = ?", (group_id,)
        )
        self._conn.execute("DELETE FROM global_groups WHERE id = ?", (group_id,))
        self._conn.commit()

    def update_global_group(
        self,
        group_id: int,
        name: str | None = None,
        display_name: str | None = None,
        display_order: int | None = None,
    ) -> None:
        """更新全域分組的屬性。"""
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if display_name is not None:
            fields["display_name"] = display_name
        if display_order is not None:
            fields["display_order"] = display_order
        if not fields:
            return
        sets = [f"{k} = ?" for k in fields]
        vals = list(fields.values())
        vals.append(group_id)
        self._conn.execute(
            f"UPDATE global_groups SET {', '.join(sets)} WHERE id = ?", vals
        )
        self._conn.commit()

    @staticmethod
    def _row_to_global_group(row: sqlite3.Row) -> GlobalGroup:
        return GlobalGroup(
            id=row["id"],
            name=row["name"],
            display_name=row["display_name"],
            display_order=row["display_order"],
        )

    # ------------------------------------------------------------------
    # 聯賽隊伍配置 CRUD (league_group_teams)
    # ------------------------------------------------------------------

    def get_league_group_teams(
        self, league_id: int, global_group_id: int, role: str
    ) -> list[str]:
        """取得指定聯賽 × 分組 × 角色的隊伍列表。role: 'current' | 'previous'"""
        row = self._conn.execute(
            "SELECT teams_json FROM league_group_teams "
            "WHERE league_id = ? AND global_group_id = ? AND role = ?",
            (league_id, global_group_id, role),
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["teams_json"])

    def set_league_group_teams(
        self, league_id: int, global_group_id: int, role: str, teams: list[str]
    ) -> None:
        """設定指定聯賽 × 分組 × 角色的隊伍列表（UPSERT）。"""
        teams_json = json.dumps(teams, ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO league_group_teams (league_id, global_group_id, role, teams_json, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(league_id, global_group_id, role) "
            "DO UPDATE SET teams_json = excluded.teams_json, updated_at = excluded.updated_at",
            (league_id, global_group_id, role, teams_json),
        )
        self._conn.commit()

    def get_all_league_group_teams(
        self, league_id: int
    ) -> list[LeagueGroupTeams]:
        """取得指定聯賽的所有分組隊伍配置。"""
        rows = self._conn.execute(
            "SELECT * FROM league_group_teams WHERE league_id = ? ORDER BY global_group_id, role",
            (league_id,),
        ).fetchall()
        return [self._row_to_league_group_teams(r) for r in rows]

    def get_league_team_pool(self, league_id: int) -> list[str]:
        """取得聯賽所有賽季 match_records 中的隊伍聯集。"""
        rows = self._conn.execute(
            "SELECT DISTINCT team FROM ("
            "  SELECT home_team AS team FROM match_records "
            "    WHERE season_instance_id IN "
            "      (SELECT id FROM season_instances WHERE league_id = ?) "
            "  UNION "
            "  SELECT away_team AS team FROM match_records "
            "    WHERE season_instance_id IN "
            "      (SELECT id FROM season_instances WHERE league_id = ?)"
            ") ORDER BY team",
            (league_id, league_id),
        ).fetchall()
        return [r["team"] for r in rows]

    @staticmethod
    def _row_to_league_group_teams(row: sqlite3.Row) -> LeagueGroupTeams:
        return LeagueGroupTeams(
            id=row["id"],
            league_id=row["league_id"],
            global_group_id=row["global_group_id"],
            role=row["role"],
            teams=json.loads(row["teams_json"]),
        )

    # ------------------------------------------------------------------
    # 隊伍分組 CRUD
    # ------------------------------------------------------------------

    def list_team_groups(self, season_instance_id: int) -> list[TeamGroup]:
        rows = self._conn.execute(
            "SELECT * FROM team_groups WHERE season_instance_id = ? ORDER BY display_order, id",
            (season_instance_id,),
        ).fetchall()
        groups: list[TeamGroup] = []
        for r in rows:
            tg = self._row_to_team_group(r)
            tg.teams = self.list_teams(tg.id)
            groups.append(tg)
        return groups

    def create_team_group(
        self,
        season_instance_id: int,
        name: str,
        display_name: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO team_groups (season_instance_id, name, display_name) "
            "VALUES (?, ?, ?)",
            (season_instance_id, name, display_name),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_team_group(self, group_id: int, **kwargs: Any) -> None:
        allowed = {"name", "display_name", "display_order"}
        sets = []
        vals: list[Any] = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        vals.append(group_id)
        self._conn.execute(
            f"UPDATE team_groups SET {', '.join(sets)} WHERE id = ?", vals
        )
        self._conn.commit()

    def delete_team_group(self, group_id: int) -> None:
        self._conn.execute("DELETE FROM team_groups WHERE id = ?", (group_id,))
        self._conn.commit()

    @staticmethod
    def _row_to_team_group(row: sqlite3.Row) -> TeamGroup:
        return TeamGroup(
            id=row["id"],
            season_instance_id=row["season_instance_id"],
            name=row["name"],
            display_name=row["display_name"],
        )

    # ------------------------------------------------------------------
    # 隊伍 CRUD
    # ------------------------------------------------------------------

    def list_teams(self, team_group_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM teams WHERE team_group_id = ? ORDER BY display_order, id",
            (team_group_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def set_teams(self, team_group_id: int, names: list[str]) -> None:
        """替換指定分組的所有隊伍。"""
        self._conn.execute(
            "DELETE FROM teams WHERE team_group_id = ?", (team_group_id,)
        )
        for i, name in enumerate(names):
            if not name.strip():
                continue
            self._conn.execute(
                "INSERT INTO teams (team_group_id, name, display_order) VALUES (?, ?, ?)",
                (team_group_id, name.strip(), i),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # 檔案路徑 CRUD (file_paths)
    # ------------------------------------------------------------------

    def set_file_path(
        self,
        season_instance_id: int,
        play_type: str,
        timing: str,
        file_path: str,
    ) -> int:
        """設定或更新 RPA 檔案路徑（UPSERT）。"""
        cur = self._conn.execute(
            "INSERT INTO file_paths (season_instance_id, play_type, timing, file_path, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(season_instance_id, play_type, timing) "
            "DO UPDATE SET file_path = excluded.file_path, updated_at = datetime('now')",
            (season_instance_id, play_type, timing, file_path),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_file_paths(self, season_instance_id: int) -> list[FilePath]:
        """取得指定賽季的所有檔案路徑。"""
        rows = self._conn.execute(
            "SELECT * FROM file_paths WHERE season_instance_id = ? ORDER BY play_type, timing",
            (season_instance_id,),
        ).fetchall()
        return [self._row_to_file_path(r) for r in rows]

    def delete_file_paths(self, season_instance_id: int) -> None:
        """刪除指定賽季的所有檔案路徑。"""
        self._conn.execute(
            "DELETE FROM file_paths WHERE season_instance_id = ?",
            (season_instance_id,),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_file_path(row: sqlite3.Row) -> FilePath:
        return FilePath(
            id=row["id"],
            season_instance_id=row["season_instance_id"],
            play_type=row["play_type"],
            timing=row["timing"],
            file_path=row["file_path"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------
    # match_records CRUD
    # ------------------------------------------------------------------

    def upsert_match_records(
        self,
        season_instance_id: int,
        play_type: str,
        timing: str,
        records: list[MatchRecord],
    ) -> int:
        """UPSERT 比賽紀錄：刪除舊資料後批量插入。回傳插入筆數。"""
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "DELETE FROM match_records "
                "WHERE season_instance_id = ? AND play_type = ? AND timing = ?",
                (season_instance_id, play_type, timing),
            )
            for r in records:
                self._conn.execute(
                    "INSERT INTO match_records "
                    "(season_instance_id, play_type, timing, round, home_team, score, "
                    "away_team, x_value, sim_result, link, settlement_value, "
                    "settlement_direction, home_away_direction, target_team) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        season_instance_id,
                        play_type,
                        timing,
                        r.round_num,
                        r.home_team,
                        r.score,
                        r.away_team,
                        r.x_value,
                        r.settlement,
                        r.link,
                        r.settlement_value,
                        r.settlement_direction,
                        r.home_away_direction,
                        r.target_team,
                    ),
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return len(records)

    def get_match_records(
        self,
        season_instance_id: int,
        play_type: str | None = None,
        timing: str | None = None,
    ) -> list[MatchRecord]:
        """查詢比賽紀錄，支援按 play_type 和 timing 篩選。"""
        sql = "SELECT * FROM match_records WHERE season_instance_id = ?"
        params: list[Any] = [season_instance_id]
        if play_type is not None:
            sql += " AND play_type = ?"
            params.append(play_type)
        if timing is not None:
            sql += " AND timing = ?"
            params.append(timing)
        sql += " ORDER BY round, id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_match_record(r) for r in rows]

    def get_match_record_counts(
        self, season_instance_id: int
    ) -> dict[tuple[str, str], int]:
        """取得各 (play_type, timing) 組合的紀錄筆數。"""
        rows = self._conn.execute(
            "SELECT play_type, timing, COUNT(*) AS cnt "
            "FROM match_records WHERE season_instance_id = ? "
            "GROUP BY play_type, timing",
            (season_instance_id,),
        ).fetchall()
        return {(r["play_type"], r["timing"]): r["cnt"] for r in rows}

    def get_team_pool(self, season_instance_id: int) -> list[str]:
        """從 match_records 提取 Team_Pool（所有 home_team + away_team 的聯集）。"""
        rows = self._conn.execute(
            "SELECT DISTINCT name FROM ("
            "  SELECT home_team AS name FROM match_records WHERE season_instance_id = ? "
            "  UNION "
            "  SELECT away_team AS name FROM match_records WHERE season_instance_id = ?"
            ") ORDER BY name",
            (season_instance_id, season_instance_id),
        ).fetchall()
        return [r["name"] for r in rows]

    def find_league_by_identity(
        self, name_zh: str, phase: str | None
    ) -> League | None:
        """以 (name_zh, phase) 查詢聯賽。"""
        if phase is None:
            row = self._conn.execute(
                "SELECT * FROM leagues "
                "WHERE name_zh = ? AND (phase IS NULL OR phase = '')",
                (name_zh,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM leagues WHERE name_zh = ? AND phase = ?",
                (name_zh, phase),
            ).fetchone()
        return self._row_to_league(row) if row else None

    @staticmethod
    def _row_to_match_record(row: sqlite3.Row) -> MatchRecord:
        return MatchRecord(
            round_num=row["round"],
            home_team=row["home_team"],
            away_team=row["away_team"],
            x_value=row["x_value"],
            settlement=row["sim_result"] or "",
            score=row["score"] or "",
            link=row["link"] or "",
            play_type=row["play_type"],
            settlement_value=row["settlement_value"],
            settlement_direction=row["settlement_direction"],
            home_away_direction=row["home_away_direction"],
            target_team=row["target_team"],
        )

    # ------------------------------------------------------------------
    # 演算法參數
    # ------------------------------------------------------------------

    def get_all_params(self) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT param_key, param_value FROM algo_params"
        ).fetchall()
        return {r["param_key"]: json.loads(r["param_value"]) for r in rows}

    def get_param(self, key: str) -> Any:
        row = self._conn.execute(
            "SELECT param_value FROM algo_params WHERE param_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["param_value"])

    def set_param(self, key: str, value: Any, description: str | None = None) -> None:
        json_val = json.dumps(value, ensure_ascii=False)
        if description is not None:
            self._conn.execute(
                "INSERT INTO algo_params (param_key, param_value, description, updated_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(param_key) DO UPDATE SET "
                "param_value = excluded.param_value, description = excluded.description, "
                "updated_at = datetime('now')",
                (key, json_val, description),
            )
        else:
            self._conn.execute(
                "INSERT INTO algo_params (param_key, param_value, updated_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(param_key) DO UPDATE SET "
                "param_value = excluded.param_value, updated_at = datetime('now')",
                (key, json_val),
            )
        self._conn.commit()

    def reset_params_to_default(self) -> None:
        """從 config/default_params.json 讀取預設值並寫入資料庫。"""
        defaults_path = _PROJECT_ROOT / "config" / "default_params.json"
        with open(defaults_path, encoding="utf-8") as f:
            defaults: dict[str, Any] = json.load(f)
        for key, value in defaults.items():
            self.set_param(key, value)

    # ------------------------------------------------------------------
    # ETL 紀錄
    # ------------------------------------------------------------------

    def create_etl_run(self, scope: dict) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        params_snapshot = json.dumps(self.get_all_params(), ensure_ascii=False)
        cur = self._conn.execute(
            "INSERT INTO etl_runs (started_at, status, scope_leagues, params_snapshot) "
            "VALUES (?, 'running', ?, ?)",
            (
                now,
                json.dumps(scope.get("leagues"), ensure_ascii=False)
                if scope.get("leagues")
                else None,
                params_snapshot,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def complete_etl_run(self, run_id: int, status: str, summary: dict) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE etl_runs SET completed_at = ?, status = ?, summary = ? WHERE id = ?",
            (now, status, json.dumps(summary, ensure_ascii=False), run_id),
        )
        self._conn.commit()

    def list_etl_runs(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM etl_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result: list[dict] = []
        for r in rows:
            d = dict(r)
            for key in ("scope_leagues", "params_snapshot", "summary"):
                if d.get(key):
                    d[key] = json.loads(d[key])
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # 計算結果儲存與查詢
    # ------------------------------------------------------------------

    def save_computation_result(self, run_id: int, result: dict) -> None:
        self._conn.execute(
            "INSERT INTO computation_results "
            "(etl_run_id, league_id, season_instance_id, team_group_id, play_type, timing, "
            "zone_data, round_block_data, season_total_win, season_total_lose, global_group_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                result["league_id"],
                result["season_instance_id"],
                result["team_group_id"],
                result["play_type"],
                result["timing"],
                json.dumps(result["zone_data"], ensure_ascii=False),
                json.dumps(result["round_block_data"], ensure_ascii=False),
                result.get("season_total_win", 0),
                result.get("season_total_lose", 0),
                result.get("global_group_id"),
            ),
        )
        self._auto_commit()

    def get_computation_results(
        self,
        run_id: int,
        league_id: int | None = None,
        play_type: str | None = None,
        timing: str | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM computation_results WHERE etl_run_id = ?"
        params: list[Any] = [run_id]
        if league_id is not None:
            sql += " AND league_id = ?"
            params.append(league_id)
        if play_type is not None:
            sql += " AND play_type = ?"
            params.append(play_type)
        if timing is not None:
            sql += " AND timing = ?"
            params.append(timing)
        sql += " ORDER BY league_id, season_instance_id, team_group_id"
        rows = self._conn.execute(sql, params).fetchall()
        results: list[dict] = []
        for r in rows:
            d = dict(r)
            d["zone_data"] = json.loads(d["zone_data"])
            d["round_block_data"] = json.loads(d["round_block_data"])
            results.append(d)
        return results

    # ------------------------------------------------------------------
    # 決策結果儲存與查詢
    # ------------------------------------------------------------------

    def save_decision_result(self, run_id: int, result: dict) -> None:
        self._conn.execute(
            "INSERT INTO decision_results "
            "(etl_run_id, league_id, team_group_id, play_type, timing, "
            "five_zone_data, guard_levels, strength_levels, home_signals, away_signals, "
            "global_group_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                result["league_id"],
                result["team_group_id"],
                result["play_type"],
                result["timing"],
                json.dumps(result["five_zone_data"], ensure_ascii=False),
                json.dumps(result["guard_levels"], ensure_ascii=False),
                json.dumps(result["strength_levels"], ensure_ascii=False),
                json.dumps(result["home_signals"], ensure_ascii=False),
                json.dumps(result["away_signals"], ensure_ascii=False),
                result.get("global_group_id"),
            ),
        )
        self._auto_commit()

    def get_decision_results(
        self,
        run_id: int,
        league_id: int | None = None,
        play_type: str | None = None,
        timing: str | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM decision_results WHERE etl_run_id = ?"
        params: list[Any] = [run_id]
        if league_id is not None:
            sql += " AND league_id = ?"
            params.append(league_id)
        if play_type is not None:
            sql += " AND play_type = ?"
            params.append(play_type)
        if timing is not None:
            sql += " AND timing = ?"
            params.append(timing)
        sql += " ORDER BY league_id, team_group_id"
        rows = self._conn.execute(sql, params).fetchall()
        results: list[dict] = []
        for r in rows:
            d = dict(r)
            for key in (
                "five_zone_data", "guard_levels", "strength_levels",
                "home_signals", "away_signals",
            ):
                d[key] = json.loads(d[key])
            results.append(d)
        return results

    # ------------------------------------------------------------------
    # 品質問題儲存與查詢
    # ------------------------------------------------------------------

    def save_quality_issue(self, run_id: int, issue: dict) -> None:
        self._conn.execute(
            "INSERT INTO quality_issues "
            "(etl_run_id, league_id, severity, issue_type, description, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                issue["league_id"],
                issue["severity"],
                issue["issue_type"],
                issue["description"],
                json.dumps(issue.get("details"), ensure_ascii=False)
                if issue.get("details")
                else None,
            ),
        )
        self._auto_commit()

    def get_quality_issues(self, run_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM quality_issues WHERE etl_run_id = ? ORDER BY severity DESC, id",
            (run_id,),
        ).fetchall()
        results: list[dict] = []
        for r in rows:
            d = dict(r)
            if d.get("details"):
                d["details"] = json.loads(d["details"])
            results.append(d)
        return results

    def cleanup_old_etl_runs(self, keep_recent: int = 10) -> int:
        """清理舊的 ETL 執行紀錄，保留最近 N 筆。

        刪除舊 run 的 computation_results、decision_results、quality_issues。

        Args:
            keep_recent: 保留最近幾筆 completed 的 run。

        Returns:
            刪除的 run 數量。
        """
        rows = self._conn.execute(
            "SELECT id FROM etl_runs ORDER BY id DESC"
        ).fetchall()
        all_ids = [r[0] for r in rows]

        if len(all_ids) <= keep_recent:
            return 0

        ids_to_delete = all_ids[keep_recent:]
        placeholders = ",".join("?" * len(ids_to_delete))

        self._conn.execute(
            f"DELETE FROM computation_results WHERE etl_run_id IN ({placeholders})",
            ids_to_delete,
        )
        self._conn.execute(
            f"DELETE FROM decision_results WHERE etl_run_id IN ({placeholders})",
            ids_to_delete,
        )
        self._conn.execute(
            f"DELETE FROM quality_issues WHERE etl_run_id IN ({placeholders})",
            ids_to_delete,
        )
        self._conn.execute(
            f"DELETE FROM etl_runs WHERE id IN ({placeholders})",
            ids_to_delete,
        )
        self._conn.commit()
        logger.info("已清理 %d 筆舊 ETL 紀錄", len(ids_to_delete))
        return len(ids_to_delete)


    # ------------------------------------------------------------------
    # 操作日誌
    # ------------------------------------------------------------------

    def log_action(self, action: str, entity_type: str,
                   entity_id: int | None = None, details: str | None = None) -> None:
        """記錄操作日誌。"""
        self._conn.execute(
            "INSERT INTO audit_logs (action, entity_type, entity_id, details) VALUES (?, ?, ?, ?)",
            (action, entity_type, entity_id, details),
        )
        self._auto_commit()

    def list_audit_logs(self, limit: int = 100, entity_type: str | None = None) -> list[dict]:
        """列出操作日誌。"""
        sql = "SELECT * FROM audit_logs WHERE 1=1"
        params: list[Any] = []
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 刪除單一 ETL Run
    # ------------------------------------------------------------------

    def delete_etl_run(self, run_id: int) -> bool:
        """刪除指定的 ETL Run 及其所有關聯資料。

        Returns:
            True 表示成功刪除，False 表示 run 不存在。
        """
        row = self._conn.execute("SELECT id FROM etl_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return False
        self._conn.execute("DELETE FROM computation_results WHERE etl_run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM decision_results WHERE etl_run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM quality_issues WHERE etl_run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM etl_runs WHERE id = ?", (run_id,))
        self._conn.commit()
        self.log_action("delete", "etl_run", run_id)
        return True

