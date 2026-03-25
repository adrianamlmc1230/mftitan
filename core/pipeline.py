"""ETLPipeline：主流程編排器。

從 match_records 資料表讀取已前處理、已結算的比賽紀錄，
對每個 ComputationUnit（聯賽 × 賽季 × 分組 × 玩法 × 時段）獨立執行。

流程：
1. 從 match_records 表讀取比賽紀錄
2. 對每個 TeamGroup 執行：分類→輪次匯總
3. 跨賽季匯總→五大區間→護級→強度→訊號
4. 品質檢查，儲存結果
"""

import json
import logging
import warnings
from datetime import datetime
from typing import Callable

from core.classifier import XValueClassifier
from core.config_store import ConfigStore
from core.five_zone import FiveZoneGrouper
from core.guard import GuardLevelEvaluator
from core.matcher import TeamMatcher
from core.models import MatchRecord, TeamGroup, ZoneStats
from core.quality import QualityChecker
from core.round_aggregator import RoundBlockAggregator
from core.season_aggregator import SeasonAggregator
from core.signal import SignalGenerator
from core.splitter import RecordSplitter
from core.strength import StrengthUpgrader

logger = logging.getLogger(__name__)


class ETLPipeline:
    """ETL 主流程編排器。"""

    def __init__(self, config_store: ConfigStore):
        self.store = config_store
        self.matcher = TeamMatcher()
        self.splitter = RecordSplitter()
        self.classifier = XValueClassifier()
        self.round_agg = RoundBlockAggregator()
        self.season_agg = SeasonAggregator()
        self.five_zone = FiveZoneGrouper()
        self.guard = GuardLevelEvaluator()
        self.strength = StrengthUpgrader()
        self.signal = SignalGenerator()
        self.quality = QualityChecker()

    def execute(
        self,
        league_ids: list[int] | None = None,
        season_pairs: dict[int, tuple[int, int | None]] | None = None,
        progress_callback: Callable | None = None,
    ) -> int:
        """執行完整 ETL 流程。

        Args:
            league_ids: 聯賽 ID 篩選（None=全部啟用聯賽）。
            season_pairs: 每個聯賽指定的賽季配對（設計決策 6）。
                格式：{league_id: (current_season_id, previous_season_id)}。
                previous_season_id 可為 None（無上季資料）。
                未指定的聯賽使用預設的 role=current/previous。
            progress_callback: 進度回呼 fn(current, total, message)。

        Returns:
            etl_run_id。
        """
        params = self.store.get_all_params()
        scope = {"league_ids": league_ids, "season_pairs": season_pairs}
        run_id = self.store.create_etl_run(scope)

        try:
            leagues = self.store.list_leagues(active_only=True)
            if league_ids:
                leagues = [lg for lg in leagues if lg.id in league_ids]

            total = len(leagues)
            for idx, league in enumerate(leagues):
                try:
                    self.store.begin_transaction()
                    self._process_league(league, params, run_id, season_pairs)
                    self.store.commit_transaction()
                except Exception as exc:
                    self.store.rollback_transaction()
                    logger.error("聯賽 %s 處理失敗，已回滾：%s", league.code, exc)
                    self.store.save_quality_issue(run_id, {
                        "league_id": league.id,
                        "severity": "error",
                        "issue_type": "processing_error",
                        "description": str(exc),
                    })
                if progress_callback:
                    progress_callback(idx + 1, total, f"處理中：{league.code}")

            self.store.complete_etl_run(run_id, "completed", {
                "finished_at": datetime.now().isoformat(),
                "leagues_processed": total,
            })
        except Exception as exc:
            logger.error("ETL 流程失敗：%s", exc, exc_info=True)
            self.store.complete_etl_run(run_id, "failed", {"error": str(exc)})

        return run_id

    # ------------------------------------------------------------------
    # 內部方法
    # ------------------------------------------------------------------

    def _process_league(self, league, params: dict, run_id: int,
                        season_pairs: dict | None = None) -> None:
        """處理單一聯賽：讀取本季/上季檔案，逐分組計算，跨賽季決策。

        支援彈性賽季選擇（設計決策 6）：
        - 若 season_pairs 有指定該聯賽的賽季配對，使用指定的賽季
        - 否則使用預設的 role=current/previous
        """
        seasons = self.store.list_season_instances(league.id)

        # 決定本季/上季賽季實例
        if season_pairs and league.id in season_pairs:
            curr_id, prev_id = season_pairs[league.id]
            current = next((s for s in seasons if s.id == curr_id), None)
            previous = next((s for s in seasons if s.id == prev_id), None) if prev_id else None
        else:
            current = next((s for s in seasons if s.role == "current"), None)
            previous = next((s for s in seasons if s.role == "previous"), None)

        if not current:
            logger.warning("聯賽 %s 無本季賽季，跳過", league.code)
            return

        # 從全域分組建構本季/上季 TeamGroup 物件
        global_groups = self.store.list_global_groups()
        curr_team_groups: list[TeamGroup] = []
        prev_team_groups: list[TeamGroup] = []

        for gg in global_groups:
            curr_teams = self.store.get_league_group_teams(league.id, gg.id, "current")
            prev_teams = self.store.get_league_group_teams(league.id, gg.id, "previous")

            if not curr_teams and not prev_teams:
                logger.warning(
                    "聯賽 %s 分組 '%s' 本季/上季隊伍皆為空，跳過",
                    league.code, gg.name,
                )
                continue

            curr_tg = TeamGroup(
                id=gg.id, season_instance_id=current.id,
                name=gg.name, display_name=gg.display_name, teams=curr_teams,
            )
            curr_team_groups.append(curr_tg)

            if previous:
                prev_tg = TeamGroup(
                    id=gg.id, season_instance_id=previous.id,
                    name=gg.name, display_name=gg.display_name, teams=prev_teams,
                )
                prev_team_groups.append(prev_tg)

        if not curr_team_groups:
            logger.warning("聯賽 %s 無有效的隊伍分組，跳過", league.code)
            return

        boundaries = params.get("x_value_boundaries", self.classifier.DEFAULT_BOUNDARIES)
        block_size = params.get("round_block_size", 10)
        five_zone_mapping = params.get("five_zone_mapping")

        # 讀取本季紀錄 → 按 (play_type, timing) 分組的紀錄
        curr_file_records = self._process_season_records(current, league, boundaries)

        # 讀取上季紀錄
        prev_file_records: dict[tuple[str, str], list[MatchRecord]] = {}
        if previous:
            prev_file_records = self._process_season_records(previous, league, boundaries)

        # 本季：對每個 (play_type, timing) × team_group 計算
        for (play_type, timing), records in curr_file_records.items():
            match_mode = "target" if play_type == "HDP" else "participant"
            split_result, unmatched = self.splitter.split(
                records, curr_team_groups, match_mode=match_mode,
            )
            if unmatched:
                self.store.save_quality_issue(run_id, {
                    "league_id": league.id,
                    "severity": "warning",
                    "issue_type": "unmatched_teams",
                    "description": f"{league.code} {play_type}-{timing} 未匹配隊伍",
                    "details": {"teams": list(unmatched)},
                })

            for tg in curr_team_groups:
                group_records = split_result.get(tg.id, [])
                self._process_team_group(
                    league, current, tg, play_type, timing,
                    group_records, block_size, run_id,
                    boundaries,
                )

        # 上季：用上季 TeamGroup 物件分割上季紀錄
        if previous and prev_team_groups:
            for (play_type, timing), records in prev_file_records.items():
                match_mode = "target" if play_type == "HDP" else "participant"
                split_result, _ = self.splitter.split(
                    records, prev_team_groups, match_mode=match_mode,
                )
                for tg in prev_team_groups:
                    group_records = split_result.get(tg.id, [])
                    self._process_team_group(
                        league, previous, tg, play_type, timing,
                        group_records, block_size, run_id,
                        boundaries,
                    )

        # 跨賽季決策（本季 vs 上季）
        self._generate_decisions(
            league, current, previous, curr_team_groups, run_id, params,
            prev_team_groups=prev_team_groups,
        )

        # 品質檢查
        self._run_quality_checks(league, curr_team_groups, run_id)

    def _process_season_records(
        self, season, league, boundaries,
    ) -> dict[tuple[str, str], list[MatchRecord]]:
        """從 match_records 表讀取已前處理的紀錄。

        取代原本的 _process_season_files（從 Excel 讀取）。
        紀錄已在匯入時完成前處理與結算計算，可直接使用。

        Returns:
            {(play_type, timing): [MatchRecord]} 已結算的紀錄。
        """
        result: dict[tuple[str, str], list[MatchRecord]] = {}

        for play_type in ("HDP", "OU"):
            for timing in ("Early", "RT"):
                records = self.store.get_match_records(
                    season.id, play_type=play_type, timing=timing
                )
                if records:
                    result[(play_type, timing)] = records

        return result

    def _process_season_files(
        self, season, league, boundaries,
    ) -> dict[tuple[str, str], list[MatchRecord]]:
        """讀取賽季的所有檔案，前處理並提取紀錄。

        .. deprecated::
            此方法已棄用，請改用 :meth:`_process_season_records`
            從 match_records 資料表讀取。

        Returns:
            {(play_type, timing): [MatchRecord]} 已結算、已分類的紀錄。
        """
        warnings.warn(
            "_process_season_files 已棄用，請改用 _process_season_records",
            DeprecationWarning,
            stacklevel=2,
        )
        # Lazy import to avoid hard dependency after refactor
        from core.preprocessor import RawDataPreprocessor
        from core.reader import RawDataReader
        from core.settlement import SettlementCalculator

        reader = RawDataReader()
        preprocessor = RawDataPreprocessor()
        settlement = SettlementCalculator()

        file_paths = self.store.get_file_paths(season.id)
        result: dict[tuple[str, str], list[MatchRecord]] = {}

        for fp in file_paths:
            df = reader.read(fp.file_path)
            if df.empty:
                logger.warning("檔案為空或不存在：%s", fp.file_path)
                continue

            df, _ = preprocessor.process(df)
            records = reader.extract_records(df)

            # 設定 play_type
            for rec in records:
                rec.play_type = fp.play_type

            # 結算計算
            records = settlement.calculate(records)

            result[(fp.play_type, fp.timing)] = records

        return result

    def _process_team_group(
        self, league, season, tg, play_type, timing,
        records, block_size, run_id, boundaries=None,
    ) -> None:
        """處理單一分組：分類 → 輪次匯總 → 儲存計算結果。"""
        classified = self.classifier.classify(records, boundaries)
        blocks = self.round_agg.aggregate(classified, block_size)
        season_zones = self.round_agg.season_total(blocks)

        # 計算全季 win/lose 總和（Home + Away）
        total_win = sum(z.home_win + z.away_win for z in season_zones)
        total_lose = sum(z.home_lose + z.away_lose for z in season_zones)

        # 序列化 zone_data
        zone_data = [
            {
                "zone_id": z.zone_id,
                "home_win": z.home_win,
                "home_lose": z.home_lose,
                "away_win": z.away_win,
                "away_lose": z.away_lose,
            }
            for z in season_zones
        ]

        # 序列化 round_block_data
        round_block_data = [
            {
                "block_id": b.block_id,
                "round_start": b.round_start,
                "round_end": b.round_end,
                "zones": [
                    {
                        "zone_id": z.zone_id,
                        "home_win": z.home_win,
                        "home_lose": z.home_lose,
                        "away_win": z.away_win,
                        "away_lose": z.away_lose,
                    }
                    for z in b.zones
                ],
            }
            for b in blocks
        ]

        self.store.save_computation_result(run_id, {
            "league_id": league.id,
            "season_instance_id": season.id,
            "team_group_id": tg.id,
            "global_group_id": tg.id,
            "play_type": play_type,
            "timing": timing,
            "zone_data": zone_data,
            "round_block_data": round_block_data,
            "season_total_win": total_win,
            "season_total_lose": total_lose,
        })

    def _generate_decisions(
        self, league, current, previous, team_groups, run_id, params,
        prev_team_groups: list | None = None,
    ) -> None:
        """跨賽季決策：五大區間 → 護級 → 強度 → 訊號。"""
        five_zone_mapping = params.get("five_zone_mapping")
        multiplier = params.get("strength_upgrade_multiplier", 2.0)
        ratio_threshold = params.get("guard_ratio_threshold", 1.4)

        # 建立 global_group_id → prev TeamGroup 的查找表
        prev_by_id: dict[int, object] = {}
        if prev_team_groups:
            prev_by_id = {ptg.id: ptg for ptg in prev_team_groups}

        for tg in team_groups:
            # 用 global_group_id (tg.id) 直接匹配上季 TeamGroup
            prev_tg = prev_by_id.get(tg.id) if previous else None

            # 對每個 (play_type, timing) 組合產生決策
            for play_type in ("HDP", "OU"):
                for timing in ("Early", "RT"):
                    self._decide_for_unit(
                        league, current, previous, tg, prev_tg,
                        play_type, timing, run_id,
                        five_zone_mapping, multiplier, ratio_threshold,
                    )

    def _decide_for_unit(
        self, league, current, previous, tg, prev_tg,
        play_type, timing, run_id,
        five_zone_mapping, multiplier, ratio_threshold,
    ) -> None:
        """單一 computation unit 的決策流程。"""
        # 取得本季計算結果
        curr_results = self.store.get_computation_results(
            run_id, league_id=league.id, play_type=play_type, timing=timing,
        )
        curr_zones = self._extract_zones(curr_results, current.id, tg.id)

        # 取得上季計算結果
        prev_zones = None
        if previous and prev_tg:
            prev_results = self.store.get_computation_results(
                run_id, league_id=league.id, play_type=play_type, timing=timing,
            )
            prev_zones = self._extract_zones(prev_results, previous.id, prev_tg.id)

        # 賽季匯總
        prev_z, curr_z, cross_z = self.season_agg.aggregate(curr_zones, prev_zones)

        # 五大區間
        prev_five = self.five_zone.group(prev_z, five_zone_mapping)
        curr_five = self.five_zone.group(curr_z, five_zone_mapping)

        # 護級 → 強度 → 訊號（Home 和 Away 分別處理）
        home_signals: list[str] = []
        away_signals: list[str] = []
        guard_levels: list[dict] = []
        strength_levels: list[dict] = []
        five_zone_data: list[dict] = []

        for i in range(5):
            p_hw, p_hl, p_aw, p_al = prev_five[i]
            c_hw, c_hl, c_aw, c_al = curr_five[i]

            # Home 方向
            home_guard = self.guard.evaluate(p_hw, p_hl, c_hw, c_hl)
            home_str = self.strength.upgrade(home_guard, p_hw, p_hl, multiplier)
            home_sig = self.signal.generate(
                home_guard, home_str, p_hw, p_hl,
                ratio_threshold, direction_logic="greater",
            )

            # Away 方向
            away_guard = self.guard.evaluate(p_aw, p_al, c_aw, c_al)
            away_str = self.strength.upgrade(away_guard, p_aw, p_al, multiplier)
            away_sig = self.signal.generate(
                away_guard, away_str, p_aw, p_al,
                ratio_threshold, direction_logic="less",
            )

            home_signals.append(home_sig)
            away_signals.append(away_sig)
            guard_levels.append({"home": home_guard, "away": away_guard})
            strength_levels.append({"home": home_str, "away": away_str})
            five_zone_data.append({
                "zone_id": i + 1,
                "prev_home_win": p_hw, "prev_home_lose": p_hl,
                "prev_away_win": p_aw, "prev_away_lose": p_al,
                "curr_home_win": c_hw, "curr_home_lose": c_hl,
                "curr_away_win": c_aw, "curr_away_lose": c_al,
            })

        self.store.save_decision_result(run_id, {
            "league_id": league.id,
            "team_group_id": tg.id,
            "global_group_id": tg.id,
            "play_type": play_type,
            "timing": timing,
            "five_zone_data": five_zone_data,
            "guard_levels": guard_levels,
            "strength_levels": strength_levels,
            "home_signals": home_signals,
            "away_signals": away_signals,
        })

    def _extract_zones(
        self, results: list[dict], season_id: int, group_id: int,
    ) -> list[ZoneStats] | None:
        """從計算結果中提取指定賽季/分組的 ZoneStats。"""
        for r in results:
            if r["season_instance_id"] == season_id and r["team_group_id"] == group_id:
                return [
                    ZoneStats(
                        zone_id=z["zone_id"],
                        home_win=z["home_win"],
                        home_lose=z["home_lose"],
                        away_win=z["away_win"],
                        away_lose=z["away_lose"],
                    )
                    for z in r["zone_data"]
                ]
        return None

    def _run_quality_checks(self, league, team_groups, run_id: int) -> None:
        """執行品質檢查並儲存問題。"""
        # 此處可擴充更多品質檢查
        for tg in team_groups:
            for play_type in ("HDP", "OU"):
                for timing in ("Early", "RT"):
                    results = self.store.get_computation_results(
                        run_id, league_id=league.id,
                        play_type=play_type, timing=timing,
                    )
                    zones = self._extract_zones(results, tg.season_instance_id, tg.id)
                    if zones:
                        issues = self.quality.check_empty_data(
                            zones, league.code, tg.name,
                        )
                        for issue in issues:
                            self.store.save_quality_issue(run_id, {
                                "league_id": league.id,
                                "severity": issue.severity,
                                "issue_type": issue.issue_type,
                                "description": issue.description,
                                "details": issue.details,
                            })