import json
import random
import unittest

from .cards import Card, Rank, Suit, build_deck, card_points
from .engine import apply_action, create_game, legal_actions
from .rules import RuleSet
from .scoring import score_hand, trick_winner
from .serialization import full_state_from_dict, full_state_to_dict, seat_view
from .state import HandState, Phase, PlayAction, Seat


def _seats() -> list[Seat]:
    return [Seat(index, f"Seat {index}", index == 0, None if index == 0 else "random") for index in range(5)]


def _scoring_hand(
    *,
    picker: int = 0,
    partner: int | None = 1,
    team_points: int = 61,
    all_tricks_for_picker_team: bool = False,
) -> HandState:
    rules = RuleSet()
    deck = build_deck(rules)
    # Scoring only needs point totals and trick-winner team membership. Partition the deck
    # deterministically until the requested team total is reached.
    team_cards: list[Card] = []
    other_cards: list[Card] = []
    running = 0
    for card in sorted(deck, key=card_points, reverse=True):
        points = card_points(card)
        if running + points <= team_points:
            team_cards.append(card)
            running += points
        else:
            other_cards.append(card)
    if running != team_points:
        raise AssertionError(f"Test fixture cannot make {team_points} points")
    taken = [[] for _ in range(5)]
    taken[picker] = team_cards
    taken[2 if partner != 2 else 3] = other_cards
    picker_team = {picker} | ({partner} if partner is not None else set())
    winning_picker = team_points >= 61
    winning_team = picker_team if winning_picker else set(range(5)) - picker_team
    trick_winner_seat = min(winning_team)
    trick_winners = (
        [trick_winner_seat] * 6
        if all_tricks_for_picker_team
        else [picker, 2, picker, 2, picker, 2]
    )
    return HandState(
        hand_number=1,
        dealer_seat=4,
        hands=[[] for _ in range(5)],
        blind=[],
        buried=[],
        phase=Phase.HAND_DONE,
        turn_seat=None,
        passes=[],
        picker_seat=picker,
        called_card=Card(Suit.HEARTS, Rank.ACE) if partner is not None else None,
        partner_seat=partner,
        partner_revealed=partner is not None,
        is_leaster=False,
        current_trick=[],
        trick_leader=0,
        taken=taken,
        last_trick_winner=trick_winner_seat,
        trick_winners=trick_winners,
    )


def _leaster_hand(
    *,
    taken: dict[int, list[Card]],
    trick_winners: list[int],
    blind: list[Card],
) -> HandState:
    """A finished leaster whose taken piles and trick order are stated explicitly."""
    piles = [[] for _ in range(5)]
    for seat, cards in taken.items():
        piles[seat] = cards
    return HandState(
        hand_number=1,
        dealer_seat=4,
        hands=[[] for _ in range(5)],
        blind=blind,
        buried=[],
        phase=Phase.HAND_DONE,
        turn_seat=None,
        passes=[0, 1, 2, 3, 4],
        picker_seat=None,
        called_card=None,
        partner_seat=None,
        partner_revealed=False,
        is_leaster=True,
        current_trick=[],
        trick_leader=0,
        taken=piles,
        last_trick_winner=trick_winners[-1],
        trick_winners=trick_winners,
    )


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


