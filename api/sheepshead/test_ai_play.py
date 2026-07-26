"""Trick-play tests.

Ordered by how visible the failure is, per AI_PLAN.md §1.4: schmear direction first, since
throwing points to the wrong side is the most obviously wrong thing an AI can do.
"""

import random
import unittest

from .ai_heuristic import (
    ALLY_THRESHOLD,
    OPPONENT_UNKNOWN_ALLY,
    PICKER_UNKNOWN_ALLY,
    HeuristicStrategy,
    allegiance,
    beats,
    card_cost,
)
from .ai_knowledge import read_view
from .cards import Card, build_deck
from .engine import apply_action, create_game, legal_actions
from .rules import RuleSet
from .serialization import seat_view
from .state import GameState, HandState, Phase, Seat

RULES = RuleSet()


def _seats() -> list[Seat]:
    return [Seat(index, f"Seat {index}", False, "heuristic") for index in range(5)]


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _trick(*plays: tuple[int, str]) -> list[tuple[int, Card]]:
    return [(seat, Card.parse(card)) for seat, card in plays]


def _playing_state(
    hands: list[list[Card]],
    *,
    turn: int,
    picker: int = 0,
    called: str | None = "AH",
    partner: int | None = 1,
    revealed: bool = False,
    current=None,
    taken=None,
) -> GameState:
    piles = [[] for _ in range(5)]
    for seat, cards in (taken or {}).items():
        piles[seat] = list(cards)
    return GameState(
        ruleset=RULES,
        seats=_seats(),
        scores=[0] * 5,
        hand=HandState(
            hand_number=1,
            dealer_seat=4,
            hands=[list(cards) for cards in hands],
            blind=[],
            buried=[],
            phase=Phase.PLAYING,
            turn_seat=turn,
            passes=[],
            picker_seat=picker,
            called_card=Card.parse(called) if called else None,
            partner_seat=partner,
            partner_revealed=revealed,
            is_leaster=False,
            current_trick=list(current or []),
            trick_leader=0,
            taken=piles,
            last_trick_winner=None,
            trick_winners=[],
        ),
        hand_history=[],
        rng_seed=1,
    )


def _decide(state: GameState, seat: int) -> Card:
    action = HeuristicStrategy().choose(
        seat_view(state, seat), legal_actions(state, seat), random.Random(11)
    )
    return action.card


class AllegianceTests(unittest.TestCase):
    def test_known_teams_are_certain(self) -> None:
        state = _playing_state(
            [_cards("QC"), _cards("AH"), _cards("7C"), _cards("8C"), _cards("9C")],
            turn=2,
            revealed=True,
        )
        knowledge = read_view(seat_view(state, 2))
        self.assertEqual(0.0, allegiance(knowledge, 0))  # picker
        self.assertEqual(0.0, allegiance(knowledge, 1))  # revealed partner
        self.assertEqual(1.0, allegiance(knowledge, 3))  # fellow opponent

    def test_the_base_rate_is_not_symmetric(self) -> None:
        # An opponent sees 3 unknown non-pickers of whom 2 are allies; the picker sees 4
        # unknowns of whom 1 is the partner. One blanket rule would be wrong for somebody.
        state = _playing_state(
            [_cards("QC"), _cards("AH"), _cards("7C"), _cards("8C"), _cards("9C")],
            turn=2,
        )
        opponent = read_view(seat_view(state, 2))
        self.assertAlmostEqual(OPPONENT_UNKNOWN_ALLY, allegiance(opponent, 3))
        self.assertEqual(0.0, allegiance(opponent, 0), "the picker is never unknown")

        picker = read_view(seat_view(state, 0))
        self.assertAlmostEqual(PICKER_UNKNOWN_ALLY, allegiance(picker, 3))

    def test_an_opponent_leans_toward_helping_and_the_picker_does_not(self) -> None:
        self.assertGreater(OPPONENT_UNKNOWN_ALLY, ALLY_THRESHOLD)
        self.assertLess(PICKER_UNKNOWN_ALLY, ALLY_THRESHOLD)


