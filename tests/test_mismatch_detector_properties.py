"""MismatchDetector 屬性測試。"""

from hypothesis import given, settings
from hypothesis import strategies as st

from core.mismatch_detector import FixAction, detect_mismatches, validate_fixes
from core.models import GlobalGroup, LeagueGroupTeams


# -- Strategies --

# Simple ASCII team names for fast generation
team_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8
)

role_st = st.sampled_from(["current", "previous"])


@st.composite
def group_teams_and_pool(draw):
    """Generate random team_pool, LeagueGroupTeams list, and group_lookup."""
    # Generate a universe of unique team names
    all_teams = draw(
        st.lists(team_name_st, min_size=1, max_size=20, unique=True)
    )

    # Split into pool and extra (extra teams are NOT in pool)
    pool_size = draw(st.integers(min_value=0, max_value=len(all_teams)))
    team_pool = set(all_teams[:pool_size])
    extra_teams = all_teams[pool_size:]

    # Generate 1~3 global groups with fixed simple names
    num_groups = draw(st.integers(min_value=1, max_value=3))
    group_lookup: dict[int, GlobalGroup] = {}
    for gid in range(1, num_groups + 1):
        group_lookup[gid] = GlobalGroup(
            id=gid,
            name=f"Group{gid}",
            display_name=f"Display{gid}" if draw(st.booleans()) else None,
            display_order=gid,
        )

    # Build LeagueGroupTeams records
    group_ids = list(group_lookup.keys())
    available_teams = list(team_pool) + extra_teams

    num_records = draw(st.integers(min_value=0, max_value=6))
    all_group_teams: list[LeagueGroupTeams] = []
    for lgt_id in range(1, num_records + 1):
        gid = draw(st.sampled_from(group_ids))
        role = draw(role_st)
        if available_teams:
            teams = draw(
                st.lists(
                    st.sampled_from(available_teams),
                    min_size=0,
                    max_size=min(8, len(available_teams)),
                )
            )
        else:
            teams = []
        all_group_teams.append(
            LeagueGroupTeams(
                id=lgt_id, league_id=1, global_group_id=gid,
                role=role, teams=teams,
            )
        )

    return all_group_teams, team_pool, group_lookup


# Feature: team-name-mismatch-fix, Property 1: 偵測結果等於集合差集且元資料正確
@given(data=group_teams_and_pool())
@settings(max_examples=200)
def test_property1_detect_mismatches_equals_set_difference_with_correct_metadata(data):
    """偵測結果等於集合差集且元資料正確：

    For any set of LeagueGroupTeams records and any team_pool set,
    detect_mismatches SHALL return a MismatchEntry for every team name
    that appears in any group config but not in the team pool, and each
    entry's group_name, global_group_id, and role SHALL match the source
    LeagueGroupTeams record. No team that exists in the team pool shall
    appear in the result.

    **Validates: Requirements 1.1, 1.2, 1.4**
    """
    all_group_teams, team_pool, group_lookup = data

    result = detect_mismatches(all_group_teams, team_pool, group_lookup)

    # -- 1) Result entries == expected set difference (per-record) --
    expected_pairs: list[tuple[int, str, str]] = []
    for lgt in all_group_teams:
        for team in lgt.teams:
            if team not in team_pool:
                expected_pairs.append((lgt.global_group_id, lgt.role, team))

    actual_pairs = [
        (e.global_group_id, e.role, e.team_name) for e in result
    ]

    assert sorted(actual_pairs) == sorted(expected_pairs), (
        f"Mismatch entries differ from expected set difference.\n"
        f"Expected: {sorted(expected_pairs)}\n"
        f"Actual:   {sorted(actual_pairs)}"
    )

    # -- 2) No team in pool appears in result --
    for entry in result:
        assert entry.team_name not in team_pool, (
            f"Team '{entry.team_name}' is in team_pool but appeared in result"
        )

    # -- 3) Metadata correctness: group_name/display_name match lookup --
    for entry in result:
        group = group_lookup.get(entry.global_group_id)
        if group is not None:
            assert entry.group_name == group.name, (
                f"group_name mismatch: expected '{group.name}', "
                f"got '{entry.group_name}'"
            )
            assert entry.group_display_name == group.display_name, (
                f"group_display_name mismatch: expected "
                f"'{group.display_name}', got '{entry.group_display_name}'"
            )


