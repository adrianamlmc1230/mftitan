"""RoundBlockAggregator 單元測試。"""

import pytest
from core.models import MatchRecord, ZoneStats, RoundBlockStats
from core.round_aggregator import RoundBlockAggregator


def _make_record(
    round_num: int = 1,
    settlement_value: float = 1.0,
    settlement_direction: str = "win",
    home_away_direction: str = "home",
) -> MatchRecord:
    """建立測試用 MatchRecord。"""
    return MatchRecord(
        round_num=round_num,
        home_team="TeamA",
        away_team="TeamB",
        x_value=0.0,
        settlement="主贏",
        play_type="HDP",
        settlement_value=settlement_value,
        settlement_direction=settlement_direction,
        home_away_direction=home_away_direction,
        target_team="TeamA",
    )


class TestRoundBlockAggregatorAggregate:
    """aggregate() 方法測試。"""

    def test_empty_input(self):
        agg = RoundBlockAggregator()
        blocks = agg.aggregate({})
        assert len(blocks) == 6
        for block in blocks:
            assert len(block.zones) == 9
            for zs in block.zones:
                assert zs.home_win == 0.0
                assert zs.home_lose == 0.0
                assert zs.away_win == 0.0
                assert zs.away_lose == 0.0

    def test_home_win_accumulation(self):
        classified = {1: [_make_record(round_num=1, settlement_value=1.0,
                                       settlement_direction="win",
                                       home_away_direction="home")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone1 = blocks[0].zones[0]  # block 1, zone 1
        assert zone1.home_win == 1.0
        assert zone1.home_lose == 0.0
        assert zone1.away_win == 0.0
        assert zone1.away_lose == 0.0

    def test_home_lose_accumulation(self):
        classified = {3: [_make_record(round_num=5, settlement_value=0.5,
                                       settlement_direction="lose",
                                       home_away_direction="home")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone3 = blocks[0].zones[2]  # block 1, zone 3
        assert zone3.home_win == 0.0
        assert zone3.home_lose == 0.5
        assert zone3.away_win == 0.0
        assert zone3.away_lose == 0.0

    def test_away_win_accumulation(self):
        classified = {5: [_make_record(round_num=3, settlement_value=1.0,
                                       settlement_direction="win",
                                       home_away_direction="away")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone5 = blocks[0].zones[4]  # block 1, zone 5
        assert zone5.home_win == 0.0
        assert zone5.home_lose == 0.0
        assert zone5.away_win == 1.0
        assert zone5.away_lose == 0.0

    def test_away_lose_accumulation(self):
        classified = {9: [_make_record(round_num=8, settlement_value=0.5,
                                       settlement_direction="lose",
                                       home_away_direction="away")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone9 = blocks[0].zones[8]  # block 1, zone 9
        assert zone9.home_win == 0.0
        assert zone9.home_lose == 0.0
        assert zone9.away_win == 0.0
        assert zone9.away_lose == 0.5

    def test_draw_direction_skipped(self):
        classified = {1: [_make_record(round_num=1, settlement_value=0.0,
                                       settlement_direction="draw",
                                       home_away_direction="home")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone1 = blocks[0].zones[0]
        assert zone1.home_win == 0.0
        assert zone1.home_lose == 0.0

    def test_empty_direction_skipped(self):
        classified = {1: [_make_record(round_num=1, settlement_value=1.0,
                                       settlement_direction="",
                                       home_away_direction="")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone1 = blocks[0].zones[0]
        assert zone1.home_win == 0.0
        assert zone1.home_lose == 0.0
        assert zone1.away_win == 0.0
        assert zone1.away_lose == 0.0

    def test_block_boundary_assignment(self):
        """輪次 10 歸入區段 1，輪次 11 歸入區段 2。"""
        classified = {
            1: [
                _make_record(round_num=10, settlement_value=1.0,
                             settlement_direction="win", home_away_direction="home"),
                _make_record(round_num=11, settlement_value=0.5,
                             settlement_direction="win", home_away_direction="away"),
            ]
        }
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        # round 10 → block 1
        assert blocks[0].zones[0].home_win == 1.0
        assert blocks[0].zones[0].away_win == 0.0
        # round 11 → block 2
        assert blocks[1].zones[0].away_win == 0.5
        assert blocks[1].zones[0].home_win == 0.0

    def test_multiple_records_same_cell(self):
        """同一區段同一區間多筆紀錄累加。"""
        classified = {
            2: [
                _make_record(round_num=1, settlement_value=1.0,
                             settlement_direction="win", home_away_direction="home"),
                _make_record(round_num=3, settlement_value=0.5,
                             settlement_direction="win", home_away_direction="home"),
                _make_record(round_num=5, settlement_value=1.0,
                             settlement_direction="lose", home_away_direction="away"),
            ]
        }
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        zone2 = blocks[0].zones[1]
        assert zone2.home_win == 1.5
        assert zone2.away_lose == 1.0

    def test_block_round_ranges(self):
        agg = RoundBlockAggregator()
        blocks = agg.aggregate({}, block_size=10, max_blocks=6)
        assert blocks[0].round_start == 1
        assert blocks[0].round_end == 10
        assert blocks[5].round_start == 51
        assert blocks[5].round_end == 60

    def test_custom_block_size(self):
        classified = {1: [_make_record(round_num=6, settlement_value=1.0,
                                       settlement_direction="win",
                                       home_away_direction="home")]}
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified, block_size=5, max_blocks=3)
        assert len(blocks) == 3
        # round 6 → block 2 (6~10)
        assert blocks[0].zones[0].home_win == 0.0
        assert blocks[1].zones[0].home_win == 1.0


class TestRoundBlockAggregatorSeasonTotal:
    """season_total() 方法測試。"""

    def test_empty_blocks(self):
        agg = RoundBlockAggregator()
        blocks = agg.aggregate({})
        totals = agg.season_total(blocks)
        assert len(totals) == 9
        for zs in totals:
            assert zs.home_win == 0.0
            assert zs.home_lose == 0.0
            assert zs.away_win == 0.0
            assert zs.away_lose == 0.0

    def test_season_total_sums_all_blocks(self):
        """全季匯總 = 所有區段之和。"""
        classified = {
            1: [
                _make_record(round_num=1, settlement_value=1.0,
                             settlement_direction="win", home_away_direction="home"),
                _make_record(round_num=11, settlement_value=0.5,
                             settlement_direction="lose", home_away_direction="away"),
                _make_record(round_num=25, settlement_value=1.0,
                             settlement_direction="win", home_away_direction="away"),
            ]
        }
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        totals = agg.season_total(blocks)
        zone1_total = totals[0]
        assert zone1_total.home_win == 1.0
        assert zone1_total.away_lose == 0.5
        assert zone1_total.away_win == 1.0
        assert zone1_total.home_lose == 0.0

    def test_season_total_all_four_directions(self):
        """驗證四個方向都能正確匯總。"""
        classified = {
            5: [
                _make_record(round_num=1, settlement_value=1.0,
                             settlement_direction="win", home_away_direction="home"),
                _make_record(round_num=12, settlement_value=0.5,
                             settlement_direction="lose", home_away_direction="home"),
                _make_record(round_num=23, settlement_value=1.0,
                             settlement_direction="win", home_away_direction="away"),
                _make_record(round_num=34, settlement_value=0.5,
                             settlement_direction="lose", home_away_direction="away"),
            ]
        }
        agg = RoundBlockAggregator()
        blocks = agg.aggregate(classified)
        totals = agg.season_total(blocks)
        zone5 = totals[4]
        assert zone5.home_win == 1.0
        assert zone5.home_lose == 0.5
        assert zone5.away_win == 1.0
        assert zone5.away_lose == 0.5
