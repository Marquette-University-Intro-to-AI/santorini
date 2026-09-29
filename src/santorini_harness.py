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

from santorini_engine import (
    BoardState,
    Fingerprint,
    SantoriniEngine,
    apply_action,
    fingerprint,
    legal_actions_from,
    public_state_for,
    setup,
    termination_reason,
)
from santorini_types import Action, GameState

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


@dataclass(frozen=True)
class _MatchState:
    """Immutable match state threaded through the pure game loop.

    ``board`` is the canonical position; ``fingerprint_history`` is the
    chronological sequence of fingerprints of every non-terminal position
    reached, including the opening position. ``moves`` accumulates the
    actions played so far. ``current_bot_id`` is the player to move.
    """

    board: BoardState
    fingerprint_history: tuple[Fingerprint, ...]
    moves: tuple[Action, ...]
    current_bot_id: BotId


def _initial_match_state(board: BoardState) -> _MatchState:
    """Seed a fresh match from the opening ``BoardState`` (opening position in history)."""
    return _MatchState(
        board=board,
        fingerprint_history=(fingerprint(board),),
        moves=(),
        current_bot_id=0,
    )


def _step_match(
    match: _MatchState,
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig,
) -> _MatchState | GameResult:
    """Advance the match by one bot turn; returns the next state or a terminal :class:`GameResult`."""
    legal_actions = legal_actions_from(match.board)
    if not legal_actions:
        return GameResult(
            winner=1 - match.current_bot_id,
            loser=match.current_bot_id,
            reason=TerminationReason.NO_LEGAL_ACTION,
            turns_played=len(match.moves),
            moves=match.moves,
        )

    bot = bot_a if match.current_bot_id == 0 else bot_b
    public_state = public_state_for(match.board, match.current_bot_id)
    started_at = perf_counter()
    try:
        action = bot(public_state, legal_actions, config.move_time_limit_seconds)
    except Exception as error:  # noqa: BLE001 - a bot crash forfeits the game
        return GameResult(
            winner=1 - match.current_bot_id,
            loser=match.current_bot_id,
            reason=TerminationReason.BOT_EXCEPTION,
            turns_played=len(match.moves),
            moves=match.moves,
            detail=f"{type(error).__name__}: {error}",
        )

    elapsed_seconds = perf_counter() - started_at
    if elapsed_seconds > config.move_time_limit_seconds:
        return GameResult(
            winner=1 - match.current_bot_id,
            loser=match.current_bot_id,
            reason=TerminationReason.TIME_LIMIT,
            turns_played=len(match.moves),
            moves=match.moves,
            detail=f"Action returned after {elapsed_seconds:.6f} seconds.",
        )
    if action not in legal_actions:
        return GameResult(
            winner=1 - match.current_bot_id,
            loser=match.current_bot_id,
            reason=TerminationReason.INVALID_ACTION,
            turns_played=len(match.moves),
            moves=match.moves,
            detail="Bot returned an action that was not supplied as legal.",
        )

    next_board = apply_action(match.board, action)
    moves = match.moves + (action,)
    history = match.fingerprint_history
    if next_board.winner is None:
        history = history + (fingerprint(next_board),)
    next_match = _MatchState(
        board=next_board,
        fingerprint_history=history,
        moves=moves,
        current_bot_id=next_board.current_player,
    )
    reason = termination_reason(next_board, history, TerminationReason)
    if reason is None:
        return next_match
    if reason == TerminationReason.WIN:
        winner, loser = match.current_bot_id, 1 - match.current_bot_id
    elif reason == TerminationReason.REPETITION:
        winner, loser = None, None
    else:
        # NO_LEGAL_ACTION: the player to move has no legal action, so per
        # spec the opponent is credited the win.
        winner, loser = 1 - match.current_bot_id, match.current_bot_id
    return GameResult(
        winner=winner,
        loser=loser,
        reason=reason,
        turns_played=len(moves),
        moves=moves,
    )


def _run_match(
    initial: _MatchState,
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig,
) -> GameResult:
    """Drive the pure match state machine to a terminal :class:`GameResult`."""
    match = initial
    for _ in range(config.max_turns):
        outcome = _step_match(match, bot_a, bot_b, config)
        if isinstance(outcome, GameResult):
            return outcome
        match = outcome
    return GameResult(
        winner=None,
        loser=None,
        reason=TerminationReason.TURN_LIMIT,
        turns_played=len(match.moves),
        moves=match.moves,
    )


def run_game(
    engine: SantoriniEngine,
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig,
) -> GameResult:
    """Run one in-process game against an already-constructed engine.

    The engine is read only for its opening position and is never mutated:
    the match runs as a pure state machine over the immutable engine core.
    This function handles bot I/O, timing, action validation, and
    turn-limit enforcement.  The production harness must call each bot in
    an isolated worker process, terminate it at the deadline, and pass the
    returned Action to this same validation logic.  This function detects
    an overrun after a call returns; it cannot forcibly stop arbitrary
    Python code.
    """
    return _run_match(_initial_match_state(engine.to_board_state()), bot_a, bot_b, config)


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

        from santorini_harness import run_santorini_tournament, MatchConfig

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
        initial = _initial_match_state(setup(game_config.seed))
        results.append(_run_match(initial, bot_a, bot_b, game_config))

    return results
