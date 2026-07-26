"""Leaster play, and the tie rule it depends on.

Two inversions from normal play drive everything here: giving points away is *good*, so a
discard is the fattest card rather than the leanest; and there are no teams, so nobody is ever
schmeared to. On top of that sits eligibility — a seat that takes no trick cannot win at all.
"""

import random
import unittest

from .ai_heuristic import LEASTER_BLIND_WEIGHT, HeuristicStrategy
from .cards import Card, build_deck, card_points
from .engine import apply_action, create_game, legal_actions
from .rules import RuleSet
from .scoring import score_hand
from .serialization import seat_view
from .state import GameState, HandState, Phase, Seat

RULES = RuleSet()


def _seats() -> list[Seat]:
    return [Seat(index, f"Seat {index}", False, "heuristic") for index in range(5)]


def _cards(*values: str) -> list[Card]:
    return [Card.parse(value) for value in values]


def _trick(*plays: tuple[int, str]) -> list[tuple[int, Card]]:
    return [(seat, Card.parse(card)) for seat, card in plays]


def _leaster_state(
    hands: list[list[Card]],
    *,
    turn: int,
    current=None,
    taken: dict[int, list[Card]] | None = None,
    trick_winners: list[int] | None = None,
    blind: list[Card] | None = None,
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
            blind=list(blind or []),
            buried=[],
            phase=Phase.PLAYING,
            turn_seat=turn,
            passes=[0, 1, 2, 3, 4],
            picker_seat=None,
            called_card=None,
            partner_seat=None,
            partner_revealed=False,
            is_leaster=True,
            current_trick=list(current or []),
            trick_leader=0,
            taken=piles,
            last_trick_winner=(trick_winners or [None])[-1],
            trick_winners=list(trick_winners or []),
        ),
        hand_history=[],
        rng_seed=1,
    )


def _decide(state: GameState, seat: int) -> Card:
    action = HeuristicStrategy().choose(
        seat_view(state, seat), legal_actions(state, seat), random.Random(4)
    )
    return action.card


def _by_points(value: int) -> list[Card]:
    return [card for card in build_deck(RULES) if card_points(card) == value]


class LeasterTieTests(unittest.TestCase):
    """A tied leaster is a wash: nobody scores, and there is no winner to name."""

    # An exact 60/60 split, built from rank groups rather than by slicing a sorted deck —
    # slicing looks tidy but does not divide the points evenly.
    LEVEL_A = _by_points(11) + _by_points(4)  # four aces + four kings = 60
    LEVEL_B = _by_points(10) + _by_points(3) + _by_points(2)  # tens + queens + jacks = 60
    # Zero-point cards, so the blind cannot disturb the balance it lands on.
    BLIND = _by_points(0)[:2]

    def _scored(self, taken: dict[int, list[Card]], trick_winners: list[int]):
        state = _leaster_state(
            [[] for _ in range(5)],
            turn=0,
            taken=taken,
            trick_winners=trick_winners,
            blind=self.BLIND,
        )
        state.hand.phase = Phase.HAND_DONE
        return score_hand(state.hand, RULES)

    def test_the_fixture_really_is_a_tie(self) -> None:
        self.assertEqual(60, sum(card_points(card) for card in self.LEVEL_A))
        self.assertEqual(60, sum(card_points(card) for card in self.LEVEL_B))
        self.assertEqual(0, sum(card_points(card) for card in self.BLIND))

    def test_a_tie_scores_nothing_for_anyone(self) -> None:
        result = self._scored({2: self.LEVEL_A, 3: self.LEVEL_B}, [2, 2, 2, 3, 3, 3])
        self.assertIsNone(result.leaster_winner)
        self.assertEqual([0, 0, 0, 0, 0], result.deltas)

    def test_a_clear_winner_still_scores_normally(self) -> None:
        low = _by_points(4) + _by_points(2)  # kings + jacks = 24
        high = _by_points(11) + _by_points(10) + _by_points(3)  # aces + tens + queens = 96
        result = self._scored({2: low, 3: high}, [2, 2, 2, 3, 3, 3])
        self.assertEqual(2, result.leaster_winner)
        self.assertEqual(4, result.deltas[2])
        self.assertEqual(0, sum(result.deltas))

    def test_there_is_no_recency_tie_break(self) -> None:
        # The old rule handed a tie to whoever won a trick latest, which both invented a winner
        # and rewarded taking the last trick — the one carrying the blind.
        taken = {2: self.LEVEL_A, 3: self.LEVEL_B}
        first = self._scored(taken, [2, 2, 2, 3, 3, 3])
        second = self._scored(taken, [3, 3, 3, 2, 2, 2])
        self.assertIsNone(first.leaster_winner)
        self.assertIsNone(second.leaster_winner)
        self.assertEqual(first.deltas, second.deltas)


