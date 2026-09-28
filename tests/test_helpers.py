"""Local development helper: in-process game runner for tests.

Moved from ``src/santorini_game_engine.py`` (step 5 of
``plans/santorini-engine-implementation.md``). The public harness module
re-exports this for use by ``run_santorini_game``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

# Make the top-level modules under src/ importable without an install step.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from santorini_engine import SantoriniEngine
from santorini_game_engine import (
    BotFunction,
    GameResult,
    MatchConfig,
    TerminationReason,
)
from data_structures import Action

BotId = int  # Always 0 or 1.


def run_game_for_testing(
    engine: SantoriniEngine,
    bot_a: BotFunction,
    bot_b: BotFunction,
    config: MatchConfig,
) -> GameResult:
    """Run a game in process for local development tests.

    The production harness must call each bot in an isolated worker process,
    terminate it at the deadline, and pass the returned Action to this same
    validation logic.  This helper detects an overrun after a call returns;
    it cannot forcibly stop arbitrary Python code.

    The stateful engine owns the rules: this loop only handles bot I/O,
    timing, action validation, and turn-limit enforcement.
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
