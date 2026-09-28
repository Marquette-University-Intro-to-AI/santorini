"""Unit tests for the stateful Santorini rules engine.

Covers setup determinism, legal-action generation (move/build legality),
action application (move, build, dome, win, turn advance), the
perspective transform to the public GameState, and termination detection.
"""

from __future__ import annotations

import copy

from santorini_engine import DOME, PLAYER_WORKERS, SantoriniEngine
from santorini_game_engine import TerminationReason


def _engine_with_positions(
    p0: tuple[int, int],
    p1: tuple[int, int],
    p2: tuple[int, int],
    p3: tuple[int, int],
    heights: list[list[int]] | None = None,
    current_player: int = 0,
    turn_number: int = 0,
    seed: int = 0,
) -> SantoriniEngine:
    """Build an engine with explicit worker positions and heights.

    Positions are assigned A, C, B, D (spec §4 order) regardless of seed;
    the seed is used only to initialize the engine before overwriting.
    """
    engine = SantoriniEngine(seed)
    engine.workers = {"A": p0, "C": p1, "B": p2, "D": p3}
    if heights is not None:
        engine.heights = copy.deepcopy(heights)
    engine.current_player = current_player
    engine.turn_number = turn_number
    # Re-sync the repetition history to the hand-built state.
    engine.state_history = [engine._canonical_fingerprint()]
    return engine


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def test_setup_determinism() -> None:
    e1, e2 = SantoriniEngine(7), SantoriniEngine(7)
    assert e1.workers == e2.workers
    assert e1.heights == e2.heights
    assert e1.current_player == e2.current_player == 0
    assert e1.turn_number == e2.turn_number == 0


def test_setup_distinct_positions() -> None:
    engine = SantoriniEngine(123)
    positions = list(engine.workers.values())
    assert len(set(positions)) == 4
    for row, col in positions:
        assert 0 <= row < 5
        assert 0 <= col < 5


def test_setup_all_squares_valid() -> None:
    engine = SantoriniEngine(99)
    assert all(h == 0 for row in engine.heights for h in row)
    # No worker on a domed square at setup (all heights are 0, but assert
    # the representation explicitly).
    for row, col in engine.workers.values():
        assert engine.heights[row][col] != DOME


def test_setup_order_matches_spec() -> None:
    # Spec §4: P1 places A, P2 places C, P1 places B, P2 places D.
    assert PLAYER_WORKERS[0] == ("A", "B")
    assert PLAYER_WORKERS[1] == ("C", "D")


# ---------------------------------------------------------------------------
# Legal action generation
# ---------------------------------------------------------------------------


def test_initial_legal_actions_nonempty() -> None:
    assert len(SantoriniEngine(42).legal_actions()) > 0


def test_move_height_restriction() -> None:
    # Worker A at (0,0) on height 0; a height-2 block at (0,1) cannot be
    # moved onto (max ascent is +1).
    heights = [[0] * 5 for _ in range(5)]
    heights[0][1] = 2
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), heights=heights, current_player=0)
    dests = {(a.move_to.row, a.move_to.column) for a in engine.legal_actions()}
    assert (0, 1) not in dests


def test_move_downward_any_levels() -> None:
    # Worker A at (0,0) on height 3 can move down to a height-0 square.
    heights = [[0] * 5 for _ in range(5)]
    heights[0][0] = 3
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), heights=heights, current_player=0)
    dests = {(a.move_to.row, a.move_to.column) for a in engine.legal_actions()}
    assert (0, 1) in dests


def test_dome_blocks_movement() -> None:
    heights = [[0] * 5 for _ in range(5)]
    heights[0][1] = DOME
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), heights=heights, current_player=0)
    dests = {(a.move_to.row, a.move_to.column) for a in engine.legal_actions()}
    assert (0, 1) not in dests


def test_dome_blocks_building() -> None:
    heights = [[0] * 5 for _ in range(5)]
    heights[1][1] = DOME
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), heights=heights, current_player=0)
    # Any action whose destination is adjacent to (1,1) must not build there.
    for action in engine.legal_actions():
        r, c = action.move_to.row, action.move_to.column
        if (r, c) in ((0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)):
            assert (action.build_at.row, action.build_at.column) != (1, 1)
    # Sanity: at least one such destination was actually legal.
    dests = {(a.move_to.row, a.move_to.column) for a in engine.legal_actions()}
    assert (0, 0) not in dests  # occupied by A
    assert len(dests) > 0