class BeatsTests(unittest.TestCase):
    def test_trump_beats_fail_and_higher_trump_beats_lower(self) -> None:
        self.assertTrue(beats(Card.parse("7D"), Card.parse("AC"), "C", RULES))
        self.assertTrue(beats(Card.parse("QC"), Card.parse("JD"), "C", RULES))
        self.assertFalse(beats(Card.parse("JD"), Card.parse("QC"), "C", RULES))

    def test_off_suit_fail_never_beats_the_led_suit(self) -> None:
        self.assertFalse(beats(Card.parse("AS"), Card.parse("7C"), "C", RULES))


class SchmearTests(unittest.TestCase):
    def test_points_go_to_a_known_partner_taking_the_trick(self) -> None:
        # Seat 1 (revealed partner) is winning with the ace; seat 0 (picker) plays last and
        # cannot follow, so it should dump its fattest card onto its own side.
        state = _playing_state(
            [
                _cards("TS", "7S", "QC"),
                _cards("AH", "8H"),
                _cards("9H"),
                _cards("KH"),
                _cards("7H"),
            ],
            turn=0,
            revealed=True,
            current=_trick((2, "9H"), (3, "KH"), (4, "7H"), (1, "AH")),
        )
        self.assertEqual(Card.parse("TS"), _decide(state, 0))

    def test_points_are_withheld_from_an_opponent_taking_the_trick(self) -> None:
        # Same shape, but an opponent is winning and the hand holds no card that could take it
        # back — the trump has to be absent, or taking an 18-point trick is simply correct.
        state = _playing_state(
            [
                _cards("TS", "7S", "9S"),
                _cards("8H"),
                _cards("AH"),
                _cards("KH"),
                _cards("7H"),
            ],
            turn=0,
            partner=1,
            revealed=True,
            current=_trick((2, "AH"), (3, "KH"), (4, "7H"), (1, "8H")),
        )
        self.assertEqual(Card.parse("7S"), _decide(state, 0))

    def test_a_fat_trick_is_taken_from_an_opponent_when_it_can_be(self) -> None:
        # The case the test above used to be by accident, kept deliberately: last to play with
        # 15 points on the table and an opponent winning, the queen is well spent.
        state = _playing_state(
            [
                _cards("TS", "7S", "QC"),
                _cards("8H"),
                _cards("AH"),
                _cards("KH"),
                _cards("7H"),
            ],
            turn=0,
            partner=1,
            revealed=True,
            current=_trick((2, "AH"), (3, "KH"), (4, "7H"), (1, "8H")),
        )
        self.assertEqual(Card.parse("QC"), _decide(state, 0))

    def test_an_unknown_seat_is_fed_by_an_opponent_but_not_by_the_picker(self) -> None:
        # The identical trick, judged from two seats. Seat 2 is an opponent, so an unidentified
        # winner is probably an ally and gets the points; the picker sees the same seat as
        # probably hostile and keeps them.
        opponent_view = _playing_state(
            [
                _cards("9S"),
                _cards("AH"),
                _cards("TS", "7S"),
                _cards("KH"),
                _cards("8H"),
            ],
            turn=2,
            current=_trick((3, "KH"), (4, "8H")),
        )
        # Seat 3 is winning and unidentified; seat 2 has no hearts, so it discards.
        self.assertEqual(Card.parse("TS"), _decide(opponent_view, 2))

        picker_view = _playing_state(
            [
                _cards("TS", "7S"),
                _cards("AH"),
                _cards("9S"),
                _cards("KH"),
                _cards("8H"),
            ],
            turn=0,
            current=_trick((3, "KH"), (4, "8H")),
        )
        self.assertEqual(Card.parse("7S"), _decide(picker_view, 0))


