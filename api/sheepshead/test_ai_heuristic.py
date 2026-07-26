"""Bidding AI tests.

The behavioural assertions are anchored to the user's calibration guidance, so they stay valid
while the constants are tuned. Absolute pick rates are the soak's job, not this suite's.
"""

import random
import unittest

from .ai_heuristic import (
    ALONE_BAR,
    FIRST_SEAT_PICK_BAR,
    LAST_SEAT_PICK_BAR,
    HeuristicStrategy,
    call_quality,
    pick_threshold,
)
from .ai_evaluate import callable_suits, offensive_strength
from .cards import Card, Rank, build_deck, is_trump
from .engine import apply_action, create_game, legal_actions
from .rules import RuleSet
from .serialization import seat_view
from .state import CallUnderAction, Phase, Seat

RULES = RuleSet()

SIX_LOWEST_TRUMP = ("AD", "TD", "KD", "9D", "8D", "7D")
THREE_HIGH_QUEENS = ("QC", "QS", "QH", "8C", "7S", "9H")


def _seats(strategy: str = "heuristic") -> list[Seat]:
    return [Seat(index, f"Seat {index}", False, strategy) for index in range(5)]


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _picking_state(hand: tuple[str, ...], *, passes: int = 0):
    state = create_game(RULES, _seats(), 4242)
    state.hand.hands[0] = _cards(*hand)
    state.hand.phase = Phase.PICKING
    state.hand.passes = list(range(1, passes + 1))
    state.hand.turn_seat = 0
    return state


def _decide(state, seat: int = 0):
    view = seat_view(state, seat)
    legal = legal_actions(state, seat)
    return HeuristicStrategy().choose(view, legal, random.Random(7)).type


class ThresholdTests(unittest.TestCase):
    def test_the_bar_falls_from_the_first_seat_to_the_last(self) -> None:
        bars = [pick_threshold(position, 5) for position in range(5)]
        self.assertEqual(FIRST_SEAT_PICK_BAR, bars[0])
        self.assertEqual(LAST_SEAT_PICK_BAR, bars[-1])
        for earlier, later in zip(bars, bars[1:]):
            self.assertGreater(earlier, later)

    def test_every_bar_sits_between_the_calibration_anchors(self) -> None:
        # Six lowest trump must never pick; three high queens must always pick. Both bars have
        # to live in that gap or the anchors are violated at some seat.
        weak = offensive_strength(_cards(*SIX_LOWEST_TRUMP), RULES)
        strong = offensive_strength(_cards(*THREE_HIGH_QUEENS), RULES)
        for position in range(5):
            bar = pick_threshold(position, 5)
            self.assertGreater(bar, weak, f"six lowest trump would pick at seat {position}")
            self.assertLessEqual(bar, strong, f"three high queens would pass at seat {position}")

    def test_the_bar_does_not_hardcode_five_seats(self) -> None:
        for players in (3, 4, 5):
            self.assertEqual(FIRST_SEAT_PICK_BAR, pick_threshold(0, players))
            self.assertEqual(LAST_SEAT_PICK_BAR, pick_threshold(players - 1, players))

    def test_alone_needs_more_than_picking_does(self) -> None:
        self.assertGreater(ALONE_BAR, FIRST_SEAT_PICK_BAR)


class PickingTests(unittest.TestCase):
    def test_six_lowest_trump_never_picks_from_any_seat(self) -> None:
        for passes in range(5):
            state = _picking_state(SIX_LOWEST_TRUMP, passes=passes)
            self.assertEqual("pass", _decide(state), f"picked at position {passes}")

    def test_three_high_queens_picks_from_every_seat(self) -> None:
        for passes in range(5):
            state = _picking_state(THREE_HIGH_QUEENS, passes=passes)
            self.assertEqual("pick", _decide(state), f"passed at position {passes}")

    def test_position_can_flip_a_marginal_hand(self) -> None:
        # The whole point of a position-dependent bar: a hand a first seat declines, a later
        # seat takes. Search for one rather than asserting a hand-picked constant survives
        # tuning.
        candidates = [
            ("QS", "JC", "AD", "9D", "AH", "8H"),
            ("QH", "JS", "AD", "TD", "AC", "7C"),
            ("QD", "JD", "JH", "KD", "9S", "7H"),
            ("JC", "JS", "AD", "TD", "AC", "8C"),
            ("QS", "JD", "TD", "9D", "7S", "8S"),
        ]
        flipped = []
        for hand in candidates:
            first = _decide(_picking_state(hand, passes=0))
            last = _decide(_picking_state(hand, passes=4))
            if first == "pass" and last == "pick":
                flipped.append(hand)
            # A later seat must never be *fussier* than an earlier one.
            self.assertFalse(first == "pick" and last == "pass", hand)
        self.assertTrue(flipped, "no hand in the sample was position-sensitive")

    def test_a_poor_leaster_hand_lowers_the_last_seats_bar(self) -> None:
        # Aces and tens make a dreadful leaster hand, so the last seat should be readier to
        # pick with one than its raw offensive strength alone would justify.
        hand = ("QS", "JD", "AC", "TC", "AS", "TS")
        state = _picking_state(hand, passes=4)
        relaxed = pick_threshold(4, 5)
        strength = offensive_strength(_cards(*hand), RULES)
        if strength < relaxed:
            # Only meaningful when the relief is what tips it over.
            self.assertEqual("pick", _decide(state))


