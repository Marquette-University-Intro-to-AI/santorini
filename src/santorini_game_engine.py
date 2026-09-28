"""Public API contract for the Santorini course-tournament harness.

The official harness owns rules, legal-action generation, timing, and match
logs. Student bots receive an immutable public state and a complete tuple of
legal actions, then return exactly one member of that tuple.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, TypeAlias

from data_structures import Action, GameState
from santorini_engine import SantoriniEngine

BOARD_SIZE = 5
MAX_HEIGHT = 4  # 0: ground; 1--3: building levels; 4: dome
BotId: TypeAlias = int  # Always 0 or 1.


class SantoriniBot(Protocol):
    """The only callable interface a student bot must expose."""

    def choose_action(
        self,
        state: GameState,
        legal_actions: tuple[Action, ...],
        time_limit_seconds: float,
    ) -> Action:
        """Return exactly one Action from legal_actions.

        The function must not mutate inputs, print match data, access the
        network, or read files outside its own submission directory.
        """


BotFunction: TypeAlias = Callable[[GameState, tuple[Action, ...], float], Action]


@dataclass(frozen=True)
class BotSpec:
    """A bot selected for a match by the harness or command-line runner.

    ``file_path`` is the submitted Python file.  The official runner loads
    each path in a fresh worker process, so both players may use ``bot.py``.
    ``entry_point`` normally remains ``choose_action``.
    """

    file_path: str
    display_name: str
    entry_point: str = "choose_action"


@dataclass(frozen=True)
class MatchConfig:
    """Conditions shared by both bots in one game."""

    move_time_limit_seconds: float = 2.0
    max_turns: int = 200
    seed: int = 0


class TerminationReason(str, Enum):
    WIN = "win"
    NO_LEGAL_ACTION = "no_legal_action"
    INVALID_ACTION = "invalid_action"
    BOT_EXCEPTION = "bot_exception"
    TIME_LIMIT = "time_limit"
    TURN_LIMIT = "turn_limit"
    REPETITION = "repetition"


@dataclass(frozen=True)
class GameResult:
    """Outcome of one game; winner is None only for a turn-limit draw."""

    winner: BotId | None
    loser: BotId | None
    reason: TerminationReason
    turns_played: int
    moves: tuple[Action, ...]
    detail: str = ""


def run_santorini_game(
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig | None = None,
    num_games: int = 1,
) -> list[GameResult]:
    """Run one or more games and return the results.

    This is the single programmatic entry point for students.  It wraps
    :func:`run_game_for_testing` with sensible defaults so that a typical
    call looks like::

        from santorini_game_engine import run_santorini_game, MatchConfig

        result = run_santorini_game(my_bot_a, my_bot_b)  # one game
        results = run_santorini_game(bot1, bot2, num_games=5)  # five games

    Parameters
    ----------
    bot_a : callable
        The first player's ``choose_action`` function.
    bot_b : callable
        The second player's ``choose_action`` function.
    config : MatchConfig | None
        Game conditions shared by both bots.  Defaults to a fresh
        ``MatchConfig()`` with the standard limits (2 seconds per move,
        200 turns).
    num_games : int
        Number of games to run sequentially.  Games are seeded from
        ``config.seed + game_index`` so that each call is reproducible
        when ``num_games == 1`` and deterministic across runs for any
        fixed seed value.

    Returns
    -------
    list[GameResult]
        One result per game, in the order they were played.
    """
    # Imported here (not at module top) because tests/test_helpers.py imports
    # this module; a top-level import would be circular.
    from tests.test_helpers import run_game_for_testing

    if config is None:
        config = MatchConfig()

    results: list[GameResult] = []
    for i in range(num_games):
        game_config = MatchConfig(
            move_time_limit_seconds=config.move_time_limit_seconds,
            max_turns=config.max_turns,
            seed=config.seed + i,
        )
        result = run_game_for_testing(
            engine=SantoriniEngine(game_config.seed),
            bot_a=bot_a,
            bot_b=bot_b,
            config=game_config,
        )
        results.append(result)

    return results
