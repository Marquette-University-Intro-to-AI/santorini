"""Integration tests for the game harness (plan step 7).

Covers ``run_game`` and ``run_santorini_tournament`` end to end:
win, invalid action, bot exception, time limit, turn limit, multiple
games, default configuration, and reproducibility.
"""

from __future__ import annotations

import time

from santorini_types import Action, GameState
from santorini_engine import SantoriniEngine
from santorini_harness import (
    BotFunction,
    GameResult,
    MatchConfig,
    TerminationReason,
    run_game,
    run_santorini_tournament,
)


# Always play the first offered legal action.
def first_move_bot(state: GameState, actions: tuple[Action, ...], limit: float) -> Action:
    return actions[0]


def _height_hunting_bot() -> BotFunction:
    """Prefer moves that win immediately; otherwise take the first action."""

    def bot(state: GameState, actions: tuple[Action, ...], limit: float) -> Action:
        for action in actions:
            row, column = action.move_to.row, action.move_to.column
            if state.heights[row][column] == 3:
                return action
        return actions[0]

    return bot


def _no_win_bot() -> BotFunction:
    """Prefer non-winning actions so a short game can run to the turn limit."""

    def bot(state: GameState, actions: tuple[Action, ...], limit: float) -> Action:
        for action in actions:
            row, column = action.move_to.row, action.move_to.column
            if state.heights[row][column] != 3:
                return action
        return actions[0]

    return bot


def _sleepy_bot(delay_seconds: float) -> BotFunction:
    def bot(state: GameState, actions: tuple[Action, ...], limit: float) -> Action:
        time.sleep(delay_seconds)
        return actions[0]

    return bot


def _crashing_bot() -> BotFunction:
    def bot(state: GameState, actions: tuple[Action, ...], limit: float) -> Action:
        raise ValueError("bot on purpose")

    return bot


def _invalid_action_bot() -> BotFunction:
    def bot(state: GameState, actions: tuple[Action, ...], limit: float) -> Action:
        return Action(worker=9, move_to=actions[0].move_to, build_at=actions[0].build_at)

    return bot


def _fresh_engine(seed: int) -> SantoriniEngine:
    return SantoriniEngine(seed)


def test_smoke_full_game_template_bot() -> None:
    """A full game between two starter bots runs to a terminal result."""
    from starter_bot import choose_action

    result = run_santorini_tournament(choose_action, choose_action, MatchConfig(seed=1), num_games=1)[0]
    assert result.reason is not None
    assert len(result.moves) == result.turns_played
    if result.reason == TerminationReason.WIN:
        assert result.winner is not None and result.loser is not None
    else:
        assert result.winner is None and result.loser is None


def test_run_game_win() -> None:
    """A bot that seizes a height-3 destination wins and the opponent loses."""
    result = run_santorini_tournament(_height_hunting_bot(), _height_hunting_bot(), MatchConfig(seed=0), num_games=1)[0]
    assert result.reason == TerminationReason.WIN
    assert (result.winner, result.loser) == (0, 1) or (result.winner, result.loser) == (1, 0)
    assert result.winner is not None and result.loser is not None
    assert len(result.moves) == result.turns_played


def test_run_game_invalid_action() -> None:
    """An action not in the supplied legal tuple loses the game for its bot."""
    engine = _fresh_engine(0)
    result = run_game(engine, _invalid_action_bot(), first_move_bot, MatchConfig(seed=0))
    assert result.reason == TerminationReason.INVALID_ACTION
    assert result.loser == 0
    assert result.winner == 1
    assert result.detail


def test_run_game_bot_exception() -> None:
    """A bot that raises an exception loses with BOT_EXCEPTION."""
    engine = _fresh_engine(0)
    result = run_game(engine, _crashing_bot(), first_move_bot, MatchConfig(seed=0))
    assert result.reason == TerminationReason.BOT_EXCEPTION
    assert result.loser == 0
    assert result.winner == 1
    assert "ValueError" in result.detail


def test_run_game_time_limit() -> None:
    """A bot whose call exceeds the limit loses with TIME_LIMIT."""
    engine = _fresh_engine(0)
    config = MatchConfig(seed=0, move_time_limit_seconds=0.05)
    result = run_game(engine, _sleepy_bot(0.1), first_move_bot, config)
    assert result.reason == TerminationReason.TIME_LIMIT
    assert result.loser == 0
    assert result.winner == 1
    assert "seconds" in result.detail


def test_run_game_turn_limit() -> None:
    """Exhausting the turn budget ends in a draw (no winner or loser)."""
    engine = _fresh_engine(0)
    config = MatchConfig(seed=0, max_turns=3)
    result = run_game(engine, _no_win_bot(), _no_win_bot(), config)
    assert result.reason == TerminationReason.TURN_LIMIT
    assert result.winner is None
    assert result.loser is None
    assert result.turns_played == 3
    assert len(result.moves) == 3


def test_run_santorini_tournament_multiple_games() -> None:
    """num_games=5 returns five results seeded from config.seed + i."""
    results = run_santorini_tournament(first_move_bot, first_move_bot, MatchConfig(seed=10), num_games=5)
    assert len(results) == 5
    # Each game i used seed 10 + i, so the opening positions differ across
    # games; the results must at least form a complete, ordered list.
    assert all(isinstance(r, GameResult) for r in results)
    assert all(r.reason in TerminationReason for r in results)


def test_run_santorini_tournament_default_config() -> None:
    """Calling without a config uses 2.0 s per move and 200 turns."""
    config = MatchConfig()
    assert config.move_time_limit_seconds == 2.0
    assert config.max_turns == 200
    results = run_santorini_tournament(first_move_bot, first_move_bot, num_games=1)
    assert len(results) == 1
    assert results[0].reason in TerminationReason


def test_run_santorini_tournament_reproducible() -> None:
    """Same bots and seed produce identical result sequences."""
    config = MatchConfig(seed=7)
    first = run_santorini_tournament(first_move_bot, first_move_bot, config, num_games=3)
    second = run_santorini_tournament(first_move_bot, first_move_bot, config, num_games=3)
    assert len(first) == len(second)
    for r1, r2 in zip(first, second, strict=True):
        assert (r1.winner, r1.loser, r1.reason, r1.turns_played, r1.moves) == (
            r2.winner,
            r2.loser,
            r2.reason,
            r2.turns_played,
            r2.moves,
        )
