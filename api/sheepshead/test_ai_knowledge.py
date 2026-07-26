import unittest

from .ai_knowledge import read_view
from .cards import Card, build_deck
from .rules import RuleSet
from .scoring import trick_winner
from .serialization import seat_view
from .state import GameState, HandState, Phase, Seat


def _seats() -> list[Seat]:
    return [Seat(index, f"Seat {index}", index == 0, None if index == 0 else "random") for index in range(5)]


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _trick(*plays: tuple[int, str]) -> list[tuple[int, Card]]:
    return [(seat, Card.parse(card)) for seat, card in plays]


def _state(
    hands: list[list[Card]],
    *,
    phase: Phase = Phase.PLAYING,
    picker: int | None = None,
    called: str | None = None,
    partner: int | None = None,
    revealed: bool = False,
    leaster: bool = False,
    completed: tuple = (),
    current: list | None = None,
    turn: int = 0,
    buried: list[Card] | None = None,
    blind: list[Card] | None = None,
) -> GameState:
    """A fully specified hand — no dealing, so every card's location is known to the test."""
    rules = RuleSet()
    taken: list[list[Card]] = [[] for _ in range(5)]
    for trick in completed:
        taken[trick_winner(trick, rules)].extend(card for _, card in trick)
    return GameState(
        ruleset=rules,
        seats=_seats(),
        scores=[0] * 5,
        hand=HandState(
            hand_number=1,
            dealer_seat=4,
            hands=[list(cards) for cards in hands],
            blind=list(blind or []),
            buried=list(buried or []),
            phase=phase,
            turn_seat=turn,
            passes=[],
            picker_seat=picker,
            called_card=Card.parse(called) if called else None,
            partner_seat=partner,
            partner_revealed=revealed,
            is_leaster=leaster,
            current_trick=list(current or []),
            trick_leader=0,
            taken=taken,
            last_trick_winner=None,
            trick_winners=[trick_winner(trick, rules) for trick in completed],
            completed_tricks=[list(trick) for trick in completed],
        ),
        hand_history=[],
        rng_seed=1,
    )


def _deal(*hands: list[Card]) -> list[list[Card]]:
    return list(hands)


class KnowledgeTests(unittest.TestCase):
    def test_void_is_inferred_only_from_failing_to_follow(self) -> None:
        # Clubs led. Seat 2 discards a spade and seat 4 trumps — both prove a club void.
        # Seats 1 and 3 follow, and seat 0 led, so neither proves anything.
        trick = _trick((0, "AC"), (1, "KC"), (2, "7S"), (3, "9C"), (4, "QC"))
        state = _state(
            _deal(_cards("TC"), _cards("8C"), _cards("8S"), _cards("7C"), _cards("QS")),
            completed=(trick,),
        )
        knowledge = read_view(seat_view(state, 0))

        self.assertEqual(frozenset({"C"}), knowledge.voids[2])
        self.assertEqual(frozenset({"C"}), knowledge.voids[4])
        self.assertEqual(frozenset(), knowledge.voids[0])
        self.assertEqual(frozenset(), knowledge.voids[1])
        self.assertEqual(frozenset(), knowledge.voids[3])
        self.assertTrue(knowledge.is_void(2, "C"))
        self.assertFalse(knowledge.is_void(1, "C"))

    def test_open_trick_is_evidence_too(self) -> None:
        # Seats 0 and 1 have played; seat 2 is on turn and asking.
        state = _state(
            _deal(_cards("TC"), _cards("8C"), _cards("8S"), _cards("7C"), _cards("QS")),
            current=_trick((0, "AC"), (1, "7H")),
            turn=2,
        )
        knowledge = read_view(seat_view(state, 2))
        # Seat 1 threw a heart on a club lead, so it is void in clubs from this moment.
        self.assertEqual(frozenset({"C"}), knowledge.voids[1])
        self.assertEqual(frozenset(), knowledge.voids[0])
        self.assertEqual("C", knowledge.led_suit)
        self.assertEqual(0, knowledge.trick_winning_seat)
        self.assertEqual(11, knowledge.trick_points)
        # After seat 2 plays, only seats 3 and 4 are left.
        self.assertEqual(2, knowledge.plays_remaining_in_trick)

    def test_unseen_accounts_for_every_card(self) -> None:
        trick = _trick((0, "AC"), (1, "KC"), (2, "7S"), (3, "9C"), (4, "QC"))
        state = _state(
            _deal(_cards("TC"), _cards("8C"), _cards("8S"), _cards("7C"), _cards("QS")),
            picker=0,
            called="AH",
            partner=1,
            completed=(trick,),
            buried=_cards("TS", "KS"),
        )
        for seat in range(5):
            knowledge = read_view(seat_view(state, seat))
            total = (
                len(knowledge.played)
                + len(knowledge.hand)
                + len(knowledge.unseen)
                + len(knowledge.buried)
            )
            self.assertEqual(len(build_deck(state.ruleset)), total, f"seat {seat}")
            self.assertFalse(knowledge.played & frozenset(knowledge.hand))

    def test_picker_alone_sees_its_own_bury_and_nobody_else_does(self) -> None:
        state = _state(
            _deal(_cards("TC"), _cards("8C"), _cards("8S"), _cards("7C"), _cards("QS")),
            picker=2,
            called="AH",
            partner=1,
            buried=_cards("TS", "KS"),
        )
        picker_knowledge = read_view(seat_view(state, 2))
        self.assertEqual(tuple(_cards("TS", "KS")), picker_knowledge.buried)
        self.assertNotIn(Card.parse("TS"), picker_knowledge.unseen)

        for seat in (0, 1, 3, 4):
            other = read_view(seat_view(state, seat))
            self.assertEqual((), other.buried)
            # A non-picker cannot distinguish a buried card from one still in a hand.
            self.assertIn(Card.parse("TS"), other.unseen)

    def test_could_hold_respects_voids_played_cards_and_own_hand(self) -> None:
        trick = _trick((0, "AC"), (1, "KC"), (2, "7S"), (3, "9C"), (4, "8C"))
        state = _state(
            _deal(_cards("TC"), _cards("8S"), _cards("9S"), _cards("7C"), _cards("QS")),
            completed=(trick,),
        )
        knowledge = read_view(seat_view(state, 0))

        self.assertTrue(knowledge.could_hold(0, Card.parse("TC")))
        self.assertFalse(knowledge.could_hold(0, Card.parse("TD")))
        # 7C is genuinely unseen — it is in seat 3's hand — so this rejection is the void
        # rule doing the work, not the card merely being accounted for elsewhere.
        seven_clubs = Card.parse("7C")
        self.assertIn(seven_clubs, knowledge.unseen)
        self.assertTrue(knowledge.could_hold(3, seven_clubs))
        self.assertFalse(knowledge.could_hold(2, seven_clubs))
        # Already played, so nobody holds it.
        self.assertFalse(knowledge.could_hold(3, Card.parse("AC")))
        # Unseen and no void known: genuinely possible.
        self.assertTrue(knowledge.could_hold(3, Card.parse("QH")))


