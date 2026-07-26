"""Unders and calling a ten.

An under is needed exactly when the picker holds no fail card of the suit they call. That one
condition covers both source cases, and it means a called *ten* never needs an under: calling a
ten requires holding all three fail aces, which guarantees a card in every fail suit.
"""

import json
import unittest

from .ai_knowledge import read_view
from .cards import Card
from .engine import apply_action, create_game, legal_actions
from .rules import RuleSet
from .scoring import trick_winner
from .serialization import (
    action_from_dict,
    action_to_dict,
    full_state_from_dict,
    full_state_to_dict,
    seat_view,
)
from .state import BuryAction, CallUnderAction, Phase, PlayAction, Seat, UnburyAction

RULES = RuleSet()


def _seats() -> list[Seat]:
    return [Seat(index, f"Seat {index}", index == 0, None if index == 0 else "random") for index in range(5)]


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _calling_state(hands: list[list[Card]], *, picker: int = 0, buried=()):
    """A game parked in the CALLING phase with every hand stated exactly."""
    state = create_game(RULES, _seats(), 4242)
    hand = state.hand
    hand.hands = [list(cards) for cards in hands]
    hand.blind = []
    hand.buried = list(buried)
    hand.phase = Phase.CALLING
    hand.picker_seat = picker
    hand.turn_seat = picker
    return state


def _calls(state):
    return legal_actions(state, state.hand.picker_seat)


def _called_cards(state):
    return {action.card for action in _calls(state) if action.type == "call" and action.card}


def _unders(state):
    return [action for action in _calls(state) if action.type == "call_under"]


