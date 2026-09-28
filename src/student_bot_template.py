"""Copy this file to your submission directory and implement choose_action."""

from data_structures import Action, GameState


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
