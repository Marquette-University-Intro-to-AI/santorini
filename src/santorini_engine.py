"""Stateful Santorini rules engine.

Maintains the canonical game state (worker identity A/B/C/D, current
player, turn count, repetition history) and exposes perspective-flipped
public state to each bot. See ``plans/game-engine-specs.html`` for the
rules and ``plans/santorini-engine-implementation.md`` for the design.
"""

from __future__ import annotations

import random
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
        all_squares = [(row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE)]
        chosen = random.Random(seed).sample(all_squares, 4)
        self.heights = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.workers = {
            "A": chosen[0],
            "C": chosen[1],
            "B": chosen[2],
            "D": chosen[3],
        }
        self.current_player = 0
        self.turn_number = 0
        self.winner = None
        self.state_history = [self._canonical_fingerprint()]

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
        """Generate all legal complete turns for the current player.

        Follows spec §14: for each of the current player's workers, for
        each legal move destination, for each legal build location, emit
        one ``Action``. Worker index 0/1 maps to the player's first/second
        worker in ``PLAYER_WORKERS`` order.
        """
        first, second = PLAYER_WORKERS[self.current_player]
        actions: list[Action] = []
        for worker_index, name in enumerate((first, second)):
            row, col = self.workers[name]
            for move_to in self._legal_move_destinations(row, col):
                for build_at in self._legal_build_locations(move_to[0], move_to[1], vacated=(row, col)):
                    actions.append(
                        Action(
                            worker=worker_index,
                            move_to=Coordinate(*move_to),
                            build_at=Coordinate(*build_at),
                        )
                    )
        return tuple(actions)

    def apply(self, action: Action) -> None:
        """Apply a legal action, mutating internal state.

        If the worker moves onto a height-3 square the current player
        wins and no build occurs. Otherwise the engine builds at
        ``action.build_at`` (height + 1, capping at dome).
        """
        first, second = PLAYER_WORKERS[self.current_player]
        name = first if action.worker == 0 else second
        dest = (action.move_to.row, action.move_to.column)
        self.workers[name] = dest

        if self.heights[dest[0]][dest[1]] == 3:
            self.winner = self.current_player
            return

        build = (action.build_at.row, action.build_at.column)
        current = self.heights[build[0]][build[1]]
        self.heights[build[0]][build[1]] = DOME if current == 3 else current + 1

        self.turn_number += 1
        self.current_player = 1 - self.current_player
        self.state_history.append(self._canonical_fingerprint())

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

        Includes all heights, all worker locations, and the player to
        move. Worker names are excluded: A/B (and C/D) are interchangeable
        within a player.
        """
        p0 = tuple(sorted(self._player_worker_positions(0)))
        p1 = tuple(sorted(self._player_worker_positions(1)))
        return (
            tuple(tuple(row) for row in self.heights),
            p0,
            p1,
            self.current_player,
        )

    def _player_worker_positions(self, player_id: int) -> tuple[tuple[int, int], tuple[int, int]]:
        first, second = PLAYER_WORKERS[player_id]
        return self.workers[first], self.workers[second]

    def _is_occupied(self, row: int, col: int) -> bool:
        return any(pos == (row, col) for pos in self.workers.values())

    def _in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

    def _neighbors(self, row: int, col: int) -> tuple[tuple[int, int], ...]:
        result: list[tuple[int, int]] = []
        for d_row, d_col in NEIGHBOR_OFFSETS:
            n_row, n_col = row + d_row, col + d_col
            if self._in_bounds(n_row, n_col):
                result.append((n_row, n_col))
        return tuple(result)

    def _legal_move_destinations(self, row: int, col: int) -> tuple[tuple[int, int], ...]:
        source_height = self.heights[row][col]
        destinations: list[tuple[int, int]] = []
        for n_row, n_col in self._neighbors(row, col):
            if self._is_occupied(n_row, n_col):
                continue
            dest_height = self.heights[n_row][n_col]
            if dest_height == DOME:
                continue
            if dest_height > source_height + 1:
                continue
            destinations.append((n_row, n_col))
        return tuple(destinations)

    def _legal_build_locations(
        self, row: int, col: int, vacated: tuple[int, int] | None = None
    ) -> tuple[tuple[int, int], ...]:
        """Legal build spots: neighbors of (row, col) that are free and not domed.

        ``vacated`` marks the source of the move: it is adjacent to the
        destination and becomes free once the worker leaves, so it is a
        legal build location even though the occupancy snapshot (taken
        before the move) still shows the worker there. (row, col) itself
        is the destination and is never a build candidate (it is not in
        its own neighbor list).
        """
        locations: list[tuple[int, int]] = []
        for n_row, n_col in self._neighbors(row, col):
            if self.heights[n_row][n_col] == DOME:
                continue
            if self._is_occupied(n_row, n_col) and (n_row, n_col) != vacated:
                continue
            locations.append((n_row, n_col))
        return tuple(locations)