class TeammateTests(unittest.TestCase):
    """The §3.5 truth table. `None` means unknown and must never be a falsy accident."""

    def _knowledge(self, seat: int, **kwargs):
        hands = _deal(
            _cards("TC"), _cards("AH", "8C"), _cards("8S"), _cards("7C"), _cards("QS")
        )
        return read_view(seat_view(_state(hands, **kwargs), seat))

    def test_self_is_always_a_teammate(self) -> None:
        for seat in range(5):
            self.assertIs(True, self._knowledge(seat, picker=0, called="AH", partner=1).is_teammate(seat))

    def test_leaster_has_no_teams(self) -> None:
        knowledge = self._knowledge(0, leaster=True)
        self.assertIs(True, knowledge.is_teammate(0))
        for other in range(1, 5):
            self.assertIs(False, knowledge.is_teammate(other))

    def test_unknown_while_still_bidding(self) -> None:
        knowledge = self._knowledge(0, phase=Phase.PICKING)
        self.assertIsNone(knowledge.is_teammate(1))

    def test_unknown_after_picking_but_before_calling(self) -> None:
        # A picker exists, but nobody knows the teams until the ace is named.
        knowledge = self._knowledge(0, phase=Phase.BURYING, picker=0)
        self.assertIsNone(knowledge.is_teammate(1))

    def test_going_alone_resolves_for_everyone(self) -> None:
        picker = self._knowledge(0, picker=0, called=None)
        self.assertIs(False, picker.is_teammate(1))

        opponent = self._knowledge(1, picker=0, called=None)
        self.assertIs(False, opponent.is_teammate(0))
        self.assertIs(True, opponent.is_teammate(2))

    def test_partner_knows_the_teams_before_the_reveal(self) -> None:
        # Seat 1 holds the called ace, so seat 1 alone knows the full picture.
        knowledge = self._knowledge(1, picker=0, called="AH", partner=1)
        self.assertFalse(knowledge.partner_revealed)
        self.assertIs(True, knowledge.is_teammate(0))
        self.assertIs(False, knowledge.is_teammate(2))
        self.assertIs(False, knowledge.is_teammate(4))

    def test_picker_does_not_know_who_holds_the_called_ace(self) -> None:
        knowledge = self._knowledge(0, picker=0, called="AH", partner=1)
        self.assertIsNone(knowledge.partner_seat)
        for other in (1, 2, 3, 4):
            self.assertIsNone(knowledge.is_teammate(other), f"seat {other}")

    def test_opponent_knows_only_that_the_picker_is_hostile(self) -> None:
        knowledge = self._knowledge(2, picker=0, called="AH", partner=1)
        self.assertIs(False, knowledge.is_teammate(0))
        for other in (1, 3, 4):
            self.assertIsNone(knowledge.is_teammate(other), f"seat {other}")

    def test_reveal_resolves_it_for_every_seat(self) -> None:
        for seat in range(5):
            knowledge = self._knowledge(seat, picker=0, called="AH", partner=1, revealed=True)
            for other in range(5):
                self.assertIsNotNone(knowledge.is_teammate(other), f"{seat} -> {other}")
        opponent = self._knowledge(2, picker=0, called="AH", partner=1, revealed=True)
        self.assertIs(False, opponent.is_teammate(0))
        self.assertIs(False, opponent.is_teammate(1))
        self.assertIs(True, opponent.is_teammate(3))


if __name__ == "__main__":
    unittest.main()
