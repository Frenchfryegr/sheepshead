"""Reracks: a hand with no trump and no ace forces a redeal.

Invisible to the player by design — the round never begins, so there is nothing to show and
nothing to score. The engine simply deals again before anyone sees anything.
"""

import unittest

from .cards import Card, build_deck, is_trump
from .engine import _deal_hand, create_game, is_rerack_hand
from .rules import RuleSet
from .serialization import full_state_from_dict, full_state_to_dict
from .state import Seat

RULES = RuleSet()
NO_RERACK = RuleSet(rerack_enabled=False)


def _seats() -> list[Seat]:
    return [Seat(index, f"Seat {index}", index == 0, None if index == 0 else "random") for index in range(5)]


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


class PredicateTests(unittest.TestCase):
    def test_no_trump_and_no_ace_is_a_rerack(self) -> None:
        self.assertTrue(is_rerack_hand(_cards("7C", "8C", "9C", "KC", "TC", "7S"), RULES))

    def test_a_ten_is_not_enough_to_save_a_hand(self) -> None:
        # Tens carry points but cannot beat an ace of their own suit, so they do not count.
        self.assertTrue(is_rerack_hand(_cards("TC", "TS", "TH", "9C", "8S", "7H"), RULES))

    def test_any_trump_saves_the_hand(self) -> None:
        for trump in ("7D", "QC", "JD", "AD"):
            with self.subTest(trump=trump):
                self.assertFalse(is_rerack_hand(_cards(trump, "7C", "8C", "9C", "KC", "TC"), RULES))

    def test_any_fail_ace_saves_the_hand(self) -> None:
        for ace in ("AC", "AS", "AH"):
            with self.subTest(ace=ace):
                self.assertFalse(is_rerack_hand(_cards(ace, "7C", "8C", "9C", "KC", "7S"), RULES))

    def test_the_ace_of_diamonds_needs_no_special_case(self) -> None:
        # It is trump, so a hand holding it is already saved by the trump test — which is why
        # the predicate can look only at fail aces without naming them.
        ace_of_diamonds = Card.parse("AD")
        self.assertTrue(is_trump(ace_of_diamonds, RULES))

    def test_an_empty_hand_counts_as_a_rerack(self) -> None:
        # Degenerate, but the predicate should not claim an empty hand can take a trick.
        self.assertTrue(is_rerack_hand([], RULES))


class DealTests(unittest.TestCase):
    def test_no_deal_ever_produces_a_rerack_hand(self) -> None:
        for seed in range(300):
            state = create_game(RULES, _seats(), seed)
            for index, hand in enumerate(state.hand.hands):
                self.assertFalse(
                    is_rerack_hand(hand, RULES),
                    f"seed {seed} dealt seat {index} a rerack hand",
                )

    def test_reracks_are_reachable_without_the_rule(self) -> None:
        # Guards the test above from passing vacuously: if reracks never occurred at all, the
        # redeal loop could be broken and nothing would notice.
        found = sum(
            any(is_rerack_hand(hand, NO_RERACK) for hand in create_game(NO_RERACK, _seats(), seed).hand.hands)
            for seed in range(300)
        )
        self.assertGreater(found, 0, "no rerack occurred in 300 raw deals")

    def test_a_reracked_seed_yields_a_different_deal(self) -> None:
        for seed in range(300):
            raw = create_game(NO_RERACK, _seats(), seed)
            if not any(is_rerack_hand(hand, NO_RERACK) for hand in raw.hand.hands):
                continue
            fixed = create_game(RULES, _seats(), seed)
            self.assertNotEqual(raw.hand.hands, fixed.hand.hands)
            self.assertFalse(any(is_rerack_hand(hand, RULES) for hand in fixed.hand.hands))
            return
        self.fail("no rerack deal found in the sample")

    def test_a_clean_seed_is_dealt_identically_either_way(self) -> None:
        # The first attempt reuses the original seed, so hands that never needed a redeal are
        # untouched by this rule.
        clean = 0
        for seed in range(60):
            raw = create_game(NO_RERACK, _seats(), seed)
            if any(is_rerack_hand(hand, NO_RERACK) for hand in raw.hand.hands):
                continue
            clean += 1
            self.assertEqual(raw.hand.hands, create_game(RULES, _seats(), seed).hand.hands)
        self.assertGreater(clean, 0)

    def test_every_deal_still_uses_the_whole_deck(self) -> None:
        for seed in range(60):
            hand = create_game(RULES, _seats(), seed).hand
            dealt = [card for cards in hand.hands for card in cards] + hand.blind
            self.assertEqual(len(build_deck(RULES)), len(dealt))
            self.assertEqual(len(dealt), len(set(dealt)), "a redeal duplicated a card")

    def test_later_hands_are_reracked_too(self) -> None:
        # The rule lives in _deal_hand rather than in create_game, so it covers every hand of a
        # session and not just the opening one.
        state = create_game(RULES, _seats(), 4242)
        for hand_number in range(2, 60):
            dealt = _deal_hand(state, dealer_seat=hand_number % 5, hand_number=hand_number)
            for index, cards in enumerate(dealt.hands):
                self.assertFalse(
                    is_rerack_hand(cards, RULES),
                    f"hand {hand_number} dealt seat {index} a rerack hand",
                )


class RulesetTests(unittest.TestCase):
    def test_the_flag_round_trips_and_defaults_on(self) -> None:
        self.assertTrue(RuleSet().rerack_enabled)
        self.assertEqual(RULES, RuleSet.from_dict(RULES.to_dict()))

    def test_snapshots_predating_the_flag_still_decode(self) -> None:
        legacy = RULES.to_dict()
        del legacy["rerack_enabled"]
        self.assertEqual(RULES, RuleSet.from_dict(legacy))

    def test_state_round_trip_keeps_the_flag(self) -> None:
        state = create_game(RULES, _seats(), 7)
        encoded = full_state_to_dict(state)
        self.assertTrue(encoded["ruleset"]["rerack_enabled"])
        self.assertEqual(encoded, full_state_to_dict(full_state_from_dict(encoded)))


if __name__ == "__main__":
    unittest.main()
