"""Santorini rules engine: a pure functional core plus a stateful shell.

The functional core is a set of immutable, side-effect-free functions over
``BoardState``: ``setup``, ``legal_actions_from``, ``apply_action``,
``successors`` and ``fingerprint``. The stateful :class:`SantoriniEngine`
is a thin mutable shell that tracks the repetition history and exposes
perspective-flipped public state to each bot; it delegates all rules
computation to the core. See ``plans/game-engine-specs.html`` for the
rules and ``plans/santorini-engine-implementation.md`` for the design.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from santorini_types import Action, Coordinate, GameState

if TYPE_CHECKING:
    from santorini_harness import TerminationReason

Fingerprint = tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[int, int], ...],
    tuple[tuple[int, int], ...],
    int,
]

BOARD_SIZE = 5
DOME = 4
PLAYER_WORKERS: tuple[tuple[str, str], tuple[str, str]] = (("A", "B"), ("C", "D"))
PLAYER_WORKER_NAMES: tuple[str, str, str, str] = ("A", "B", "C", "D")
NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


@dataclass(frozen=True)
class BoardState:
    """Immutable canonical board state (independent of any mutable engine).

    ``workers[player][index]`` is that player's worker coordinate in
    ``PLAYER_WORKERS`` order (player 0 = A/B, player 1 = C/D). Heights use
    the same 0--4 encoding as ``GameState`` (4 = dome).
    """

    heights: tuple[tuple[int, ...], ...]
    workers: tuple[tuple[Coordinate, Coordinate], tuple[Coordinate, Coordinate]]
    current_player: int
    turn_number: int
    winner: int | None = None


def _setup_worker_coordinates(seed: int) -> tuple[tuple[int, int], ...]:
    """Sample four distinct squares and map them to A, C, B, D (spec §4)."""
    all_squares = [(row, column) for row in range(BOARD_SIZE) for column in range(BOARD_SIZE)]
    return tuple(random.Random(seed).sample(all_squares, 4))


def setup(seed: int) -> BoardState:
    """Build the opening ``BoardState`` for a deterministic ``seed``."""
    a, c, b, d = _setup_worker_coordinates(seed)
    heights = tuple(tuple(0 for _ in range(BOARD_SIZE)) for _ in range(BOARD_SIZE))
    return BoardState(
        heights=heights,
        workers=((Coordinate(*a), Coordinate(*b)), (Coordinate(*c), Coordinate(*d))),
        current_player=0,
        turn_number=0,
        winner=None,
    )


def _is_occupied(state: BoardState, row: int, column: int) -> bool:
    target = (row, column)
    return any((coordinate.row, coordinate.column) == target for coordinate in _all_workers(state))


def _all_workers(state: BoardState) -> tuple[Coordinate, ...]:
    return state.workers[0] + state.workers[1]


def _in_bounds(row: int, column: int) -> bool:
    return 0 <= row < BOARD_SIZE and 0 <= column < BOARD_SIZE


def _neighbors(row: int, column: int) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for row_offset, column_offset in NEIGHBOR_OFFSETS:
        neighbor_row, neighbor_column = row + row_offset, column + column_offset
        if _in_bounds(neighbor_row, neighbor_column):
            result.append((neighbor_row, neighbor_column))
    return tuple(result)


def _legal_move_destinations(state: BoardState, row: int, column: int) -> tuple[tuple[int, int], ...]:
    source_height = state.heights[row][column]
    destinations: list[tuple[int, int]] = []
    for neighbor_row, neighbor_column in _neighbors(row, column):
        if _is_occupied(state, neighbor_row, neighbor_column):
            continue
        destination_height = state.heights[neighbor_row][neighbor_column]
        if destination_height == DOME:
            continue
        if destination_height > source_height + 1:
            continue
        destinations.append((neighbor_row, neighbor_column))
    return tuple(destinations)


def _legal_build_locations(
    state: BoardState, row: int, column: int, vacated: tuple[int, int] | None = None
) -> tuple[tuple[int, int], ...]:
    """Legal build spots: neighbors of (row, column) that are free and not domed.

    ``vacated`` marks the source of the move: it is adjacent to the
    destination and becomes free once the worker leaves, so it is a legal
    build location even though the pre-move board still shows the worker
    there. (row, column) itself is the destination and is never a build
    candidate (it is not in its own neighbor list).
    """
    locations: list[tuple[int, int]] = []
    for neighbor_row, neighbor_column in _neighbors(row, column):
        if state.heights[neighbor_row][neighbor_column] == DOME:
            continue
        if _is_occupied(state, neighbor_row, neighbor_column) and (neighbor_row, neighbor_column) != vacated:
            continue
        locations.append((neighbor_row, neighbor_column))
    return tuple(locations)


def legal_actions_from(state: BoardState) -> tuple[Action, ...]:
    """All legal complete turns for ``state``'s current player (spec §14).

    For each of the current player's workers, for each legal move
    destination, for each legal build location, emit one ``Action``.
    ``Action.worker`` is 0/1 and indexes the current player's workers.
    """
    actions: list[Action] = []
    for worker_index, worker in enumerate(state.workers[state.current_player]):
        for move_to in _legal_move_destinations(state, worker.row, worker.column):
            for build_at in _legal_build_locations(state, move_to[0], move_to[1], vacated=(worker.row, worker.column)):
                actions.append(
                    Action(
                        worker=worker_index,
                        move_to=Coordinate(*move_to),
                        build_at=Coordinate(*build_at),
                    )
                )
    return tuple(actions)


def apply_action(state: BoardState, action: Action) -> BoardState:
    """Return the immutable ``BoardState`` resulting from a legal ``action``.

    If the worker moves onto a height-3 square the current player wins and
    no build occurs. Otherwise the build square increases by one (capping
    at dome), the turn counter increments, and the player to move flips.
    """
    heights = [list(row) for row in state.heights]
    workers: dict[tuple[int, int], Coordinate] = {}
    for player in (0, 1):
        for index, worker in enumerate(state.workers[player]):
            workers[(player, index)] = worker

    destination = (action.move_to.row, action.move_to.column)
    workers[(state.current_player, action.worker)] = Coordinate(*destination)

    result_workers = (
        (workers[(0, 0)], workers[(0, 1)]),
        (workers[(1, 0)], workers[(1, 1)]),
    )

    if heights[destination[0]][destination[1]] == 3:
        return BoardState(
            heights=tuple(tuple(row) for row in heights),
            workers=result_workers,
            current_player=state.current_player,
            turn_number=state.turn_number,
            winner=state.current_player,
        )

    build = (action.build_at.row, action.build_at.column)
    current_height = heights[build[0]][build[1]]
    heights[build[0]][build[1]] = DOME if current_height == 3 else current_height + 1

    return BoardState(
        heights=tuple(tuple(row) for row in heights),
        workers=result_workers,
        current_player=1 - state.current_player,
        turn_number=state.turn_number + 1,
        winner=None,
    )


def successors(state: BoardState) -> tuple[tuple[Action, BoardState], ...]:
    """All valid next states reachable from ``state`` by one legal action.

    Returns a tuple of ``(action, next_state)`` pairs, one per legal
    complete turn, where ``next_state`` is the immutable board resulting
    from applying ``action``. Terminal positions yield an empty tuple.
    """
    return tuple((action, apply_action(state, action)) for action in legal_actions_from(state))


def fingerprint(state: BoardState) -> Fingerprint:
    """Hashable fingerprint of the complete state (spec §11).

    Includes all heights, all worker locations, and the player to move.
    Worker identities are excluded: A/B (and C/D) are interchangeable
    within a player.
    """
    player_zero = tuple(sorted((w.row, w.column) for w in state.workers[0]))
    player_one = tuple(sorted((w.row, w.column) for w in state.workers[1]))
    return (state.heights, player_zero, player_one, state.current_player)


class SantoriniEngine:
    """A stateful engine for one Santorini game.

    A fresh engine (``SantoriniEngine(seed)``) is fully set up and ready
    to play: setup has been applied and the opening position is recorded
    in the repetition history.
    """

    def __init__(self, seed: int) -> None:
        self.heights: list[list[int]] = []
        self.workers: dict[str, tuple[int, int]] = {}
        self.current_player: int = 0
        self.turn_number: int = 0
        self.state_history: list[Fingerprint] = []
        self.winner: int | None = None
        self.setup(seed)

    def setup(self, seed: int) -> None:
        """Apply the spec §4 setup: A, C, B, D on four distinct squares."""
        a, c, b, d = _setup_worker_coordinates(seed)
        self.heights = [list(row) for row in setup(seed).heights]
        self.workers = {"A": a, "C": c, "B": b, "D": d}
        self.current_player = 0
        self.turn_number = 0
        self.winner = None
        self.state_history = [self._canonical_fingerprint()]

    def to_board_state(self) -> BoardState:
        """Snapshot the engine's current position as an immutable ``BoardState``."""
        a, b = self._player_worker_positions(0)
        c, d = self._player_worker_positions(1)
        return BoardState(
            heights=tuple(tuple(row) for row in self.heights),
            workers=((Coordinate(*a), Coordinate(*b)), (Coordinate(*c), Coordinate(*d))),
            current_player=self.current_player,
            turn_number=self.turn_number,
            winner=self.winner,
        )

    def to_public_state(self, player_id: int) -> GameState:
        """Return the perspective-flipped public state for ``player_id``."""
        mine = self._player_worker_positions(player_id)
        theirs = self._player_worker_positions(1 - player_id)
        return GameState(
            heights=tuple(tuple(row) for row in self.heights),
            current_workers=(
                Coordinate(*mine[0]),
                Coordinate(*mine[1]),
            ),
            opponent_workers=(
                Coordinate(*theirs[0]),
                Coordinate(*theirs[1]),
            ),
            turn_number=self.turn_number,
        )

    def legal_actions(self) -> tuple[Action, ...]:
        """All legal complete turns for the current player (spec §14).

        Delegates to the module-level :func:`legal_actions_from` applied to
        the engine's immutable snapshot.
        """
        return legal_actions_from(self.to_board_state())

    def apply(self, action: Action) -> None:
        """Apply a legal action, mutating internal state.

        Delegates to the module-level :func:`apply_action` and re-syncs the
        engine's mutable fields (including the repetition history) from the
        resulting immutable state.
        """
        next_state = apply_action(self.to_board_state(), action)
        self.heights = [list(row) for row in next_state.heights]
        flat = next_state.workers[0] + next_state.workers[1]
        worker_pairs = [(worker.row, worker.column) for worker in flat]
        self.workers = dict(zip(PLAYER_WORKER_NAMES, worker_pairs, strict=True))
        self.current_player = next_state.current_player
        self.turn_number = next_state.turn_number
        self.winner = next_state.winner
        if next_state.winner is None:
            self.state_history.append(self._canonical_fingerprint())

    def successors(self) -> tuple[tuple[Action, BoardState], ...]:
        """All valid next states reachable from the engine's current position.

        Delegates to the module-level :func:`successors` applied to the
        engine's immutable snapshot. Returns ``(action, next_state)`` pairs.
        """
        return successors(self.to_board_state())

    def check_termination(self, termination_reason: type[TerminationReason]) -> TerminationReason | None:
        """Return a termination reason for the engine-tracked rules, else None.

        Takes the TerminationReason enum class as a parameter to avoid a
        runtime circular import (santorini_harness imports this module).

        Checks win, no-legal-action, and threefold repetition. The
        turn-limit is enforced by the harness loop, not here.
        """
        if self.winner is not None:
            return termination_reason.WIN
        if len(self.legal_actions()) == 0:
            return termination_reason.NO_LEGAL_ACTION
        fingerprint = self.state_history[-1]
        if self.state_history.count(fingerprint) >= 3:
            return termination_reason.REPETITION
        return None

    def _canonical_fingerprint(self) -> Fingerprint:
        """Hashable fingerprint of the complete state (spec §11).

        Delegates to the module-level :func:`fingerprint` applied to the
        engine's immutable snapshot. Worker names are excluded: A/B (and
        C/D) are interchangeable within a player.
        """
        return fingerprint(self.to_board_state())

    def _player_worker_positions(self, player_id: int) -> tuple[tuple[int, int], tuple[int, int]]:
        first, second = PLAYER_WORKERS[player_id]
        return self.workers[first], self.workers[second]
