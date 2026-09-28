"""Public API contract for the Santorini course-tournament harness.

The official harness owns rules, legal-action generation, timing, and match
logs. Student bots receive an immutable public state and a complete tuple of
legal actions, then return exactly one member of that tuple.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Protocol, TypeAlias

from data_structures import Action, GameState

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


@dataclass(frozen=True)
class GameResult:
    """Outcome of one game; winner is None only for a turn-limit draw."""

    winner: BotId | None
    loser: BotId | None
    reason: TerminationReason
    turns_played: int
    moves: tuple[Action, ...]
    detail: str = ""


class GameEngine(Protocol):
    """Interface implemented by the official, trusted rules engine only."""

    def initial_state(self, seed: int) -> GameState: ...

    def legal_actions(self, state: GameState) -> tuple[Action, ...]: ...

    def apply_action(self, state: GameState, action: Action) -> GameState: ...

    def is_winning_state(self, state: GameState) -> bool: ...


def run_game_for_testing(
    engine: GameEngine,
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig,
) -> GameResult:
    """Run a game in process for local development tests.

    The production harness must call each bot in an isolated worker process,
    terminate it at the deadline, and pass the returned Action to this same
    validation logic.  This helper detects an overrun after a call returns;
    it cannot forcibly stop arbitrary Python code.
    """

    state = engine.initial_state(config.seed)
    current_bot_id: BotId = 0
    moves: list[Action] = []

    for _ in range(config.max_turns):
        legal_actions = engine.legal_actions(state)
        if not legal_actions:
            return GameResult(
                winner=1 - current_bot_id,
                loser=current_bot_id,
                reason=TerminationReason.NO_LEGAL_ACTION,
                turns_played=len(moves),
                moves=tuple(moves),
            )

        bot = bot_a if current_bot_id == 0 else bot_b
        started_at = perf_counter()
        try:
            action = bot(state, legal_actions, config.move_time_limit_seconds)
        except Exception as error:  # The official harness records the traceback.
            return GameResult(
                winner=1 - current_bot_id,
                loser=current_bot_id,
                reason=TerminationReason.BOT_EXCEPTION,
                turns_played=len(moves),
                moves=tuple(moves),
                detail=f"{type(error).__name__}: {error}",
            )

        elapsed_seconds = perf_counter() - started_at
        if elapsed_seconds > config.move_time_limit_seconds:
            return GameResult(
                winner=1 - current_bot_id,
                loser=current_bot_id,
                reason=TerminationReason.TIME_LIMIT,
                turns_played=len(moves),
                moves=tuple(moves),
                detail=f"Action returned after {elapsed_seconds:.6f} seconds.",
            )
        if action not in legal_actions:
            return GameResult(
                winner=1 - current_bot_id,
                loser=current_bot_id,
                reason=TerminationReason.INVALID_ACTION,
                turns_played=len(moves),
                moves=tuple(moves),
                detail="Bot returned an action that was not supplied as legal.",
            )

        moves.append(action)
        state = engine.apply_action(state, action)
        if engine.is_winning_state(state):
            return GameResult(
                winner=current_bot_id,
                loser=1 - current_bot_id,
                reason=TerminationReason.WIN,
                turns_played=len(moves),
                moves=tuple(moves),
            )
        current_bot_id = 1 - current_bot_id

    return GameResult(
        winner=None,
        loser=None,
        reason=TerminationReason.TURN_LIMIT,
        turns_played=len(moves),
        moves=tuple(moves),
    )


def run_sG(
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig | None = None,
    num_games: int = 1,
) -> list[GameResult]:
    """Run one or more games and return the results.

    This is the single programmatic entry point for students.  It wraps
    :func:`run_game_for_testing` with sensible defaults so that a typical
    call looks like::

        from santorini_harness_api import run_sG, MatchConfig

        result = run_sG(my_bot_a, my_bot_b)  # one game, default config
        results = run_sG(bot1, bot2, num_games=5)  # five games

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
            engine=_get_engine(),  # type: ignore — the harness provides this.
            bot_a=bot_a,
            bot_b=bot_b,
            config=game_config,
        )
        results.append(result)

    return results


def _get_engine() -> GameEngine:
    """Return the game engine instance provided by the harness.

    The official harness sets ``sys.modules[__name__].engine`` after
    importing this module.  This helper raises a clear error if it is
    called before that import happens (e.g., during local development).
    """
    try:
        return sys.modules[__name__].engine  # type: ignore — set by harness.
    except AttributeError:
        raise RuntimeError(
            "Game engine not found. Did you run this through the official harness? "
            "For local testing, use run_game_for_testing() directly."
        )