class BuryAndCallTests(unittest.TestCase):
    def _burying_state(self, hand: tuple[str, ...]):
        # Burying always happens with cards_per_player + blind_size cards: the blind has been
        # taken and nothing discarded yet. A shorter hand is an unreachable state and gives
        # misleading answers, since it can make voiding every fail suit look forced.
        expected = RULES.cards_per_player + RULES.blind_size
        self.assertEqual(expected, len(hand), "a bury is chosen from a full post-blind hand")
        state = create_game(RULES, _seats(), 111)
        state.hand.hands[0] = _cards(*hand)
        state.hand.blind = []
        state.hand.phase = Phase.BURYING
        state.hand.picker_seat = 0
        state.hand.turn_seat = 0
        return state

    def _chosen_bury(self, hand: tuple[str, ...]) -> set[Card]:
        state = self._burying_state(hand)
        action = HeuristicStrategy().choose(
            seat_view(state, 0), legal_actions(state, 0), random.Random(3)
        )
        self.assertEqual("bury", action.type)
        return set(action.cards)

    def test_trump_is_kept_when_spare_fail_cards_exist(self) -> None:
        # Four trump and four fail: there is no reason to touch the trump, and none is needed
        # to preserve a call. offensive_strength collapses when trump leaves, so this needs no
        # explicit rule — it falls out of the evaluation.
        buried = self._chosen_bury(("QC", "QS", "JD", "AD", "7C", "8C", "9S", "7H"))
        for card in buried:
            self.assertFalse(is_trump(card, RULES), f"buried trump: {card}")

    def test_burying_keeps_a_callable_suit_rather_than_forcing_an_under(self) -> None:
        # Six trump and two clubs. Burying both clubs leaves no fail at all, which forces an
        # under and wastes a card in a trick; keeping one club preserves an ordinary call.
        hand = ("QC", "QS", "JD", "AD", "TD", "9D", "7C", "8C")
        buried = self._chosen_bury(hand)
        remaining = [card for card in _cards(*hand) if card not in buried]
        self.assertTrue(
            callable_suits(remaining, RULES),
            "buried into an under when an ordinary call was reachable",
        )

    def test_a_forced_trump_bury_takes_the_points(self) -> None:
        # All trump, so two trump must go. Buried points are banked for the picker's team, so
        # spend the point-carriers (A/T of diamonds) rather than the worthless 7/8/9.
        buried = self._chosen_bury(("QC", "QS", "JC", "JD", "AD", "TD", "9D", "8D"))
        self.assertEqual(set(_cards("AD", "TD")), buried)

    def test_a_forced_trump_bury_still_protects_the_only_fail_card(self) -> None:
        # Seven trump and one club: the club is the difference between an ordinary call and an
        # under, so it survives, and the trump spent are again the point-carrying ones.
        buried = self._chosen_bury(("QC", "QS", "JC", "JD", "AD", "TD", "9D", "7C"))
        self.assertNotIn(Card.parse("7C"), buried)
        self.assertEqual(set(_cards("AD", "TD")), buried)

    def test_a_queen_is_never_buried(self) -> None:
        # An absolute rule, not a weight — no score may outvote it.
        deck = build_deck(RULES)
        for start in range(0, len(deck) - 8, 3):
            hand = tuple(str(card) for card in deck[start : start + 8])
            for card in self._chosen_bury(hand):
                self.assertIsNot(Rank.QUEEN, card.rank, f"buried {card} from {hand}")

    def test_jacks_are_spared_while_anything_else_remains(self) -> None:
        # Four queens, three jacks and one club: only the club is freely buryable, so a jack
        # must go with it — but never a queen.
        buried = self._chosen_bury(("QC", "QS", "QH", "QD", "JC", "JS", "JH", "7C"))
        self.assertIn(Card.parse("7C"), buried)
        for card in buried:
            self.assertIsNot(Rank.QUEEN, card.rank)

    def test_an_all_trump_hand_buries_jacks_rather_than_queens(self) -> None:
        # Every queen and every jack. Two jacks are always available, so a queen is never
        # forced — the constraint is total, not best-effort.
        buried = self._chosen_bury(("QC", "QS", "QH", "QD", "JC", "JS", "JH", "JD"))
        for card in buried:
            self.assertIs(Rank.JACK, card.rank, f"buried {card} instead of a jack")

    def test_call_quality_prefers_a_near_void_suit(self) -> None:
        singleton = call_quality(_cards("QC", "QS", "JD", "AD", "7C", "9H"), RULES)
        crowded = call_quality(_cards("QC", "QS", "JD", "7C", "8C", "9C"), RULES)
        self.assertGreater(singleton, crowded)

    def test_call_quality_penalises_being_stuck_with_a_high_keeper(self) -> None:
        # The retention rule forces the picker to hold a called-suit card until the suit is led.
        # Clubs must be the *only* callable suit here: call_quality reports the best call
        # available, so a second callable suit would mask the difference entirely.
        low_keeper = call_quality(_cards("QC", "QS", "JD", "AD", "TD", "7C"), RULES)
        high_keeper = call_quality(_cards("QC", "QS", "JD", "AD", "TD", "TC"), RULES)
        self.assertGreater(low_keeper, high_keeper)

    def test_no_ordinary_call_scores_worse_than_any_real_one(self) -> None:
        # All fail cards are aces, so only an under is possible.
        self.assertLess(
            call_quality(_cards("AC", "AS", "QC", "JD", "TD", "AD"), RULES),
            call_quality(_cards("QC", "QS", "JD", "AD", "7C", "9H"), RULES),
        )