# -- Strategy for Property 3 --

@st.composite
def fix_with_duplicate_target(draw):
    """Generate a FixAction whose new_team already exists in the same group config.

    Ensures the precondition: action="replace", new_team is in the same
    (global_group_id, role) group's existing teams, and new_team != old_team.
    """
    # Generate a set of existing team names (at least 2 so we can pick
    # one as old_team and another as new_team)
    existing_teams = draw(
        st.lists(team_name_st, min_size=2, max_size=10, unique=True)
    )

    # Pick new_team from existing teams (this is the duplicate)
    new_team = draw(st.sampled_from(existing_teams))

    # Pick old_team that is NOT in existing_teams (simulating a mismatch name)
    old_team = draw(
        team_name_st.filter(lambda t: t not in existing_teams)
    )

    global_group_id = draw(st.integers(min_value=1, max_value=100))
    role = draw(role_st)
    group_name = draw(st.sampled_from(["Top", "Weak", "Mid"]))

    fix = FixAction(
        league_id=1,
        group_name=group_name,
        global_group_id=global_group_id,
        role=role,
        old_team=old_team,
        action="replace",
        new_team=new_team,
    )

    # Build a LeagueGroupTeams record that contains the existing teams
    # (including new_team but NOT old_team)
    lgt = LeagueGroupTeams(
        id=1,
        league_id=1,
        global_group_id=global_group_id,
        role=role,
        teams=existing_teams,
    )

    return fix, [lgt]


# Feature: team-name-mismatch-fix, Property 3: 驗證邏輯偵測重複隊名
@given(data=fix_with_duplicate_target())
@settings(max_examples=200)
def test_property3_validate_fixes_detects_duplicate_team_name(data):
    """驗證邏輯偵測重複隊名：

    For any fix action where action="replace" and new_team already exists
    in the same (global_group_id, role) group config, validate_fixes SHALL
    return a non-empty error list containing a message about the duplicate.

    **Validates: Requirements 4.1**
    """
    fix, all_group_teams = data

    errors = validate_fixes([fix], all_group_teams)

    assert len(errors) > 0, (
        f"validate_fixes should return non-empty errors when new_team "
        f"'{fix.new_team}' already exists in group "
        f"(global_group_id={fix.global_group_id}, role='{fix.role}'), "
        f"but got empty list"
    )

    # Verify at least one error message mentions the duplicate team name
    has_relevant_error = any(fix.new_team in err for err in errors)
    assert has_relevant_error, (
        f"Error list should contain a message mentioning the duplicate "
        f"team name '{fix.new_team}', but got: {errors}"
    )


# -- Helper for Property 2 --

def _apply_fixes_to_list(teams: list[str], fixes: list[FixAction]) -> list[str]:
    """Pure list manipulation logic mirroring apply_fixes internals.

    For each fix:
    - replace: swap old_team with new_team at the same position
    - delete: remove old_team from the list
    """
    result = list(teams)
    for fix in fixes:
        if fix.action == "replace" and fix.new_team is not None:
            if fix.old_team in result:
                idx = result.index(fix.old_team)
                result[idx] = fix.new_team
        elif fix.action == "delete":
            if fix.old_team in result:
                result.remove(fix.old_team)
    return result


# -- Strategy for Property 2 --