class TakingTests(unittest.TestCase):
    def test_a_fat_trick_is_taken_even_at_a_price(self) -> None:
        state = _playing_state(
            [
                _cards("QC", "7C"),
                _cards("AH"),
                _cards("9S"),
                _cards("KH"),
                _cards("8H"),
            ],
            turn=0,
            revealed=True,
            current=_trick((2, "AS"), (3, "TS")),
        )
        # 21 points on the table with an opponent winning: spend the queen.
        self.assertEqual(Card.parse("QC"), _decide(state, 0))

    def test_a_worthless_trick_is_not_bought_with_a_good_card(self) -> None:
        state = _playing_state(
            [
                _cards("QC", "7C"),
                _cards("AH"),
                _cards("9S"),
                _cards("KH"),
                _cards("8H"),
            ],
            turn=0,
            revealed=True,
            current=_trick((2, "8S"), (3, "9S")),
        )
        self.assertEqual(Card.parse("7C"), _decide(state, 0))


class CalledSuitTrickTests(unittest.TestCase):
    """The called card is *forced* into its own trick, so it counts before it is played.

    Reported from play: an opponent holding one queen ducked a called-suit trick, because the
    pot read 3 points instead of the 14 actually at stake.
    """

    # Hearts called. Seat 4 leads a low heart; seat 0 is an opponent, void in hearts, and its
    # only trump is the queen of clubs.
    HANDS = [
        _cards("QC", "9S", "7S"),
        _cards("AH", "8H"),
        _cards("KH", "9C"),
        _cards("TH", "8C"),
        _cards("7H", "9H"),
    ]

    def _state(self, **kwargs):
        return _playing_state(
            self.HANDS, turn=0, picker=3, partner=1, called="AH",
            current=_trick((4, "7H")), **kwargs,
        )

    def test_an_opponent_trumps_in_to_capture_the_forced_ace(self) -> None:
        self.assertEqual(Card.parse("QC"), _decide(self._state(), 0))

    def test_it_still_trumps_once_the_ace_is_actually_on_the_table(self) -> None:
        # Same trick a beat later: now the 11 points are visible in trick_points instead of
        # being anticipated, and the decision must not change.
        state = _playing_state(
            self.HANDS, turn=0, picker=3, partner=1, called="AH", revealed=True,
            current=_trick((4, "7H"), (1, "AH")),
        )
        self.assertEqual(Card.parse("QC"), _decide(state, 0))

    def test_the_bonus_does_not_apply_once_the_partner_is_known_spent(self) -> None:
        # Partner revealed and the called card gone: nothing is forced any more, so a lone
        # queen goes back to being too expensive for a trick worth 4.
        hands = [_cards("QC", "9S", "7S"), _cards("8H",), _cards("KH", "9C"),
                 _cards("TH", "8C"), _cards("7H", "9H")]
        state = _playing_state(
            hands, turn=0, picker=3, partner=1, called="AH", revealed=True,
            current=_trick((4, "7H")),
        )
        self.assertNotEqual(Card.parse("QC"), _decide(state, 0))

    def test_the_pickers_side_does_not_get_the_bonus(self) -> None:
        # The ace is already coming to the picker's team, so counting it would only buy
        # over-trumping their own partner. Seat 0 is the picker here, same cards.
        state = _playing_state(
            self.HANDS, turn=0, picker=0, partner=1, called="AH",
            current=_trick((4, "7H")),
        )
        self.assertNotEqual(Card.parse("QC"), _decide(state, 0))

    def test_no_bonus_on_a_trick_in_another_suit(self) -> None:
        # Clubs led, hearts called: nothing is forced, so the queen stays home.
        hands = [_cards("QC", "9S", "7S"), _cards("AH", "8H"), _cards("KH", "9C"),
                 _cards("TH", "8C"), _cards("7C", "9H")]
        state = _playing_state(
            hands, turn=0, picker=3, partner=1, called="AH", current=_trick((4, "7C")),
        )
        self.assertNotEqual(Card.parse("QC"), _decide(state, 0))