class CallingTests(unittest.TestCase):
    def _calling_state(self, hands: list[list[Card]]):
        state = create_game(RULES, _seats(), 909)
        state.hand.hands = [list(cards) for cards in hands]
        state.hand.blind = []
        state.hand.phase = Phase.CALLING
        state.hand.picker_seat = 0
        state.hand.turn_seat = 0
        return state

    def test_a_near_void_suit_is_called_over_a_crowded_one(self) -> None:
        state = self._calling_state([
            _cards("QC", "QS", "JD", "9H", "7C", "8C"),
            _cards("AC", "AH", "7S", "8S", "9S", "TS"),
            _cards("QH", "QD", "JC", "JS", "JH", "AD"),
            _cards("KC", "TC", "9C", "KS", "KH", "TH"),
            _cards("KD", "TD", "9D", "8D", "7D", "7H"),
        ])
        action = HeuristicStrategy().choose(
            seat_view(state, 0), legal_actions(state, 0), random.Random(1)
        )
        # Hearts is a singleton, clubs is held twice — call through the short suit.
        self.assertEqual("call", action.type)
        self.assertEqual(Card.parse("AH"), action.card)

    def test_an_under_spends_the_least_useful_card(self) -> None:
        state = self._calling_state([
            _cards("AC", "AS", "QC", "JD", "TD", "AD"),
            _cards("AH", "7H", "8H", "9H", "7S", "8S"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("KC", "TC", "KS", "TS", "KH", "TH"),
            _cards("KD", "9D", "8D", "7D", "7C", "8C"),
        ])
        action = HeuristicStrategy().choose(
            seat_view(state, 0), legal_actions(state, 0), random.Random(1)
        )
        self.assertIsInstance(action, CallUnderAction)
        # Never spend a queen when a fail ace is dead weight anyway.
        self.assertNotEqual(Card.parse("QC"), action.under)


class SafetyTests(unittest.TestCase):
    def test_every_choice_is_a_legal_action(self) -> None:
        # The strategy must never invent an intent: apply_action raises on anything outside
        # legal_actions, and an AI that raises takes the whole game down.
        state = create_game(RULES, _seats(), 20260725)
        strategy = HeuristicStrategy()
        rng = random.Random(5)
        for _ in range(400):
            turn = state.hand.turn_seat
            self.assertIsNotNone(turn)
            legal = legal_actions(state, turn)
            self.assertTrue(legal)
            action = strategy.choose(seat_view(state, turn), legal, rng)
            self.assertIn(action, legal)
            state, _ = apply_action(state, turn, action)

    def test_an_empty_legal_list_is_rejected_rather_than_guessed_at(self) -> None:
        state = create_game(RULES, _seats(), 1)
        with self.assertRaises(ValueError):
            HeuristicStrategy().choose(seat_view(state, 0), [], random.Random(1))


if __name__ == "__main__":
    unittest.main()
