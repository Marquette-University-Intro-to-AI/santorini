# Santorini course tournament

This package contains the trusted Santorini rules engine and the public API
your bot uses to play. You write a single `choose_action` function; the
engine and harness handle everything else. Internal details of the harness
and repository are in [INTERNAL.md](INTERNAL.md).

## The bot interface: `choose_action`

Every submission contains a Python file, normally `bot.py`, with exactly this
top-level function:

```python
from santorini_types import Action, GameState


def choose_action(
    state: GameState,
    legal_actions: tuple[Action, ...],
    time_limit_seconds: float,
) -> Action: ...
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

## Exploring successor positions: `successors`

To reason about what each move leads to — for example, when building a
search tree — use the `successors` function from `santorini_engine`:

```python
from santorini_engine import successors

pairs = successors(board_state)  # tuple of (action, next_state) pairs
```

It returns one `(action, next_state)` pair per legal complete turn, where
`next_state` is the immutable board resulting from applying `action`.
Terminal positions yield an empty tuple. `successors` operates on the
canonical `BoardState` (the engine's internal representation), so if you
keep your own `BoardState` while searching, pass it straight in.

`santorini_engine` also exposes the other pure rules functions — `setup`,
`legal_actions_from`, `apply_action`, `fingerprint`, `public_state_for`,
and `termination_reason` — plus the stateful `SantoriniEngine` wrapper.
These are part of the trusted engine you may import and read, but never
modify. The `GameState` and `Action` types from `santorini_types` are the
public data structures your bot exchanges with the harness.

## Programmatic harness API

`santorini_harness` is the public entry point:

```python
from santorini_harness import MatchConfig, run_santorini_tournament

result = run_santorini_tournament(bot_a, bot_b)  # one game
results = run_santorini_tournament(bot_a, bot_b, num_games=5)  # five games
config = MatchConfig(move_time_limit_seconds=2.0, max_turns=200, seed=2026)
results = run_santorini_tournament(bot_a, bot_b, config=config)  # explicit config
```

`run_santorini_tournament` returns one `GameResult` per game, in the order they
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

## Running games from the command line

`src/run_santorini.py` is the local game runner:

```console
python src/run_santorini.py \
  --bot1 bot_a.py \
  --bot2 bot_b.py \
  --seed 2026 \
  --time-limit 2.0 \
  --num-games 5
```

`--num-games` runs sequential games seeded from `--seed + game_index`.
The game always allows 200 turns. A template bot lives at
`src/starter_bot.py`.

## Requirements and restrictions

- Treat `state` and `legal_actions` as read-only.
- Do not use the network, subprocesses, interprocess communication, or files
  outside the submitted bot directory.
- Do not depend on wall-clock time except to finish before the deadline.
- A bot may load a model file stored inside its own submission directory.
- Do not modify the provided rules engine, harness package, or opponent files.
- A crash, timeout, malformed response, or response not in `legal_actions`
  forfeits the game.