class LeadTests(unittest.TestCase):
    # Both cases use the same hand, where the called suit's card (9H) is *not* the cheapest
    # fail (7C is). Only then does the choice reveal whether the called suit was targeted
    # deliberately or just happened to be the cheapest thing to throw.
    HIDDEN_PARTNER_HANDS = [
        _cards("QC", "JD"),
        _cards("AH", "7S"),
        _cards("9H", "7C", "QS"),
        _cards("KH", "8C"),
        _cards("7H", "9S"),
    ]

    def test_an_opponent_leads_the_called_suit_to_flush_the_ace(self) -> None:
        state = _playing_state(self.HIDDEN_PARTNER_HANDS, turn=2)
        self.assertEqual(Card.parse("9H"), _decide(state, 2))

    def test_the_called_suit_stops_being_special_once_the_ace_is_out(self) -> None:
        state = _playing_state(self.HIDDEN_PARTNER_HANDS, turn=2, revealed=True)
        # Hearts is now an ordinary suit, so the cheapest fail card goes instead.
        self.assertEqual(Card.parse("7C"), _decide(state, 2))

    def test_the_picker_pulls_trump(self) -> None:
        state = _playing_state(
            [
                _cards("QC", "JD", "7C"),
                _cards("AH", "7S"),
                _cards("8H", "9C"),
                _cards("KH", "8C"),
                _cards("7H", "9S"),
            ],
            turn=0,
            revealed=True,
        )
        self.assertEqual(Card.parse("QC"), _decide(state, 0))


class CostTests(unittest.TestCase):
    def test_every_card_has_a_cost(self) -> None:
        for card in build_deck(RULES):
            self.assertGreater(card_cost(card, RULES), 0)

    def test_cost_rises_within_trump_and_within_a_fail_suit(self) -> None:
        self.assertLess(card_cost(Card.parse("7D"), RULES), card_cost(Card.parse("QC"), RULES))
        self.assertLess(card_cost(Card.parse("JD"), RULES), card_cost(Card.parse("QD"), RULES))
        self.assertLess(card_cost(Card.parse("7C"), RULES), card_cost(Card.parse("KC"), RULES))
        self.assertLess(card_cost(Card.parse("KC"), RULES), card_cost(Card.parse("AC"), RULES))

    def test_worthless_fail_is_the_cheapest_thing_to_shed(self) -> None:
        # Trump does *not* uniformly outrank fail, and should not: a fail ace is a likely trick
        # and the 7 of diamonds is nearly worthless, which is what offensive_strength says too.
        # The shedding order that matters is junk fail, then low trump, then tens and aces.
        self.assertLess(card_cost(Card.parse("7C"), RULES), card_cost(Card.parse("7D"), RULES))
        self.assertLess(card_cost(Card.parse("7D"), RULES), card_cost(Card.parse("TC"), RULES))
        self.assertLess(card_cost(Card.parse("TC"), RULES), card_cost(Card.parse("AC"), RULES))


class FullHandTests(unittest.TestCase):
    def test_the_strategy_plays_whole_games_legally(self) -> None:
        state = create_game(RULES, _seats(), 20260726)
        strategy = HeuristicStrategy()
        rng = random.Random(9)
        for _ in range(600):
            turn = state.hand.turn_seat
            self.assertIsNotNone(turn)
            legal = legal_actions(state, turn)
            self.assertTrue(legal)
            action = strategy.choose(seat_view(state, turn), legal, rng)
            self.assertIn(action, legal)
            state, _ = apply_action(state, turn, action)

    def test_points_are_conserved_across_scored_hands(self) -> None:
        state = create_game(RULES, _seats(), 4242)
        strategy = HeuristicStrategy()
        rng = random.Random(2)
        scored = 0
        while scored < 12:
            turn = state.hand.turn_seat
            action = strategy.choose(seat_view(state, turn), legal_actions(state, turn), rng)
            before = len(state.hand_history)
            state, _ = apply_action(state, turn, action)
            if len(state.hand_history) > before:
                result = state.hand_history[-1]
                self.assertEqual(120, sum(result.points) + result.buried_points)
                self.assertEqual(0, sum(result.deltas))
                scored += 1


if __name__ == "__main__":
    unittest.main()