def test_occupied_blocks_movement() -> None:
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=0)
    dests = {(a.move_to.row, a.move_to.column) for a in engine.legal_actions()}
    assert (0, 0) not in dests  # A
    assert (0, 2) not in dests  # B
    assert (4, 4) not in dests  # C
    assert (4, 3) not in dests  # D


def test_occupied_blocks_building() -> None:
    # A square occupied by any worker after the move is not a build
    # location. The mover's source square is an exception: it becomes free
    # once the worker leaves, so building back there is legal (spec §14).
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=0)
    occupied_after = {(4, 4), (4, 3)}  # P1 workers never move
    for action in engine.legal_actions():
        build = (action.build_at.row, action.build_at.column)
        assert build not in occupied_after


def test_corner_worker_fewer_actions() -> None:
    # Worker at (0,0) has 3 adjacent squares vs 8 for one at (2,2).
    corner = _engine_with_positions((0, 0), (4, 4), (4, 3), (4, 2), current_player=0)
    assert len(corner._legal_move_destinations(0, 0)) == 3
    center = _engine_with_positions((2, 2), (4, 4), (4, 3), (4, 2), current_player=0)
    assert len(center._legal_move_destinations(2, 2)) == 8


def test_worker_index_perspective() -> None:
    # Player 1 moves: worker index 0 must correspond to C, index 1 to D.
    engine = _engine_with_positions((4, 4), (0, 0), (4, 3), (0, 2), current_player=1)
    actions_by_worker: dict[int, set[tuple[int, int]]] = {0: set(), 1: set()}
    for action in engine.legal_actions():
        actions_by_worker[action.worker].add((action.move_to.row, action.move_to.column))
    assert actions_by_worker[0] == set(engine._legal_move_destinations(0, 0))
    assert actions_by_worker[1] == set(engine._legal_move_destinations(0, 2))


def test_all_actions_are_complete_turns() -> None:
    # Spec §14: every (worker, move, build) combination is one Action.
    engine = SantoriniEngine(5)
    actions = engine.legal_actions()
    assert len(actions) > 0
    assert len(set(actions)) == len(actions)
    for action in actions:
        assert action.worker in (0, 1)
        assert action.move_to != action.build_at


# ---------------------------------------------------------------------------
# Apply action
# ---------------------------------------------------------------------------


def test_apply_move_updates_position() -> None:
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=0)
    action = next(a for a in engine.legal_actions() if (a.move_to.row, a.move_to.column) == (0, 1) and a.worker == 0)
    engine.apply(action)
    assert engine.workers["A"] == (0, 1)


def test_apply_build_increments_height() -> None:
    # A at (0,0), B at (4,4): A moves to (0,1) and builds back at (0,0).
    heights = [[0] * 5 for _ in range(5)]
    engine = _engine_with_positions((0, 0), (4, 4), (4, 3), (4, 2), heights=heights, current_player=0)
    action = next(
        a
        for a in engine.legal_actions()
        if (a.move_to.row, a.move_to.column) == (0, 1) and (a.build_at.row, a.build_at.column) == (0, 0)
    )
    engine.apply(action)
    assert engine.heights[0][0] == 1


def test_apply_build_dome() -> None:
    # A moves onto (0,1) and builds on the height-3 square (0,0): dome.
    heights = [[0] * 5 for _ in range(5)]
    heights[0][0] = 3
    engine = _engine_with_positions((0, 0), (4, 4), (4, 3), (4, 2), heights=heights, current_player=0)
    action = next(
        a
        for a in engine.legal_actions()
        if (a.move_to.row, a.move_to.column) == (0, 1) and (a.build_at.row, a.build_at.column) == (0, 0)
    )
    engine.apply(action)
    assert engine.heights[0][0] == DOME


