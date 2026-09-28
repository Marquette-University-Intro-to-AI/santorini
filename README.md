# Santorini tournament harness API

## Student bot interface

Every submission contains a Python file, normally `bot.py`, with exactly this
top-level function:

```python
from santorini_harness_api import Action, GameState

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

## Harness API

The harness identifies each competitor using a `BotSpec`:

```python
from santorini_harness_api import BotSpec, MatchConfig

bot_a = BotSpec(file_path="submissions/blue/bot.py", display_name="Blue")
bot_b = BotSpec(file_path="submissions/gold/bot.py", display_name="Gold")
config = MatchConfig(move_time_limit_seconds=2.0, max_turns=200, seed=2026)
```

The production command-line runner should accept the same information:

```console
python -m santorini_harness match \
  --bot-a submissions/blue/bot.py \
  --bot-b submissions/gold/bot.py \
  --seed 2026 \
  --time-limit 2.0 \
  --max-turns 200
```

For a fair paired match, run a second game with the bot order swapped using the
same seed. The trusted rules engine should preserve the canonical game state
internally and transform it into `GameState` so that each called bot always
sees itself as `current_workers`.

## Harness responsibilities

The official harness, not the student bot, is responsible for:

1. Creating the starting state and the complete legal-action list.
2. Loading each bot in a fresh isolated worker process.
3. Enforcing the per-move time and memory limits.
4. Validating the returned action against the supplied legal-action tuple.
5. Applying the action, detecting wins and no-legal-move losses, and enforcing
   the maximum game length.
6. Recording the seed, actions, elapsed time, errors, and final outcome in a
   machine-readable match log.

`run_game_for_testing` in `santorini_harness_api.py` is a local development
helper. The official tournament runner should use process isolation because an
in-process Python call cannot safely terminate a bot that hangs.