@st.composite
def teams_and_non_conflicting_fixes(draw):
    """Generate a random team list and non-conflicting fix actions.

    Non-conflicting means:
    - Each old_team appears at most once in fixes
    - Replace targets (new_team) don't collide with existing teams or other replacements
    - Teams targeted for fix actually exist in the initial list
    """
    # Generate a unique initial team list (at least 1 team)
    initial_teams = draw(
        st.lists(team_name_st, min_size=1, max_size=15, unique=True)
    )

    # Decide how many teams to fix (0 to all)
    num_fixes = draw(st.integers(min_value=0, max_value=len(initial_teams)))

    # Pick which teams to fix (random subset, preserving draw order)
    fix_indices = draw(
        st.lists(
            st.sampled_from(range(len(initial_teams))),
            min_size=num_fixes,
            max_size=num_fixes,
            unique=True,
        )
    )
    teams_to_fix = [initial_teams[i] for i in fix_indices]

    # Generate replacement names that don't collide with initial_teams or each other
    all_existing = set(initial_teams)
    replacement_names: list[str] = []
    for _ in teams_to_fix:
        new_name = draw(
            team_name_st.filter(
                lambda t, ex=set(all_existing) | set(replacement_names): t not in ex
            )
        )
        replacement_names.append(new_name)

    # For each team to fix, randomly choose replace or delete
    fixes: list[FixAction] = []
    for i, old_team in enumerate(teams_to_fix):
        action = draw(st.sampled_from(["replace", "delete"]))
        new_team = replacement_names[i] if action == "replace" else None
        fixes.append(
            FixAction(
                league_id=1,
                group_name="TestGroup",
                global_group_id=1,
                role="current",
                old_team=old_team,
                action=action,
                new_team=new_team,
            )
        )

    return initial_teams, fixes


# Feature: team-name-mismatch-fix, Property 2: 修正操作正確套用替換與刪除
@given(data=teams_and_non_conflicting_fixes())
@settings(max_examples=200)
def test_property2_apply_fixes_correctly_replaces_and_deletes(data):
    """修正操作正確套用替換與刪除：

    For any initial team list and any sequence of non-conflicting fix actions
    (replace or delete), after applying the fixes:
    (a) each replaced team name SHALL be swapped to its new name in the
        resulting list,
    (b) each deleted team name SHALL be absent from the resulting list, and
    (c) all other team names SHALL remain unchanged and in their original order.

    **Validates: Requirements 2.5**
    """
    initial_teams, fixes = data

    result = _apply_fixes_to_list(initial_teams, fixes)

    # Build lookup maps for verification
    replaced = {f.old_team: f.new_team for f in fixes if f.action == "replace"}
    deleted = {f.old_team for f in fixes if f.action == "delete"}

    # -- (a) Replaced teams have new names at same positions --
    for old_team, new_team in replaced.items():
        original_idx = initial_teams.index(old_team)
        # Account for deletions of teams before this index
        adjusted_idx = original_idx - sum(
            1 for d in deleted
            if initial_teams.index(d) < original_idx
        )
        assert result[adjusted_idx] == new_team, (
            f"Expected '{new_team}' at adjusted index {adjusted_idx} "
            f"(original index {original_idx}), but got '{result[adjusted_idx]}'"
        )

    # -- (b) Deleted teams are absent --
    for team in deleted:
        assert team not in result, (
            f"Deleted team '{team}' should not be in result, but found it"
        )

    # -- (c) Remaining teams unchanged and in original order --
    untouched = [
        t for t in initial_teams
        if t not in replaced and t not in deleted
    ]
    # Extract the untouched teams from result (filter out new replacement names)
    new_names = set(replaced.values())
    result_untouched = [t for t in result if t not in new_names]

    assert result_untouched == untouched, (
        f"Untouched teams should preserve original order.\n"
        f"Expected: {untouched}\n"
        f"Actual:   {result_untouched}"
    )

    # -- Bonus: total length check --
    expected_len = len(initial_teams) - len(deleted)
    assert len(result) == expected_len, (
        f"Result length should be {expected_len} "
        f"(initial {len(initial_teams)} - deleted {len(deleted)}), "
        f"but got {len(result)}"
    )