def test_apply_win_detection() -> None:
    # A on height 2 at (0,0) can move up onto the height-3 square (0,1)
    # (max ascent is +1: 3 <= 2 + 1) and wins immediately.
    heights = [[0] * 5 for _ in range(5)]
    heights[0][0] = 2
    heights[0][1] = 3
    engine = _engine_with_positions((0, 0), (4, 4), (4, 3), (4, 2), heights=heights, current_player=0)
    action = next(a for a in engine.legal_actions() if (a.move_to.row, a.move_to.column) == (0, 1))
    engine.apply(action)
    assert engine.winner == 0
    assert engine.heights[0][1] == 3  # build skipped
    assert engine.turn_number == 0  # no turn advanced


def test_apply_advances_turn() -> None:
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=0)
    engine.apply(engine.legal_actions()[0])
    assert engine.turn_number == 1
    assert engine.current_player == 1
    engine.apply(engine.legal_actions()[0])
    assert engine.turn_number == 2
    assert engine.current_player == 0


# ---------------------------------------------------------------------------
# Perspective transform
# ---------------------------------------------------------------------------


def test_perspective_player0() -> None:
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=0)
    state = engine.to_public_state(0)
    assert {(c.row, c.column) for c in state.current_workers} == {(0, 0), (0, 2)}
    assert {(c.row, c.column) for c in state.opponent_workers} == {(4, 4), (4, 3)}


def test_perspective_player1() -> None:
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=1)
    state = engine.to_public_state(1)
    assert {(c.row, c.column) for c in state.current_workers} == {(4, 4), (4, 3)}
    assert {(c.row, c.column) for c in state.opponent_workers} == {(0, 0), (0, 2)}


def test_perspective_dome_as_4() -> None:
    heights = [[0] * 5 for _ in range(5)]
    heights[3][3] = DOME
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), heights=heights, current_player=0)
    state = engine.to_public_state(0)
    assert state.heights[3][3] == 4


def test_perspective_turn_number() -> None:
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), current_player=0, turn_number=17)
    assert engine.to_public_state(0).turn_number == 17
    assert engine.to_public_state(1).turn_number == 17


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------


def test_no_legal_action() -> None:
    # Both of player 0's workers completely walled in by domes.
    heights = [[0] * 5 for _ in range(5)]
    for r, c in ((0, 1), (1, 0), (1, 1)):
        heights[r][c] = DOME  # walls (0,0)
    for r, c in ((0, 3), (1, 2), (1, 3)):
        heights[r][c] = DOME  # walls (0,2)
    engine = _engine_with_positions((0, 0), (4, 4), (0, 2), (4, 3), heights=heights, current_player=0)
    assert engine.legal_actions() == ()
    assert engine.check_termination(TerminationReason) == TerminationReason.NO_LEGAL_ACTION


def test_win_termination() -> None:
    heights = [[0] * 5 for _ in range(5)]
    heights[0][0] = 2
    heights[0][1] = 3
    engine = _engine_with_positions((0, 0), (4, 4), (4, 3), (4, 2), heights=heights, current_player=0)
    engine.apply(next(a for a in engine.legal_actions() if (a.move_to.row, a.move_to.column) == (0, 1)))
    assert engine.check_termination(TerminationReason) == TerminationReason.WIN


def test_threefold_repetition() -> None:
    # The opening fingerprint was recorded at setup (1st occurrence). Play
    # two moves and hand-craft the engine state back to the opening position
    # twice: 3 identical fingerprints → repetition.
    engine = SantoriniEngine(11)
    opening = engine.state_history[-1]
    engine.apply(engine.legal_actions()[0])
    engine.apply(engine.legal_actions()[0])
    engine.state_history[-1] = opening
    engine.state_history.append(opening)
    assert len(engine.state_history) == 4
    assert engine.check_termination(TerminationReason) == TerminationReason.REPETITION


def test_two_repeats_not_draw() -> None:
    engine = SantoriniEngine(11)
    opening = engine.state_history[-1]
    engine.apply(engine.legal_actions()[0])
    engine.state_history[-1] = opening  # 2nd occurrence
    assert engine.check_termination(TerminationReason) is None


def test_non_repeating_position_not_draw() -> None:
    engine = SantoriniEngine(11)
    engine.apply(engine.legal_actions()[0])
    engine.apply(engine.legal_actions()[0])
    assert engine.state_history[-1] != engine.state_history[0]
    assert engine.check_termination(TerminationReason) is None
