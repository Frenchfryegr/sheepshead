"""Playstyle presets.

These are personality, not difficulty, so the tests are mostly *invariants* rather than expected
values: every preset has to stay inside the bands that make the shared logic work, and has to
actually differ from the others. What a given constant is set to is a tuning decision; that it
stays in range is not.
"""

import random
import unittest

from .ai import AI_STRATEGIES
from .ai_evaluate import offensive_strength
from .ai_heuristic import (
    OPPONENT_UNKNOWN_ALLY,
    PICKER_UNKNOWN_ALLY,
    HeuristicStrategy,
    pick_threshold,
)
from .ai_style import BALANCED, PLAYSTYLE_KEYS, STYLES, PlayStyle
from .cards import Card
from .engine import apply_action, create_game, legal_actions
from .rules import RuleSet
from .serialization import seat_view
from .state import Seat

RULES = RuleSet()

SIX_LOWEST_TRUMP = ("AD", "TD", "KD", "9D", "8D", "7D")
THREE_HIGH_QUEENS = ("QC", "QS", "QH", "8C", "7S", "9H")


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _all_styles() -> list[PlayStyle]:
    return [BALANCED, *STYLES.values()]


class StyleInvariantTests(unittest.TestCase):
    def test_every_pick_bar_stays_inside_the_calibration_anchors(self) -> None:
        # Outside this band a style would pick on six low diamonds or pass on three queens,
        # breaking the user's anchors at some seat.
        weak = offensive_strength(_cards(*SIX_LOWEST_TRUMP), RULES)
        strong = offensive_strength(_cards(*THREE_HIGH_QUEENS), RULES)
        for style in _all_styles():
            for position in range(5):
                bar = pick_threshold(
                    position,
                    5,
                    first=style.first_seat_pick_bar,
                    last=style.last_seat_pick_bar,
                )
                self.assertGreater(bar, weak, f"{style.name} picks six low trump at {position}")
                self.assertLessEqual(
                    bar, strong, f"{style.name} passes three queens at {position}"
                )

    def test_every_bar_falls_from_the_first_seat_to_the_last(self) -> None:
        for style in _all_styles():
            self.assertGreater(
                style.first_seat_pick_bar,
                style.last_seat_pick_bar,
                f"{style.name} is fussier late than early",
            )

    def test_ally_threshold_sits_between_the_unknown_base_rates(self) -> None:
        # Below the picker's rate it would start feeding unknown seats; above an opponent's, the
        # three opponents would stop helping each other. Either collapses the role-aware logic.
        for style in _all_styles():
            self.assertGreater(style.ally_threshold, PICKER_UNKNOWN_ALLY, style.name)
            self.assertLess(style.ally_threshold, OPPONENT_UNKNOWN_ALLY, style.name)

    def test_going_alone_always_needs_more_than_picking(self) -> None:
        for style in _all_styles():
            self.assertGreater(style.alone_bar, style.first_seat_pick_bar, style.name)

    def test_presets_are_actually_distinct(self) -> None:
        # A roster of near-identical styles is worse than no roster: it implies variety that
        # is not there.
        seen = {style.name: style for style in STYLES.values()}
        self.assertEqual(4, len(seen))
        for key in ("first_seat_pick_bar", "alone_bar", "bury_point_weight", "cheap_trump_cost"):
            values = {getattr(style, key) for style in STYLES.values()}
            self.assertEqual(4, len(values), f"{key} is shared between presets")


class RegistryTests(unittest.TestCase):
    def test_every_style_is_registered_and_constructible(self) -> None:
        for key in PLAYSTYLE_KEYS:
            self.assertIn(key, AI_STRATEGIES)
            strategy = AI_STRATEGIES[key]()
            self.assertIsInstance(strategy, HeuristicStrategy)
            self.assertEqual(STYLES[key], strategy.style)

    def test_the_baseline_entries_survive(self) -> None:
        # RandomStrategy is the legality fuzzer simulate.py depends on; "heuristic" is the
        # balanced baseline every constant was calibrated against.
        self.assertIn("random", AI_STRATEGIES)
        self.assertEqual(BALANCED, AI_STRATEGIES["heuristic"]().style)


class StyleBehaviourTests(unittest.TestCase):
    def _picks(self, style_key: str, hand: tuple[str, ...], passes: int) -> bool:
        state = create_game(RULES, [Seat(i, f"S{i}", False, style_key) for i in range(5)], 77)
        state.hand.hands[0] = _cards(*hand)
        state.hand.passes = list(range(1, passes + 1))
        state.hand.turn_seat = 0
        action = AI_STRATEGIES[style_key]().choose(
            seat_view(state, 0), legal_actions(state, 0), random.Random(1)
        )
        return action.type == "pick"

    def test_the_gambler_picks_hands_the_cautious_style_declines(self) -> None:
        # The clearest visible difference between presets: who takes the blind.
        marginal = [
            ("QS", "JC", "AD", "9D", "AH", "8H"),
            ("QH", "JS", "AD", "TD", "AC", "7C"),
            ("JC", "JS", "AD", "TD", "AC", "8C"),
            ("QD", "JD", "JH", "KD", "9S", "7H"),
            ("QS", "JD", "TD", "9D", "7S", "8S"),
        ]
        divergent = [
            hand
            for hand in marginal
            if self._picks("gambler", hand, 0) and not self._picks("cautious", hand, 0)
        ]
        self.assertTrue(divergent, "no hand in the sample separated Gambler from Cautious")

    def test_all_styles_play_full_games_legally(self) -> None:
        for key in PLAYSTYLE_KEYS:
            seats = [Seat(index, f"S{index}", False, key) for index in range(5)]
            state = create_game(RULES, seats, 31337)
            strategy = AI_STRATEGIES[key]()
            rng = random.Random(6)
            for _ in range(300):
                turn = state.hand.turn_seat
                legal = legal_actions(state, turn)
                self.assertTrue(legal, key)
                action = strategy.choose(seat_view(state, turn), legal, rng)
                self.assertIn(action, legal, key)
                state, _ = apply_action(state, turn, action)


class SeatViewTests(unittest.TestCase):
    def test_the_playstyle_is_public(self) -> None:
        seats = [
            Seat(0, "You", True, None),
            *[Seat(index, f"AI {index}", False, "gambler") for index in range(1, 5)],
        ]
        view = seat_view(create_game(RULES, seats, 5), 0)
        self.assertIsNone(view["seats"][0]["ai_strategy"])
        self.assertEqual("gambler", view["seats"][1]["ai_strategy"])


if __name__ == "__main__":
    unittest.main()
