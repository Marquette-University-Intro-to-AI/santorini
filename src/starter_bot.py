"""Copy this file to your submission directory and implement choose_action. To get the successor states, use the successors function from santorini_engine.py. You can also use the GameState class from santorini_types.py to
represent the game state in your bot. The starter bot is intentionally weak; you should replace it with your own
search or learned policy."""

from santorini_engine import successors
from santorini_types import Action, GameState


def choose_action(
    state: GameState,
    legal_actions: tuple[Action, ...],
    time_limit_seconds: float,
) -> Action:
    """Return exactly one member of legal_actions before the deadline.

    State and legal_actions are read-only.  This starter bot is legal but
    intentionally weak: replace it with your own search or learned policy.
    """

    return legal_actions[0]
