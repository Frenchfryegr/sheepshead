import random
from collections.abc import Callable
from typing import Protocol

from functools import partial

from .ai_heuristic import HeuristicStrategy
from .ai_style import STYLES
from .state import Action


class AIStrategy(Protocol):
    def choose(self, view: dict, legal: list[Action], rng: random.Random) -> Action: ...


class RandomStrategy:
    """Uniform over legal actions.

    Kept permanently, not superseded: `simulate.py` leans on it to prove `legal_actions()` never
    returns empty across the whole state space, and a heuristic AI explores far fewer branches.
    """

    def choose(self, view: dict, legal: list[Action], rng: random.Random) -> Action:
        del view
        if not legal:
            raise ValueError("AI was asked to choose with no legal actions")
        return rng.choice(legal)


# Zero-argument callables, so a playstyle-parameterised strategy can be registered later as
# `partial(HeuristicStrategy, style=...)` without touching the call site in _drive_online_ai.
AI_STRATEGIES: dict[str, Callable[[], AIStrategy]] = {
    "random": RandomStrategy,
    "heuristic": HeuristicStrategy,  # the balanced baseline
    **{key: partial(HeuristicStrategy, style=style) for key, style in STYLES.items()},
}
DEFAULT_AI = "random"