class EngineTests(unittest.TestCase):
    def _leaster_in_play(self, seed: int):
        """Drive a fresh game to the leaster's first trick via five passes."""
        state = create_game(RuleSet(), _seats(), seed)
        for _ in range(5):
            turn = state.hand.turn_seat
            pass_action = next(
                action for action in legal_actions(state, turn) if action.type == "pass"
            )
            state, _ = apply_action(state, turn, pass_action)
        self.assertEqual(Phase.PLAYING, state.hand.phase)
        return state

    def _play_one_trick(self, state):
        """Play the first legal card for each seat until the trick closes."""
        for _ in range(5):
            turn = state.hand.turn_seat
            play = next(
                action for action in legal_actions(state, turn) if action.type == "play"
            )
            state, _ = apply_action(state, turn, play)
        return state

    def test_state_round_trip(self) -> None:
        state = create_game(RuleSet(), _seats(), 123)
        encoded = full_state_to_dict(state)
        decoded = full_state_from_dict(json.loads(json.dumps(encoded)))
        self.assertEqual(encoded, full_state_to_dict(decoded))

    def test_all_pass_starts_leaster(self) -> None:
        state = create_game(RuleSet(), _seats(), 456)
        for _ in range(5):
            turn = state.hand.turn_seat
            pass_action = next(action for action in legal_actions(state, turn) if action.type == "pass")
            state, _ = apply_action(state, turn, pass_action)
        self.assertTrue(state.hand.is_leaster)
        self.assertEqual(Phase.PLAYING, state.hand.phase)

    def test_scoring_parity(self) -> None:
        partner_win = score_hand(_scoring_hand(team_points=61), RuleSet())
        self.assertEqual([2, 1, -1, -1, -1], partner_win.deltas)

        partner_loss = score_hand(_scoring_hand(team_points=60), RuleSet())
        self.assertEqual([-2, -1, 1, 1, 1], partner_loss.deltas)

        alone_win = score_hand(_scoring_hand(partner=None, team_points=61), RuleSet())
        self.assertEqual([4, -1, -1, -1, -1], alone_win.deltas)

        schneider = score_hand(_scoring_hand(team_points=91), RuleSet())
        self.assertEqual(2, schneider.multiplier)
        self.assertEqual([4, 2, -2, -2, -2], schneider.deltas)

        no_trick = score_hand(
            _scoring_hand(team_points=120, all_tricks_for_picker_team=True),
            RuleSet(),
        )
        self.assertEqual(3, no_trick.multiplier)
        self.assertEqual([6, 3, -3, -3, -3], no_trick.deltas)

        leaster_hand = _scoring_hand()
        leaster_hand.is_leaster = True
        leaster_hand.picker_seat = None
        leaster_hand.partner_seat = None
        leaster_hand.called_card = None
        leaster_hand.blind = []
        leaster = score_hand(leaster_hand, RuleSet())
        self.assertEqual(4, leaster.deltas[leaster.leaster_winner])
        self.assertEqual(0, sum(leaster.deltas))

    def test_called_ace_constraints_are_legal_action_rules(self) -> None:
        rules = RuleSet()
        state = create_game(rules, _seats(), 999)
        called = Card(Suit.HEARTS, Rank.ACE)
        other_heart = Card(Suit.HEARTS, Rank.SEVEN)
        off_suit = Card(Suit.SPADES, Rank.ACE)
        led_club = Card(Suit.CLUBS, Rank.SEVEN)
        state.hand.phase = Phase.PLAYING
        state.hand.picker_seat = 0
        state.hand.partner_seat = 1
        state.hand.called_card = called
        state.hand.turn_seat = 1
        state.hand.hands[1] = [called, other_heart, off_suit]

        state.hand.current_trick = [(0, other_heart)]
        self.assertEqual(
            [called],
            [action.card for action in legal_actions(state, 1) if action.type == "play"],
        )

        state.hand.current_trick = [(0, led_club)]
        discards = [action.card for action in legal_actions(state, 1) if action.type == "play"]
        self.assertNotIn(called, discards)
        self.assertIn(other_heart, discards)
        self.assertIn(off_suit, discards)

        state.hand.current_trick = []
        leading = [action.card for action in legal_actions(state, 1) if action.type == "play"]
        self.assertIn(called, leading)
        self.assertIn(off_suit, leading)
        self.assertNotIn(other_heart, leading)

    def test_leaster_requires_a_trick_to_win(self) -> None:
        # Seats 2 and 3 take every trick; seats 0, 1 and 4 take none and so score zero.
        # Under the old min(points) rule seat 0 would win on zero points without playing.
        deck = sorted(build_deck(RuleSet()), key=card_points)
        hand = _leaster_hand(
            taken={2: deck[2:17], 3: deck[17:]},
            trick_winners=[2, 2, 2, 3, 3, 3],
            blind=deck[:2],
        )
        result = score_hand(hand, RuleSet())
        self.assertEqual(2, result.leaster_winner)
        self.assertLess(result.points[2], result.points[3])
        self.assertEqual(0, result.points[0])
        self.assertEqual(4, result.deltas[2])
        self.assertEqual(0, sum(result.deltas))

    def test_leaster_blind_lands_before_eligibility_is_judged(self) -> None:
        # Seat 3 wins the last trick and is the lower of the two eligible seats on taken
        # points alone (45 vs 53) — until the 22-point blind is dumped on it, at 67.
        seat_three = _cards("AH", "AD", "TC", "TS", "QC") + _cards(
            "7C", "8C", "9C", "7S", "8S", "9S", "7H", "8H", "9H", "7D"
        )
        seat_two = _cards(
            "TH", "TD", "KC", "KS", "KH", "KD", "QS", "QH", "QD", "JC", "JS", "JH", "JD", "8D", "9D"
        )
        hand = _leaster_hand(
            taken={2: seat_two, 3: seat_three},
            trick_winners=[2, 2, 2, 3, 3, 3],
            blind=_cards("AC", "AS"),
        )
        self.assertEqual(45, sum(card_points(card) for card in seat_three))
        self.assertEqual(53, sum(card_points(card) for card in seat_two))
        result = score_hand(hand, RuleSet())
        self.assertEqual(67, result.points[3])
        self.assertEqual(2, result.leaster_winner)

    def test_picker_must_keep_a_called_suit_card_until_it_is_led(self) -> None:
        rules = RuleSet()
        state = create_game(rules, _seats(), 999)
        called = Card(Suit.HEARTS, Rank.ACE)
        heart_seven = Card(Suit.HEARTS, Rank.SEVEN)
        heart_eight = Card(Suit.HEARTS, Rank.EIGHT)
        off_suit = Card(Suit.SPADES, Rank.NINE)
        led_club = Card(Suit.CLUBS, Rank.SEVEN)
        state.hand.phase = Phase.PLAYING
        state.hand.picker_seat = 0
        state.hand.partner_seat = 1
        state.hand.called_card = called
        state.hand.turn_seat = 0

        # Holding two hearts, the picker may fail one off on a club lead.
        state.hand.hands[0] = [heart_seven, heart_eight, off_suit]
        state.hand.current_trick = [(4, led_club)]
        discards = [action.card for action in legal_actions(state, 0) if action.type == "play"]
        self.assertIn(heart_seven, discards)
        self.assertIn(heart_eight, discards)
        self.assertIn(off_suit, discards)

        # Down to the last heart, it is held back until the called suit is led.
        state.hand.hands[0] = [heart_seven, off_suit]
        self.assertEqual(
            [off_suit],
            [action.card for action in legal_actions(state, 0) if action.type == "play"],
        )

        # Leading the called suit themselves is always allowed.
        state.hand.current_trick = []
        leading = [action.card for action in legal_actions(state, 0) if action.type == "play"]
        self.assertIn(heart_seven, leading)
        self.assertIn(off_suit, leading)

        # A forced hand still yields a legal play rather than an empty action list.
        state.hand.hands[0] = [heart_seven]
        state.hand.current_trick = [(4, led_club)]
        self.assertEqual(
            [heart_seven],
            [action.card for action in legal_actions(state, 0) if action.type == "play"],
        )

        # Once the suit has been led the restriction lifts.
        state.hand.hands[0] = [heart_seven, off_suit]
        state.hand.called_suit_led = True
        released = [action.card for action in legal_actions(state, 0) if action.type == "play"]
        self.assertIn(heart_seven, released)
        self.assertIn(off_suit, released)

    def test_leading_the_called_suit_sets_the_flag(self) -> None:
        rules = RuleSet()
        state = create_game(rules, _seats(), 321)
        called = Card(Suit.HEARTS, Rank.ACE)
        heart_seven = Card(Suit.HEARTS, Rank.SEVEN)
        state.hand.phase = Phase.PLAYING
        state.hand.picker_seat = 0
        state.hand.partner_seat = 1
        state.hand.called_card = called
        state.hand.turn_seat = 0
        state.hand.trick_leader = 0
        state.hand.current_trick = []
        state.hand.hands[0] = [heart_seven, Card(Suit.SPADES, Rank.NINE)]
        self.assertFalse(state.hand.called_suit_led)
        state, _ = apply_action(state, 0, PlayAction(heart_seven))
        self.assertTrue(state.hand.called_suit_led)

    def test_completed_trick_records_seat_attribution(self) -> None:
        state = self._leaster_in_play(2468)
        leader = state.hand.turn_seat
        state = self._play_one_trick(state)

        self.assertEqual(1, len(state.hand.completed_tricks))
        trick = state.hand.completed_tricks[0]
        self.assertEqual(5, len(trick))
        self.assertEqual([], state.hand.current_trick)
        # Play order is the leader followed by the seats in rotation.
        self.assertEqual(
            [(leader + offset) % 5 for offset in range(5)],
            [seat for seat, _ in trick],
        )
        self.assertEqual(trick_winner(trick, state.ruleset), state.hand.trick_winners[0])

        # The recorded trick is a snapshot: playing on into the next trick must not disturb it.
        recorded = list(trick)
        turn = state.hand.turn_seat
        play = next(action for action in legal_actions(state, turn) if action.type == "play")
        state, _ = apply_action(state, turn, play)
        self.assertEqual(1, len(state.hand.current_trick))
        self.assertEqual(recorded, state.hand.completed_tricks[0])

    def test_completed_tricks_survive_a_round_trip(self) -> None:
        state = self._leaster_in_play(1357)
        state = self._play_one_trick(state)
        state = self._play_one_trick(state)
        encoded = full_state_to_dict(state)
        self.assertEqual(2, len(encoded["hand"]["completed_tricks"]))
        decoded = full_state_from_dict(json.loads(json.dumps(encoded)))
        self.assertEqual(encoded, full_state_to_dict(decoded))
        self.assertEqual(state.hand.completed_tricks, decoded.hand.completed_tricks)

    def test_snapshots_without_completed_tricks_decode_empty(self) -> None:
        state = self._leaster_in_play(9753)
        state = self._play_one_trick(state)
        encoded = full_state_to_dict(state)
        del encoded["hand"]["completed_tricks"]
        decoded = full_state_from_dict(encoded)
        self.assertEqual([], decoded.hand.completed_tricks)
        # The rest of the hand still decodes, including the winner list it cannot rebuild.
        self.assertEqual(state.hand.trick_winners, decoded.hand.trick_winners)

    def test_the_running_trick_leader_is_reported_and_moves(self) -> None:
        state = self._leaster_in_play(2468)
        self.assertIsNone(seat_view(state, 0)["trick_winning_seat"], "no trick open yet")

        leaders = []
        for _ in range(5):
            turn = state.hand.turn_seat
            play = next(a for a in legal_actions(state, turn) if a.type == "play")
            state, events = apply_action(state, turn, play)
            played = next(event for event in events if event.type == "card_played")
            leaders.append(played.winning_seat)

        # Every card reports who is taking the trick at that moment, and the first card always
        # leads its own trick.
        self.assertEqual(leaders[0], state.hand.completed_tricks[0][0][0])
        self.assertTrue(all(seat is not None for seat in leaders))
        # The last report must agree with who actually took it.
        self.assertEqual(state.hand.trick_winners[0], leaders[-1])
        # Swept, so nobody is taking anything until the next card falls.
        self.assertIsNone(seat_view(state, 0)["trick_winning_seat"])

    def test_seat_view_exposes_public_trick_history_and_points(self) -> None:
        state = self._leaster_in_play(8642)
        state = self._play_one_trick(state)
        view = seat_view(state, 0)

        self.assertEqual(1, len(view["completed_tricks"]))
        played = view["completed_tricks"][0]
        self.assertEqual(state.hand.trick_winners[0], played["winner"])
        self.assertEqual(
            [{"seat": seat, "card": str(card)} for seat, card in state.hand.completed_tricks[0]],
            played["plays"],
        )
        # Every seat's taken points are public, not just the requesting seat's.
        self.assertTrue(all(seat["taken_points"] is not None for seat in view["seats"]))
        self.assertEqual(
            sum(card_points(card) for card in state.hand.taken[3]),
            view["seats"][3]["taken_points"],
        )

    def _assert_no_leak(self, state, seat: int) -> None:
        view = seat_view(state, seat)
        payload = json.dumps(view)
        own_cards = {str(card) for card in state.hand.hands[seat]}
        hidden_cards = {
            str(card)
            for index, hand in enumerate(state.hand.hands)
            if index != seat
            for card in hand
        } | {str(card) for card in state.hand.blind} | {
            str(card) for card in state.hand.buried
        }
        # Card strings are two characters and can theoretically occur in prose fragments;
        # inspect JSON values rather than doing substring matching.
        def values(value):
            if isinstance(value, dict):
                for nested in value.values():
                    yield from values(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from values(nested)
            elif isinstance(value, str):
                yield value

        exposed = {value for value in values(json.loads(payload)) if len(value) == 2}
        self.assertTrue(own_cards <= exposed)
        self.assertFalse(hidden_cards & exposed)
        # The bury is the picker's own information and nobody else's.
        if seat != state.hand.picker_seat:
            self.assertEqual([], view["buried"])

    def test_seat_view_does_not_leak_hidden_cards(self) -> None:
        self._assert_no_leak(create_game(RuleSet(), _seats(), 789), 0)

    def test_enriched_seat_view_does_not_leak_hidden_cards(self) -> None:
        # The trick history and per-seat points added for the AI are public information;
        # exposing them must not widen the redaction boundary mid-hand.
        state = self._leaster_in_play(789)
        for _ in range(3):
            state = self._play_one_trick(state)
        self.assertEqual(3, len(state.hand.completed_tricks))
        for seat in range(5):
            self._assert_no_leak(state, seat)


if __name__ == "__main__":
    unittest.main()
