from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Coordinate:
    """A zero-indexed board coordinate: 0 <= row, column < 5."""

    row: int
    column: int


@dataclass(frozen=True)
class Action:
    """One complete legal Santorini turn.

    ``worker`` is 0 or 1 and indexes ``state.current_workers``.  The current
    player moves that worker to ``move_to`` and then builds at ``build_at``.
    The harness guarantees every supplied Action is fully legal.
    """

    worker: int
    move_to: Coordinate
    build_at: Coordinate


@dataclass(frozen=True)
class GameState:
    """The complete public state from the current player's perspective.

    ``heights[row][column]`` is an integer in [0, 4], where 4 is a dome.
    ``current_workers`` are the current player's workers; ``opponent_workers``
    are the other player's workers.  Worker positions are always distinct.
    ``turn_number`` begins at zero for the opening position.
    """

    heights: tuple[tuple[int, ...], ...]
    current_workers: tuple[Coordinate, Coordinate]
    opponent_workers: tuple[Coordinate, Coordinate]
    turn_number: int
