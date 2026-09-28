"""Command-line interface for running the Santorini game engine.

Usage::

    python src/run_santorini.py --bot1 bot_a.py --bot2 bot_b.py \\
        [--num-games 5] [--time-limit 3.0] [--seed 42]

This module is not part of the public API contract; it exists solely to let
students run games from their own terminals without writing Python code.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from typing import Any


def _load_bot(path: str) -> Any:
    """Load a bot module from *path* and return its ``choose_action`` function.

    Raises ``ValueError`` if the file does not exist, is not importable, or
    lacks a ``choose_action`` attribute.  The caller should catch this and
    print a user-friendly message before exiting with code 1.
    """
    spec = importlib.util.spec_from_file_location("bot_module", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot create module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["bot_module"] = module
    spec.loader.exec_module(module)
    if hasattr(module, "choose_action"):
        return module.choose_action

    raise ValueError(
        f"{path} does not have a ``choose_action`` function. "
        "The bot must expose: def choose_action(state, legal_actions, time_limit): ..."
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        description="Run the Santorini game engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bot1", required=True, help="Path to the first player's bot Python file.")
    parser.add_argument("--bot2", required=True, help="Path to the second player's bot Python file.")
    parser.add_argument(
        "--num-games",
        type=int,
        default=1,
        help="Number of games to run sequentially (default: 1).",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=2.0,
        help="Maximum seconds per move for both bots (default: 2.0).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for game initialization (default: 0).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns 0 on success, 1 on error."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        bot_a = _load_bot(args.bot1)
        bot_b = _load_bot(args.bot2)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    from santorini_harness import MatchConfig, run_santorini_tournament

    config = MatchConfig(
        move_time_limit_seconds=args.time_limit,
        max_turns=200,
        seed=args.seed,
    )

    results = run_santorini_tournament(bot_a, bot_b, config=config, num_games=args.num_games)
    name = {0: "Bot A", 1: "Bot B"}

    def display(bot_id: int | None) -> str:
        return name[bot_id] if bot_id is not None else "None"

    for i, result in enumerate(results):
        print(f"\n=== Game {i + 1} ===")
        print(f"Winner: {display(result.winner)}")
        print(f"Loser: {display(result.loser)}")
        print(f"Reason: {result.reason.value}")
        print(f"Turns played: {result.turns_played}")
        if result.detail:
            print(f"Detail: {result.detail}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