class CallLadderTests(unittest.TestCase):
    def test_ordinary_call_is_unchanged_for_a_normal_hand(self) -> None:
        state = _calling_state([
            _cards("QC", "JD", "7C", "8C", "9S", "TD"),
            _cards("AC", "AS", "AH", "7S", "8S", "9H"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("KC", "TC", "KS", "TS", "KH", "TH"),
            _cards("AD", "KD", "9D", "8D", "7D", "7H"),
        ])
        # Clubs and spades are held without their aces, so both call ordinarily. Hearts would
        # need an under, but an under is forced-only and never offered beside an ordinary call.
        self.assertEqual({Card.parse("AC"), Card.parse("AS")}, _called_cards(state))
        self.assertFalse(_unders(state))

    def test_all_fail_cards_being_aces_forces_an_under(self) -> None:
        # Holds AC and AS and nothing else fail: cannot call either, and is void in hearts, so
        # calling AH requires a card face down.
        state = _calling_state([
            _cards("AC", "AS", "QC", "JD", "TD", "AD"),
            _cards("AH", "7H", "8H", "9H", "7S", "8S"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("KC", "TC", "KS", "TS", "KH", "TH"),
            _cards("KD", "9D", "8D", "7D", "7C", "8C"),
        ])
        unders = _unders(state)
        self.assertTrue(unders)
        self.assertEqual({Card.parse("AH")}, {action.card for action in unders})
        # Any card in hand may go face down.
        self.assertEqual(set(state.hand.hands[0]), {action.under for action in unders})
        self.assertEqual(set(), _called_cards(state))

    def test_holding_all_three_aces_calls_a_ten_without_an_under(self) -> None:
        state = _calling_state([
            _cards("AC", "AS", "AH", "QC", "JD", "AD"),
            _cards("TC", "7H", "8H", "9H", "7S", "8S"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("TS", "TH", "KS", "KC", "KH", "TD"),
            _cards("KD", "9D", "8D", "7D", "7C", "8C"),
        ])
        called = _called_cards(state)
        # Every ace is held, so the ladder falls to tens. Holding all three aces means holding a
        # card in every fail suit, so the picker can always follow — no under is ever required.
        self.assertEqual(3, len(called))
        self.assertTrue(all(card.rank is Card.parse("TC").rank for card in called))
        self.assertFalse(_unders(state))

    def test_ladder_reaches_kings_when_aces_and_tens_are_all_held(self) -> None:
        state = _calling_state([
            _cards("AC", "AS", "AH", "TC", "TS", "TH"),
            _cards("KC", "7H", "8H", "9H", "7S", "8S"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("KS", "KH", "QC", "JD", "AD", "TD"),
            _cards("KD", "9D", "8D", "7D", "7C", "8C"),
        ])
        called = _called_cards(state)
        self.assertEqual(3, len(called))
        self.assertTrue(all(card.rank is Card.parse("KC").rank for card in called))

    def test_ladder_falls_through_when_the_missing_aces_are_buried(self) -> None:
        # Holds AC; AS and AH are buried, so no ace has a holder even though the picker does not
        # hold all three. Falling through by availability keeps a partner reachable.
        state = _calling_state(
            [
                _cards("AC", "QC", "JD", "TD", "AD", "7C"),
                _cards("TC", "7H", "8H", "9H", "7S", "8S"),
                _cards("QS", "QH", "QD", "JC", "JS", "JH"),
                _cards("TS", "TH", "KS", "KC", "KH", "KD"),
                _cards("9D", "8D", "7D", "8C", "9C", "9S"),
            ],
            buried=_cards("AS", "AH"),
        )
        # Only clubs is followable, and its ace is held, so the ten of clubs is the call.
        self.assertEqual({Card.parse("TC")}, _called_cards(state))

    def test_going_alone_is_always_offered(self) -> None:
        state = _calling_state([
            _cards("AC", "AS", "QC", "JD", "TD", "AD"),
            _cards("AH", "7H", "8H", "9H", "7S", "8S"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("KC", "TC", "KS", "TS", "KH", "TH"),
            _cards("KD", "9D", "8D", "7D", "7C", "8C"),
        ])
        self.assertIn(None, [action.card for action in _calls(state) if action.type == "call"])


def _called_state(hands: list[list[Card]], *, buried: list[Card], picker: int = 0):
    """A game parked in CALLING, having already buried the given cards."""
    state = _burying_state(hands, picker=picker)
    state.hand.buried = list(buried)
    state.hand.hands[picker] = [card for card in hands[picker] if card not in buried]
    state.hand.phase = Phase.CALLING
    return state


def _burying_state(hands: list[list[Card]], *, picker: int = 0):
    """A game parked in BURYING with the picker holding a full post-blind hand."""
    state = create_game(RULES, _seats(), 4242)
    hand = state.hand
    hand.hands = [list(cards) for cards in hands]
    hand.blind = []
    hand.phase = Phase.BURYING
    hand.picker_seat = picker
    hand.turn_seat = picker
    return state


def _buries(state) -> list[set[Card]]:
    return [
        set(action.cards)
        for action in legal_actions(state, state.hand.picker_seat)
        if action.type == "bury"
    ]


class BuryAndCallInteractionTests(unittest.TestCase):
    """Burying is unrestricted; what is left decides what may be called.

    A picker who buries away the only suit whose ace they could call is not blocked — they are
    simply left with going alone, and may take the cards back and choose again.
    """

    # Clubs without the ace (callable) plus hearts with the ace (not callable).
    TWO_CLUBS_AND_THE_HEART_ACE = [
        _cards("7C", "8C", "AH", "7H", "QC", "JD", "AD", "TD"),
        _cards("AC", "AS", "9H", "TH", "KH", "7S"),
        _cards("QS", "QH", "QD", "JC", "JS", "JH"),
        _cards("KC", "TC", "KS", "TS", "9S", "8S"),
        _cards("KD", "9D", "8D", "7D", "9C", "8H"),
    ]

    def test_every_bury_is_legal(self) -> None:
        state = _burying_state(self.TWO_CLUBS_AND_THE_HEART_ACE)
        offered = _buries(state)
        self.assertEqual(28, len(offered))
        self.assertIn(set(_cards("7C", "8C")), offered, "burying the callable suit is allowed")

    def test_burying_the_callable_suit_away_leaves_only_going_alone(self) -> None:
        state = _called_state(self.TWO_CLUBS_AND_THE_HEART_ACE, buried=_cards("7C", "8C"))
        calls = _calls(state)
        self.assertEqual([None], [a.card for a in calls if a.type == "call"])
        self.assertFalse(_unders(state), "an under is not theirs to take here")

    def test_keeping_a_club_offers_the_ace_of_clubs(self) -> None:
        state = _called_state(self.TWO_CLUBS_AND_THE_HEART_ACE, buried=_cards("8C", "7H"))
        self.assertIn(Card.parse("AC"), _called_cards(state))
        self.assertFalse(_unders(state))

    def test_holding_the_ace_of_every_suit_you_hold_still_earns_an_under(self) -> None:
        # Ace+7 of clubs and spades: no suit was ever callable, so the under is legitimate
        # however the picker buries.
        hands = [
            _cards("AC", "7C", "AS", "7S", "QC", "JD", "AD", "TD"),
            _cards("AH", "8H", "9H", "TH", "KH", "7H"),
            _cards("QS", "QH", "QD", "JC", "JS", "JH"),
            _cards("KC", "TC", "8C", "9C", "KS", "TS"),
            _cards("KD", "9D", "8D", "7D", "9S", "8S"),
        ]
        for bury in (_cards("QC", "JD"), _cards("AC", "7C"), _cards("7C", "7S")):
            with self.subTest(bury=[str(card) for card in bury]):
                state = _called_state(hands, buried=bury)
                unders = _unders(state)
                self.assertTrue(unders, "the under should survive any bury here")
                self.assertEqual({Card.parse("AH")}, {action.card for action in unders})

    def test_an_all_trump_hand_earns_an_under(self) -> None:
        hands = [
            _cards("QC", "QS", "QH", "QD", "JC", "JS", "JH", "JD"),
            _cards("AC", "AS", "AH", "7C", "8C", "9C"),
            _cards("7S", "8S", "9S", "7H", "8H", "9H"),
            _cards("KC", "TC", "KS", "TS", "KH", "TH"),
            _cards("AD", "KD", "TD", "9D", "8D", "7D"),
        ]
        state = _called_state(hands, buried=_cards("JH", "JD"))
        self.assertTrue(_unders(state))


class UnburyTests(unittest.TestCase):
    def _state(self, *, human_picker: bool):
        seats = [
            Seat(index, f"Seat {index}", index == 0 if human_picker else False, "random")
            for index in range(5)
        ]
        state = create_game(RULES, seats, 4242)
        state.hand.hands = [
            list(cards) for cards in BuryAndCallInteractionTests.TWO_CLUBS_AND_THE_HEART_ACE
        ]
        state.hand.blind = []
        state.hand.buried = _cards("7C", "8C")
        state.hand.hands[0] = [
            card
            for card in BuryAndCallInteractionTests.TWO_CLUBS_AND_THE_HEART_ACE[0]
            if card not in state.hand.buried
        ]
        state.hand.phase = Phase.CALLING
        state.hand.picker_seat = 0
        state.hand.turn_seat = 0
        return state

    def test_a_human_picker_may_take_the_bury_back(self) -> None:
        state = self._state(human_picker=True)
        self.assertIn(UnburyAction(), legal_actions(state, 0))

    def test_an_ai_picker_may_not(self) -> None:
        # Offering it would let the drive loop churn bury/unbury against its action cap.
        state = self._state(human_picker=False)
        self.assertNotIn(UnburyAction(), legal_actions(state, 0))

    def test_unburying_restores_the_hand_and_the_phase(self) -> None:
        state = self._state(human_picker=True)
        before = sorted(str(card) for card in state.hand.hands[0] + state.hand.buried)
        state, events = apply_action(state, 0, UnburyAction())
        self.assertEqual(Phase.BURYING, state.hand.phase)
        self.assertEqual([], state.hand.buried)
        self.assertEqual(before, sorted(str(card) for card in state.hand.hands[0]))
        self.assertEqual(["unburied"], [event.type for event in events])

    def test_the_picker_can_then_bury_differently_and_call(self) -> None:
        state = self._state(human_picker=True)
        state, _ = apply_action(state, 0, UnburyAction())
        state, _ = apply_action(state, 0, BuryAction(tuple(_cards("8C", "7H"))))
        self.assertEqual(Phase.CALLING, state.hand.phase)
        self.assertIn(Card.parse("AC"), _called_cards(state))

    def test_unbury_round_trips_on_the_wire(self) -> None:
        self.assertEqual(
            UnburyAction(), action_from_dict(json.loads(json.dumps(action_to_dict(UnburyAction()))))
        )


def _under_game():
    """Seat 0 has called A♥ under, with Q♣ face down. Seat 1 holds the ace."""
    state = _calling_state([
        _cards("AC", "AS", "QC", "JD", "TD", "AD"),
        _cards("AH", "7H", "8H", "9H", "7S", "8S"),
        _cards("9C", "KC", "TC", "KS", "TS", "9S"),
        _cards("KH", "TH", "JC", "JS", "JH", "QS"),
        _cards("7C", "8C", "KD", "9D", "8D", "7D"),
    ])
    state, _ = apply_action(state, 0, CallUnderAction(Card.parse("AH"), Card.parse("QC")))
    return state


def _play(state, seat: int, card: str):
    state.hand.turn_seat = seat
    return apply_action(state, seat, PlayAction(Card.parse(card)))[0]


class UnderPlayTests(unittest.TestCase):
    def test_calling_under_records_the_card_and_the_partner(self) -> None:
        state = _under_game()
        self.assertEqual(Card.parse("QC"), state.hand.under_card)
        self.assertEqual(Card.parse("AH"), state.hand.called_card)
        self.assertEqual(1, state.hand.partner_seat)
        self.assertEqual(Phase.PLAYING, state.hand.phase)

    def test_the_under_may_not_be_played_early(self) -> None:
        state = _under_game()
        state.hand.turn_seat = 0
        state.hand.current_trick = [(4, Card.parse("7C"))]
        playable = [action.card for action in legal_actions(state, 0) if action.type == "play"]
        self.assertNotIn(Card.parse("QC"), playable)
        self.assertTrue(playable)

    def test_the_under_is_the_only_play_when_the_called_suit_is_led(self) -> None:
        state = _under_game()
        state.hand.turn_seat = 0
        state.hand.current_trick = [(3, Card.parse("KH"))]
        self.assertEqual(
            [Card.parse("QC")],
            [action.card for action in legal_actions(state, 0) if action.type == "play"],
        )

    def test_the_under_is_playable_when_it_is_the_last_card(self) -> None:
        # Restrict, but never strip the only option — the same guard as called-suit retention.
        state = _under_game()
        state.hand.hands[0] = _cards("QC")
        state.hand.turn_seat = 0
        state.hand.current_trick = [(4, Card.parse("7C"))]
        self.assertEqual(
            [Card.parse("QC")],
            [action.card for action in legal_actions(state, 0) if action.type == "play"],
        )

    def test_an_under_that_leads_stands_in_for_the_called_suit(self) -> None:
        state = _under_game()
        state.hand.hands[0] = _cards("QC")
        state.hand.trick_leader = 0
        state = _play(state, 0, "QC")
        # Hearts counts as led, so the partner is obliged to produce the called ace.
        self.assertTrue(state.hand.called_suit_led)
        self.assertEqual(
            [Card.parse("AH")],
            [action.card for action in legal_actions(state, 1) if action.type == "play"],
        )


class TrickWinnerTests(unittest.TestCase):
    def test_the_under_cannot_win_even_as_the_highest_card(self) -> None:
        trick = [
            (0, Card.parse("QC")),  # the under — otherwise the best card in the deck
            (1, Card.parse("7H")),
            (2, Card.parse("AH")),
            (3, Card.parse("8H")),
            (4, Card.parse("9H")),
        ]
        self.assertEqual(0, trick_winner(trick, RULES))
        self.assertEqual(
            2, trick_winner(trick, RULES, ineligible=Card.parse("QC"), led_suit="H")
        )

    def test_an_under_leading_puts_the_called_suit_in_charge(self) -> None:
        trick = [
            (0, Card.parse("QC")),
            (1, Card.parse("AH")),
            (2, Card.parse("7C")),
            (3, Card.parse("8C")),
            (4, Card.parse("9C")),
        ]
        # Read literally the lead is trump and Q♣ takes it; as an under it stands for hearts,
        # so the called ace wins instead.
        self.assertEqual(0, trick_winner(trick, RULES))
        self.assertEqual(
            1, trick_winner(trick, RULES, ineligible=Card.parse("QC"), led_suit="H")
        )


def _under_played():
    """Seat 3 leads hearts, the under falls, and seat 1 takes the trick with the called ace."""
    state = _under_game()
    state.hand.trick_leader = 3
    for seat, card in ((3, "KH"), (4, "7C"), (0, "QC"), (1, "AH"), (2, "9C")):
        state = _play(state, seat, card)
    return state


class UnderRedactionTests(unittest.TestCase):
    def test_only_the_picker_sees_an_unplayed_under(self) -> None:
        state = _under_game()
        self.assertEqual("QC", seat_view(state, 0)["under_card"])
        for seat in range(1, 5):
            self.assertIsNone(seat_view(state, seat)["under_card"])

    def test_the_under_is_hidden_while_its_trick_is_still_open(self) -> None:
        state = _under_game()
        state.hand.trick_leader = 3
        state = _play(state, 3, "KH")
        state = _play(state, 0, "QC")
        # Nobody has won it yet, so only the picker may look.
        for seat in range(1, 5):
            entry = next(
                play for play in seat_view(state, seat)["current_trick"] if play.get("under")
            )
            self.assertIsNone(entry["card"], f"seat {seat} saw the under")

    def test_a_played_under_is_masked_for_everyone_but_the_picker_and_winner(self) -> None:
        state = _under_played()
        self.assertEqual([1], state.hand.trick_winners)

        def under_entry(seat: int) -> dict:
            plays = seat_view(state, seat)["completed_tricks"][0]["plays"]
            return next(play for play in plays if play.get("under"))

        self.assertEqual("QC", under_entry(0)["card"])  # the picker
        self.assertEqual("QC", under_entry(1)["card"])  # took the trick
        for seat in (2, 3, 4):
            self.assertIsNone(under_entry(seat)["card"], f"seat {seat} saw the under")
            self.assertTrue(under_entry(seat)["under"])

    def test_the_under_never_appears_anywhere_in_an_unentitled_view(self) -> None:
        state = _under_played()
        for seat in (2, 3, 4):
            payload = json.dumps(seat_view(state, seat))
            self.assertNotIn('"QC"', payload, f"seat {seat} saw the under somewhere")

    def test_the_card_played_event_does_not_announce_the_under(self) -> None:
        # seat_view embeds the events from the actions just applied, so masking the trick
        # entries alone is not enough — the event carries the same card.
        state = _under_game()
        state.hand.trick_leader = 3
        state = _play(state, 3, "KH")
        state.hand.turn_seat = 0
        state, events = apply_action(state, 0, PlayAction(Card.parse("QC")))

        picker_events = seat_view(state, 0, events=events)["events"]
        self.assertEqual("QC", picker_events[0]["card"])

        for seat in (1, 2, 3, 4):
            played = seat_view(state, seat, events=events)["events"][0]
            self.assertEqual("card_played", played["type"])
            self.assertIsNone(played["card"], f"seat {seat} was told the under")
            self.assertTrue(played["under"])
            self.assertNotIn('"QC"', json.dumps(seat_view(state, seat, events=events)))

    def test_knowledge_leaves_a_masked_under_unseen(self) -> None:
        state = _under_game()
        state.hand.trick_leader = 3
        state = _play(state, 3, "KH")
        state = _play(state, 0, "QC")

        opponent = read_view(seat_view(state, 2))
        # Not seen, so it stays in unseen alongside the bury — dead but unidentified.
        self.assertNotIn(Card.parse("QC"), opponent.played)
        self.assertIn(Card.parse("QC"), opponent.unseen)
        # An under proves nothing about voids, whichever suit it really is.
        self.assertEqual(frozenset(), opponent.voids[0])
        # It cannot win, so it is never the seat currently taking the trick.
        self.assertEqual(3, opponent.trick_winning_seat)

        picker = read_view(seat_view(state, 0))
        self.assertIn(Card.parse("QC"), picker.played)
        self.assertNotIn(Card.parse("QC"), picker.unseen)


class SerializationTests(unittest.TestCase):
    def test_call_under_round_trips_on_the_wire(self) -> None:
        action = CallUnderAction(Card.parse("AH"), Card.parse("QC"))
        self.assertEqual(action, action_from_dict(json.loads(json.dumps(action_to_dict(action)))))

    def test_under_card_survives_a_full_state_round_trip(self) -> None:
        state = _under_played()
        encoded = full_state_to_dict(state)
        self.assertEqual("QC", encoded["hand"]["under_card"])
        decoded = full_state_from_dict(json.loads(json.dumps(encoded)))
        self.assertEqual(Card.parse("QC"), decoded.hand.under_card)
        self.assertEqual(encoded, full_state_to_dict(decoded))

    def test_retired_ruleset_fields_are_ignored_on_decode(self) -> None:
        # Games stored before no_callable_ace_fallback was removed must still load.
        legacy = RuleSet().to_dict() | {"no_callable_ace_fallback": "alone"}
        self.assertEqual(RuleSet(), RuleSet.from_dict(legacy))


if __name__ == "__main__":
    unittest.main()
