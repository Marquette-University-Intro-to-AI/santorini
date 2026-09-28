"""Public API contract for the Santorini course-tournament harness.

The official harness owns rules, legal-action generation, timing, and match
logs. Student bots receive an immutable public state and a complete tuple of
legal actions, then return exactly one member of that tuple.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import TypeAlias

from data_structures import Action, GameState
from santorini_engine import SantoriniEngine

BOARD_SIZE = 5
MAX_HEIGHT = 4  # 0: ground; 1--3: building levels; 4: dome
BotId: TypeAlias = int  # Always 0 or 1.


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


def run_game(
    engine: SantoriniEngine,
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig,
) -> GameResult:
    """Run one in-process game against an already-constructed engine.

    The stateful engine owns the rules: this loop only handles bot I/O,
    timing, action validation, and turn-limit enforcement.  The production
    harness must call each bot in an isolated worker process, terminate it
    at the deadline, and pass the returned Action to this same validation
    logic.  This function detects an overrun after a call returns; it
    cannot forcibly stop arbitrary Python code.
    """

    current_bot_id: BotId = 0
    moves: list[Action] = []

    for _ in range(config.max_turns):
        state = engine.to_public_state(current_bot_id)
        legal_actions = engine.legal_actions()
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
        except Exception as error:  # noqa: BLE001 - a bot crash forfeits the game
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
        engine.apply(action)
        reason = engine.check_termination(TerminationReason)
        if reason is not None:
            if reason == TerminationReason.WIN:
                winner, loser = current_bot_id, 1 - current_bot_id
            else:
                # The player to move has no legal action, or the position
                # has repeated: per spec the opponent is credited the win
                # for no-legal-action; repetition is a draw.
                if reason == TerminationReason.REPETITION:
                    winner, loser = None, None
                else:
                    winner, loser = 1 - current_bot_id, current_bot_id
            return GameResult(
                winner=winner,
                loser=loser,
                reason=reason,
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


def run_santorini_tournament(
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig | None = None,
    num_games: int = 1,
) -> list[GameResult]:
    """Run one or more games and return the results.

    This is the single programmatic entry point for students.  It wraps
    :func:`run_game` with sensible defaults so that a typical call looks
    like::

        from santorini_tournament_harness import run_santorini_tournament, MatchConfig

        result = run_santorini_tournament(my_bot_a, my_bot_b)  # one game
        results = run_santorini_tournament(bot1, bot2, num_games=5)  # five games

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
        result = run_game(
            engine=SantoriniEngine(game_config.seed),
            bot_a=bot_a,
            bot_b=bot_b,
            config=game_config,
        )
        results.append(result)

    return results
