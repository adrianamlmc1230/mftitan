"""TeamMatcher 與 RecordSplitter 屬性測試：隊名比對篩選與未匹配偵測。"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from core.models import MatchRecord, TeamGroup
from core.matcher import TeamMatcher
from core.splitter import RecordSplitter


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Pool of team names to draw from
_TEAM_POOL = [
    "甲隊", "乙隊", "丙隊", "丁隊", "戊隊",
    "己隊", "庚隊", "辛隊", "壬隊", "癸隊",
    "TeamA", "TeamB", "TeamC", "TeamD", "TeamE",
]

_team_name = st.sampled_from(_TEAM_POOL)

# Generate a MatchRecord with target_team already set
@st.composite
def _match_record_with_target(draw):
    """Generate a MatchRecord with target_team set to either home or away team."""
    home = draw(_team_name)
    away = draw(_team_name.filter(lambda t: t != home))
    # Randomly pick home or away as target
    is_home = draw(st.booleans())
    target = home if is_home else away
    direction = "home" if is_home else "away"
    return MatchRecord(
        round_num=draw(st.integers(min_value=1, max_value=60)),
        home_team=home,
        away_team=away,
        x_value=draw(st.floats(min_value=-1.0, max_value=1.0,
                               allow_nan=False, allow_infinity=False)),
        settlement="主贏" if is_home else "客贏",
        play_type="HDP",
        settlement_value=1.0,
        settlement_direction="win",
        home_away_direction=direction,
        target_team=target,
    )


# Generate a list of records
_records_list = st.lists(
    _match_record_with_target(),
    min_size=1, max_size=20,
)

# Generate a set of team names (subset of pool)
_team_set = st.frozensets(
    _team_name,
    min_size=1, max_size=8,
).map(set)


# ---------------------------------------------------------------------------
# Property 14: 隊名比對篩選正確性
# ---------------------------------------------------------------------------

# Feature: football-quant-v2-refactor, Property 14: 隊名比對篩選正確性
# Validates: Requirements 7.3
@given(records=_records_list, team_names=_team_set)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property14_team_matching_correctness(
    records: list[MatchRecord], team_names: set[str]
) -> None:
    """對任意隊伍分組清單和比賽紀錄集合，比對篩選後的紀錄中，
    每筆紀錄的目標隊伍都應存在於該分組的隊伍清單中。
    """
    matcher = TeamMatcher()
    matched, _unmatched = matcher.match(records, team_names)

    for rec in matched:
        assert rec.target_team in team_names, (
            f"匹配紀錄的 target_team='{rec.target_team}' 不在隊伍清單 {team_names} 中"
        )


# ---------------------------------------------------------------------------
# Property 15: 未匹配隊伍偵測
# ---------------------------------------------------------------------------

# Generate team groups with known team sets
@st.composite
def _team_groups_strategy(draw):
    """Generate 1-3 TeamGroups with teams from the pool."""
    n_groups = draw(st.integers(min_value=1, max_value=3))
    groups = []
    for i in range(n_groups):
        teams = list(draw(st.frozensets(_team_name, min_size=1, max_size=5)))
        groups.append(TeamGroup(
            id=i + 1,
            season_instance_id=1,
            name=f"Group{i+1}",
            display_name=None,
            teams=teams,
        ))
    return groups


# Feature: football-quant-v2-refactor, Property 15: 未匹配隊伍偵測
# Validates: Requirements 7.5
@given(records=_records_list, team_groups=_team_groups_strategy())
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property15_unmatched_team_detection(
    records: list[MatchRecord], team_groups: list[TeamGroup]
) -> None:
    """對任意比賽紀錄集合和所有分組的隊伍清單聯集，
    未匹配隊伍集合應等於紀錄中出現的所有目標隊伍名稱減去已知隊伍清單聯集。
    """
    splitter = RecordSplitter()
    _split_result, unmatched = splitter.split(records, team_groups)

    # Compute expected unmatched
    all_known: set[str] = set()
    for tg in team_groups:
        all_known.update(tg.teams)

    all_target_teams: set[str] = {
        rec.target_team for rec in records if rec.target_team
    }

    expected_unmatched = all_target_teams - all_known

    assert unmatched == expected_unmatched, (
        f"未匹配隊伍不一致：\n"
        f"  實際={unmatched}\n"
        f"  預期={expected_unmatched}\n"
        f"  差異={unmatched.symmetric_difference(expected_unmatched)}"
    )
