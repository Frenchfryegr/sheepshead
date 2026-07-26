"""Pure-Python, server-authoritative Sheepshead engine."""

from .engine import IllegalActionError, apply_action, create_game, legal_actions
from .rules import RULESET_PRESETS, RuleSet

__all__ = [
    "IllegalActionError",
    "RULESET_PRESETS",
    "RuleSet",
    "apply_action",
    "create_game",
    "legal_actions",
]
