# Santorini harness internals

This file documents the harness internals and repository layout. Student
facing material (bot interface, `successors`, programmatic API, CLI usage,
restrictions) lives in [README.md](README.md).

## Harness responsibilities

The harness, not the student bot, is responsible for:

1. Creating the starting state and the complete legal-action list.
2. Enforcing the per-move time limit.
3. Validating the returned action against the supplied legal-action tuple.
4. Applying the action, detecting wins, no-legal-move losses, repetition, and
   enforcing the maximum game length.
5. Recording the seed, actions, and final outcome in the returned results.

`run_game` in `santorini_harness` drives one in-process game
against a given engine and two bot functions. The official tournament runner
should additionally use process isolation because an in-process Python call
cannot safely terminate a bot that hangs.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/santorini_types.py` | `Coordinate`, `Action`, `GameState` (public API types). |
| `src/santorini_engine.py` | `SantoriniEngine`: setup, legal actions, apply, termination. |
| `src/santorini_harness.py` | `MatchConfig`, `TerminationReason`, `GameResult`, `run_game`, `run_santorini_tournament`. |
| `src/run_santorini.py` | Local game runner. |
| `src/starter_bot.py` | Minimal example bot. |
| `tests/` | Engine unit tests and harness integration tests. |