class LeasterDiscardTests(unittest.TestCase):
    def test_points_are_dumped_on_whoever_is_taking_the_trick(self) -> None:
        # The inversion: in a leaster, handing points away is good. Seat 0 cannot follow and
        # cannot win, so it sheds its fattest card rather than its leanest.
        state = _leaster_state(
            [
                _cards("AS", "7S", "9S"),
                _cards("AH"),
                _cards("KH"),
                _cards("7H"),
                _cards("8H"),
            ],
            turn=0,
            current=_trick((1, "AH"), (2, "KH")),
            trick_winners=[4],
            taken={4: _cards("7C", "8C", "9C", "TC", "KC")},
        )
        self.assertEqual(Card.parse("AS"), _decide(state, 0))

    def test_a_trick_that_cannot_be_avoided_is_taken_cheaply(self) -> None:
        # Every legal card wins, so the choice is only how much to pay for it.
        state = _leaster_state(
            [
                _cards("QC", "QS"),
                _cards("7H"),
                _cards("8H"),
                _cards("9H"),
                _cards("KH"),
            ],
            turn=0,
            current=_trick((1, "7H"), (2, "8H"), (3, "9H"), (4, "KH")),
        )
        # Both queens win and both are worth 3, so spend the more dangerous one. Keeping Q-clubs
        # back would only mean winning another unwanted trick with it later.
        self.assertEqual(Card.parse("QC"), _decide(state, 0))


class LeasterEligibilityTests(unittest.TestCase):
    def test_a_cheap_trick_is_taken_to_qualify(self) -> None:
        state = _leaster_state(
            [
                _cards("QC", "7S", "9S"),
                _cards("7H"),
                _cards("8H"),
                _cards("9H"),
                _cards("7C"),
            ],
            turn=0,
            current=_trick((1, "7H"), (2, "8H"), (3, "9H"), (4, "7C")),
            trick_winners=[1, 1, 1],
            taken={1: _cards("AC", "TC", "KC", "AS", "TS")},
        )
        # Zero points on the table and no trick yet: qualify here rather than risk it later.
        self.assertEqual(Card.parse("QC"), _decide(state, 0))

    def test_an_already_eligible_seat_ducks_instead(self) -> None:
        # trick_count is len(taken) // num_players, so a seat needs a full five-card pile to
        # register as having taken a trick at all.
        state = _leaster_state(
            [
                _cards("QC", "7S", "9S"),
                _cards("7H"),
                _cards("8H"),
                _cards("9H"),
                _cards("7C"),
            ],
            turn=0,
            current=_trick((1, "7H"), (2, "8H"), (3, "9H"), (4, "7C")),
            trick_winners=[0, 1, 1],
            taken={
                0: _cards("7D", "8D", "9D", "KD", "TD"),
                1: _cards("AC", "TC", "KC", "8C", "9C", "AS", "TS", "KS", "8S", "QD"),
            },
        )
        # Eligible already, so the queen is kept out of it and the higher spade goes — among
        # equal points, shedding the more dangerous card is right in a leaster.
        self.assertEqual(Card.parse("9S"), _decide(state, 0))

    def test_the_last_trick_is_priced_with_the_blind(self) -> None:
        # The blind lands on whoever takes the final trick, so it is worth avoiding even when
        # the trick itself looks cheap.
        self.assertGreaterEqual(LEASTER_BLIND_WEIGHT, 7, "the blind averages 7-8 points")


class LeasterFullHandTests(unittest.TestCase):
    def test_leasters_play_out_legally_and_score(self) -> None:
        strategy = HeuristicStrategy()
        rng = random.Random(3)
        played = 0
        for seed in range(400):
            state = create_game(RULES, _seats(), seed)
            for _ in range(5):
                turn = state.hand.turn_seat
                passes = [a for a in legal_actions(state, turn) if a.type == "pass"]
                if not passes:
                    break
                state, _ = apply_action(state, turn, passes[0])
            if not state.hand.is_leaster:
                continue
            played += 1
            while not state.hand_history:
                turn = state.hand.turn_seat
                legal = legal_actions(state, turn)
                self.assertTrue(legal)
                action = strategy.choose(seat_view(state, turn), legal, rng)
                self.assertIn(action, legal)
                state, _ = apply_action(state, turn, action)
            result = state.hand_history[0]
            self.assertEqual("leaster", result.kind)
            self.assertEqual(120, sum(result.points))
            self.assertEqual(0, sum(result.deltas))
            if result.leaster_winner is None:
                self.assertEqual([0] * 5, result.deltas)  # a tie pays nobody
            else:
                # Not min(points) overall: an ineligible seat can hold fewer points and still
                # not win. The winner is lowest among those who took a trick.
                self.assertEqual(4, result.deltas[result.leaster_winner])
            if played >= 8:
                return
        self.assertGreater(played, 0, "no leaster was reachable in the sample")


if __name__ == "__main__":
    unittest.main()
