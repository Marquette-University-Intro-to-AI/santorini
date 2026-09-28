# Santorini tournament harness

## Student bot interface

Every submission contains a Python file, normally `bot.py`, with exactly this
top-level function:

```python
from data_structures import Action, GameState

def choose_action(
    state: GameState,
    legal_actions: tuple[Action, ...],
    time_limit_seconds: float,
) -> Action:
    ...
```

The function must return one member of `legal_actions` before the time limit.
It may return either the supplied `Action` object or an equal newly constructed
`Action`. Do not return an integer, string, tuple, or `None`.

The state is from the perspective of the player whose bot is being called:

| Field | Meaning |
| --- | --- |
| `state.heights` | Immutable 5 x 5 tuple of heights: 0 is ground, 1--3 are building levels, and 4 is a dome. |
| `state.current_workers` | The two workers of the bot currently choosing an action. |
| `state.opponent_workers` | The opponent's two workers. |
| `state.turn_number` | Number of completed turns since the opening state. |
| `Action.worker` | Index 0 or 1 into `state.current_workers`. |
| `Action.move_to` | Legal destination for that worker. |
| `Action.build_at` | Legal build location after the move. |

The harness supplies complete legal actions rather than asking students to
generate them. This keeps rules implementation separate from AI design and
makes an invalid response unambiguous.

## Requirements and restrictions

- Treat `state` and `legal_actions` as read-only.
- Do not use the network, subprocesses, interprocess communication, or files
  outside the submitted bot directory.
- Do not depend on wall-clock time except to finish before the deadline.
- A bot may load a model file stored inside its own submission directory.
- Do not modify the provided rules engine, harness package, or opponent files.
- A crash, timeout, malformed response, or response not in `legal_actions`
  forfeits the game.

## Running games from the command line

`src/santorini.py` is the local command-line runner:

```console
python src/santorini.py \
  --bot1 bot_a.py \
  --bot2 bot_b.py \
  --seed 2026 \
  --time-limit 2.0 \
  --num-games 5
```

`--num-games` runs sequential games seeded from `--seed + game_index`.
The game always allows 200 turns. A template bot lives at
`src/student_bot_template.py`.

## Programmatic harness API

`santorini_game_engine` is the public entry point:

```python
from santorini_game_engine import MatchConfig, run_santorini_game

result = run_santorini_game(bot_a, bot_b)                      # one game
results = run_santorini_game(bot_a, bot_b, num_games=5)        # five games
config = MatchConfig(move_time_limit_seconds=2.0, max_turns=200, seed=2026)
results = run_santorini_game(bot_a, bot_b, config=config)      # explicit config
```

`run_santorini_game` returns one `GameResult` per game, in the order they
were played. Each `GameResult` carries `winner`, `loser`, `reason`
(a `TerminationReason`), `turns_played`, the recorded `moves`, and a `detail`
string for timeout/exception/invalid-action messages. The winner is `None`
only for turn-limit and repetition draws. `BotSpec` in the same module
describes a bot selection (file path, display name, entry point) for match
scheduling.

For a fair paired match, run a second game with the bot order swapped using
the same seed. The trusted rules engine (`SantoriniEngine` in
`santorini_engine.py`) preserves the canonical game state internally and
transforms it into `GameState` so that each called bot always sees itself as
`current_workers`.

## Harness responsibilities

The harness, not the student bot, is responsible for:

1. Creating the starting state and the complete legal-action list.
2. Enforcing the per-move time limit.
3. Validating the returned action against the supplied legal-action tuple.
4. Applying the action, detecting wins, no-legal-move losses, repetition, and
   enforcing the maximum game length.
5. Recording the seed, actions, and final outcome in the returned results.

`run_game_for_testing` in `tests/test_helpers.py` is a local development
helper that drives one in-process game against a given engine and two bot
functions. The official tournament runner should additionally use process
isolation because an in-process Python call cannot safely terminate a bot
that hangs.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/data_structures.py` | `Coordinate`, `Action`, `GameState` (public API types). |
| `src/santorini_engine.py` | `SantoriniEngine`: setup, legal actions, apply, termination. |
| `src/santorini_game_engine.py` | `MatchConfig`, `TerminationReason`, `GameResult`, `run_santorini_game`. |
| `src/santorini.py` | Command-line runner. |
| `src/student_bot_template.py` | Minimal example bot. |
| `tests/` | Engine unit tests, harness integration tests, and `test_helpers.py`. |
