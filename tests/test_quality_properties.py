"""QualityChecker 屬性測試。"""

from hypothesis import given, settings
from hypothesis import strategies as st

from core.models import ZoneStats, TeamGroup
from core.quality import QualityChecker


# Feature: football-quant-v2-refactor, Property 27: 品質檢查偵測正確性
@given(
    num_zones=st.integers(min_value=1, max_value=9),
)
@settings(max_examples=100)
def test_property27_empty_data_detection(num_zones):
    """全零 ZoneStats 應產生 empty_data 警告。"""
    checker = QualityChecker()
    zones = [ZoneStats(zone_id=i + 1) for i in range(num_zones)]
    issues = checker.check_empty_data(zones, "TEST1", "Top")
    assert len(issues) == 1
    assert issues[0].issue_type == "empty_data"
    assert issues[0].severity == "warning"


@given(
    hw=st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_property27_nonempty_data_no_warning(hw):
    """非全零 ZoneStats 不應產生 empty_data 警告。"""
    checker = QualityChecker()
    zones = [ZoneStats(zone_id=1, home_win=hw)] + [
        ZoneStats(zone_id=i) for i in range(2, 10)
    ]
    issues = checker.check_empty_data(zones, "TEST1", "Top")
    assert len(issues) == 0


@given(
    extra_team=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("L",))),
)
@settings(max_examples=100)
def test_property27_team_mismatch_detection(extra_team):
    """不同時段的不一致隊名清單應產生 team_mismatch 警告。"""
    checker = QualityChecker()
    base_teams = ["TeamA", "TeamB"]
    other_teams = ["TeamA", "TeamB", extra_team] if extra_team not in base_teams else ["TeamA"]

    # 只有在兩邊隊伍不同時才會有警告
    if set(base_teams) == set(other_teams):
        return

    groups_by_timing = {
        "Early": [TeamGroup(id=1, season_instance_id=1, name="Top",
                            display_name=None,
                            teams=base_teams)],
        "RT": [TeamGroup(id=2, season_instance_id=1, name="Top",
                         display_name=None,
                         teams=other_teams)],
    }
    issues = checker.check_team_consistency(groups_by_timing)
    assert len(issues) >= 1
    assert any(i.issue_type == "team_mismatch" for i in issues)
