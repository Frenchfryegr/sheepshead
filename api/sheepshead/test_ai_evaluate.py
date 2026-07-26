"""Hand evaluation tests.

The valuable ones are the calibration anchors (`PickingAnchorTests`) and the monotonicity
properties. Both assert *orderings* rather than values, so the weights stay tunable without
rewriting the suite — which is the point, since the weights are guesses and the orderings are not.
"""

import itertools
import unittest

from .ai_evaluate import (
    TRUMP_WEIGHTS,
    callable_suits,
    leaster_strength,
    offensive_strength,
    shape,
)
from .cards import Card, Rank, build_deck, is_trump, trump_power
from .rules import RuleSet

RULES = RuleSet()


def _hand(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _off(*values: str) -> float:
    return offensive_strength(_hand(*values), RULES)


def _leaster(*values: str) -> float:
    return leaster_strength(_hand(*values), RULES)


class ShapeTests(unittest.TestCase):
    def test_trump_never_counts_as_its_printed_suit(self) -> None:
        # QH and JH are trump, not hearts; AD is trump, not a fail diamond.
        result = shape(_hand("QH", "JH", "AD", "7H", "8S", "AC"), RULES)
        self.assertEqual(3, result.trump_count)
        self.assertEqual((Card.parse("7H"),), result.fail_by_suit["H"])
        self.assertNotIn("D", result.fail_by_suit)

    def test_voids_and_singletons_cover_fail_suits_only(self) -> None:
        result = shape(_hand("QC", "QS", "AD", "TD", "7H", "AC"), RULES)
        self.assertEqual(frozenset({"S"}), result.void_suits)
        self.assertEqual(frozenset({"H", "C"}), result.singleton_suits)

    def test_fail_suits_are_ordered_high_to_low(self) -> None:
        result = shape(_hand("7C", "AC", "9C", "TC"), RULES)
        self.assertEqual(_hand("AC", "TC", "9C", "7C"), list(result.fail_by_suit["C"]))

    def test_points_counts_every_card(self) -> None:
        self.assertEqual(11 + 10 + 4 + 3 + 2, shape(_hand("AC", "TS", "KH", "QD", "JD"), RULES).points)


class PickingAnchorTests(unittest.TestCase):
    """The user's calibration anchors. These outrank any individual weight."""

    # All six diamonds and no queen or jack — six trump, but the six *lowest*.
    SIX_LOWEST_TRUMP = ("AD", "TD", "KD", "9D", "8D", "7D")
    # Three trump, but the three best cards in the deck.
    THREE_HIGH_QUEENS = ("QC", "QS", "QH", "8C", "7S", "9H")

    def test_six_lowest_trump_is_weaker_than_three_high_queens(self) -> None:
        # The anchor that constrains the whole weight table: "6 trump, almost always pick —
        # unless it is the six lowest", against "<=3 trump, almost never — unless very strong".
        # Quantity of weak trump must never outrun quality.
        self.assertLess(_off(*self.SIX_LOWEST_TRUMP), _off(*self.THREE_HIGH_QUEENS))

    def test_the_pick_bar_has_somewhere_to_sit(self) -> None:
        # Phase 6's first-seat threshold must fall strictly between these two. Assert the gap is
        # real and not a rounding artefact, so there is room to place a bar between them.
        gap = _off(*self.THREE_HIGH_QUEENS) - _off(*self.SIX_LOWEST_TRUMP)
        self.assertGreater(gap, 1.0)

    def test_six_trump_with_a_queen_beats_six_lowest_trump(self) -> None:
        # "6 trump -> almost always pick" holds once even one real trump is present.
        self.assertLess(_off(*self.SIX_LOWEST_TRUMP), _off("QC", "AD", "TD", "KD", "9D", "8D"))

    def test_four_strong_trump_beats_six_lowest_trump(self) -> None:
        # "4-5 trump, mostly queens/jacks -> pick".
        self.assertLess(_off(*self.SIX_LOWEST_TRUMP), _off("QS", "JC", "JD", "AD", "AH", "8H"))

    def test_three_weak_trump_is_the_worst_of_them(self) -> None:
        # "<=3 trump -> almost never pick", when the trump are not the exception.
        weak = _off("AD", "TD", "KD", "8C", "7S", "9H")
        self.assertLess(weak, _off(*self.SIX_LOWEST_TRUMP))
        self.assertLess(weak, _off(*self.THREE_HIGH_QUEENS))

    def test_a_void_beats_holding_all_three_fail_suits(self) -> None:
        # "It is best for your only fail to be your called suit" — the same trump, arranged
        # with a void, must beat the same trump spread across every fail suit.
        void = _off("QC", "JS", "AD", "9D", "8C", "7C")
        spread = _off("QC", "JS", "AD", "9D", "8C", "7S")
        self.assertGreater(void, spread)


class MonotonicityTests(unittest.TestCase):
    """Properties that catch weight-table typos inspection will not."""

    def test_upgrading_any_trump_never_weakens_a_hand(self) -> None:
        base = _hand("AD", "8C", "7S", "9H")
        trump = sorted(
            (card for card in build_deck(RULES) if is_trump(card, RULES)),
            key=lambda card: trump_power(card, RULES),
        )
        for lower, higher in itertools.pairwise(trump):
            with self.subTest(lower=str(lower), higher=str(higher)):
                self.assertLessEqual(
                    offensive_strength(base + [lower], RULES),
                    offensive_strength(base + [higher], RULES),
                )

    def test_trump_weights_are_strictly_increasing(self) -> None:
        for lower, higher in itertools.pairwise(TRUMP_WEIGHTS):
            self.assertLess(lower, higher)

    def test_weight_table_covers_every_trump(self) -> None:
        trump = [card for card in build_deck(RULES) if is_trump(card, RULES)]
        self.assertEqual(len(trump), len(TRUMP_WEIGHTS))


class LeasterTests(unittest.TestCase):
    def test_a_low_lowest_card_beats_a_high_one(self) -> None:
        # The dominant signal: you follow with your lowest card, so a lowest of 7 ducks and a
        # lowest of ace does not. Same suit lengths, same trump.
        self.assertGreater(
            _leaster("7C", "8C", "7S", "8S", "9H", "9D"),
            _leaster("AC", "TC", "AS", "TS", "AH", "9D"),
        )

    def test_a_singleton_low_card_is_fine_but_a_singleton_ace_is_not(self) -> None:
        # Shortness itself is not the problem — the card is. A void is merely neutral.
        self.assertGreater(
            _leaster("7C", "8S", "9S", "7H", "8H", "9D"),
            _leaster("AC", "8S", "9S", "7H", "8H", "9D"),
        )

    def test_a_hand_that_cannot_win_a_trick_is_penalised(self) -> None:
        # Taking zero tricks means ineligibility, so pure junk with no trump is not the ideal.
        no_trump = _leaster("7C", "8C", "9C", "7S", "8S", "9S")
        with_moderate = _leaster("7C", "8C", "9C", "7S", "8S", "AD")
        self.assertGreater(with_moderate, no_trump)

    def test_one_high_trump_is_good_and_four_queens_are_not(self) -> None:
        # One reliable winner is what eligibility needs; every extra wins tricks you did not want.
        one_queen = _leaster("QC", "7C", "8C", "7S", "8S", "9H")
        all_queens = _leaster("QC", "QS", "QH", "QD", "7S", "8S")
        self.assertGreater(one_queen, all_queens)

    def test_leaster_and_offence_disagree(self) -> None:
        # The two evaluations must not be reskins of each other: the best picking hand here
        # should be among the worst leaster hands.
        strong = _hand("QC", "QS", "JC", "AD", "AH", "AC")
        junk = _hand("7C", "8C", "9C", "7S", "8S", "9D")
        self.assertGreater(offensive_strength(strong, RULES), offensive_strength(junk, RULES))
        self.assertGreater(leaster_strength(junk, RULES), leaster_strength(strong, RULES))


class CallableSuitsTests(unittest.TestCase):
    def test_holding_the_ace_excludes_its_suit(self) -> None:
        self.assertNotIn("C", callable_suits(_hand("AC", "8C", "7S", "QD"), RULES))

    def test_holding_only_the_ace_excludes_its_suit(self) -> None:
        self.assertNotIn("C", callable_suits(_hand("AC", "7S", "8S", "QD"), RULES))

    def test_a_non_ace_fail_card_without_the_ace_qualifies(self) -> None:
        self.assertIn("S", callable_suits(_hand("AC", "8C", "7S", "QD"), RULES))

    def test_a_void_suit_does_not_qualify(self) -> None:
        # No fail card of the suit means no ordinary call; unders are a Phase 5 concern.
        self.assertEqual(frozenset({"C"}), callable_suits(_hand("8C", "7C", "QD", "JD"), RULES))

    def test_all_fail_cards_being_aces_leaves_nothing_callable(self) -> None:
        # The case real rules answer with an under, and the engine currently answers with
        # "play alone". See AI_IMPLEMENTATION.md Phase 5.
        self.assertEqual(frozenset(), callable_suits(_hand("AC", "AS", "AH", "QD"), RULES))

    def test_never_returns_a_suit_whose_ace_is_held(self) -> None:
        deck = build_deck(RULES)
        for start in range(0, len(deck) - 6, 3):
            cards = deck[start : start + 6]
            for suit in callable_suits(cards, RULES):
                held = {card for card in cards if card.rank is Rank.ACE}
                self.assertNotIn(Card.parse(f"A{suit}"), held)


if __name__ == "__main__":
    unittest.main()
