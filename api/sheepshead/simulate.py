"""Engine soak and AI calibration harness.

    uv run python -m sheepshead.simulate 3000
    uv run python -m sheepshead.simulate 2000 --strategy heuristic
    uv run python -m sheepshead.simulate 2000 --strategy heuristic --seed 12345

With `--strategy heuristic` this is the instrument for tuning the pick bars: it reports the
leaster rate (target 10-15%) and the pick rate by seat position.

A run is fully deterministic, so repeating it changes nothing — that is the point, since it
isolates the effect of a code change from sampling noise. Use `--seed` to draw a different
sample and confirm a tuned constant is not overfitted to the default one.
"""

import json
import random
import sys

from .ai import AI_STRATEGIES
from .ai_knowledge import read_view
from .cards import Rank, Suit, build_deck, card_points, effective_suit, trump_power
from .engine import apply_action, create_game, is_rerack_hand, legal_actions
from .rules import RuleSet
from .serialization import full_state_from_dict, full_state_to_dict, seat_view
from .state import GameState, Phase, Seat


def _assert_no_rerack_hand(state: GameState) -> None:
    """No freshly dealt hand may be trumpless and aceless — the deal should have been redone."""
    for seat, hand in enumerate(state.hand.hands):
        assert not is_rerack_hand(hand, state.ruleset), (
            f"seat {seat} was dealt a rerack hand: {[str(card) for card in hand]}"
        )


def _assert_knowledge_is_true(view: dict, state: GameState, seat: int) -> None:
    """Oracle check: everything ai_knowledge derives must match the real hidden state.

    Knowledge claims to be exact rather than probabilistic, so any divergence from ground
    truth is a bug. Running this on every AI turn turns the soak into a proof of the whole
    derivation across every phase, seat and role.
    """
    knowledge = read_view(view)
    hand = state.hand
    rules = state.ruleset

    for other in range(rules.num_players):
        actual = hand.hands[other]
        for suit in knowledge.voids[other]:
            held = [card for card in actual if effective_suit(card, rules) == suit]
            assert not held, f"seat {other} inferred void in {suit} but holds {held}"
        assert knowledge.taken_points[other] == sum(card_points(card) for card in hand.taken[other])
        assert knowledge.card_counts[other] == len(actual)
        if other != seat:
            unknown = set(actual) - knowledge.unseen
            assert not unknown, f"seat {seat} should not be able to place {unknown}"

    for card in knowledge.played:
        assert all(card not in cards for cards in hand.hands), f"{card} played but still held"
        assert card not in hand.blind, f"{card} played but still in the blind"

    total = len(knowledge.played) + len(knowledge.hand) + len(knowledge.unseen) + len(knowledge.buried)
    assert total == len(build_deck(rules)), f"card accounting lost cards: {total}"


DEFAULT_SEED = 8675309


def run(hand_count: int = 1000, strategy_name: str = "random", seed: int = DEFAULT_SEED) -> dict:
    """Play legal hands, asserting invariants throughout. Returns a summary.

    Fully deterministic: the seed fixes both the deals and the strategy's choices, so repeating
    a run reproduces it exactly. That is what makes calibration meaningful — any change in the
    reported rates is caused by a code change, with no sampling noise mixed in.

    The cost is that one seed is one fixed sample. Tuning repeatedly against the default seed
    overfits to it, so re-check a tuned constant against two or three other seeds before
    believing the number.
    """
    rules = RuleSet()
    deck = build_deck(rules)
    assert len(deck) == 32
    assert sum(card_points(card) for card in deck) == 120
    expected_trump = ["QC", "QS", "QH", "QD", "JC", "JS", "JH", "JD", "AD", "TD", "KD", "9D", "8D", "7D"]
    actual_trump = sorted(
        [card for card in deck if card.rank in {Rank.QUEEN, Rank.JACK} or card.suit == Suit.DIAMONDS],
        key=lambda card: trump_power(card, rules),
        reverse=True,
    )
    assert [str(card) for card in actual_trump] == expected_trump

    factory = AI_STRATEGIES.get(strategy_name)
    if factory is None:
        raise SystemExit(f"Unknown strategy {strategy_name!r}; try {sorted(AI_STRATEGIES)}")
    seats = [
        Seat(index, f"AI {index + 1}", False, strategy_name) for index in range(rules.num_players)
    ]
    state = create_game(rules, seats, rng_seed=seed)
    _assert_no_rerack_hand(state)
    rng = random.Random(seed)
    strategy = factory()
    completed = 0
    leasters = 0
    actions = 0
    alone = 0
    unders = 0
    # Picks and offers indexed by picking position, so pick rate per seat can be reported.
    picks_by_position = [0] * rules.num_players
    offers_by_position = [0] * rules.num_players

    while completed < hand_count:
        turn = state.hand.turn_seat
        assert turn is not None
        legal = legal_actions(state, turn)
        assert legal, f"No legal action in {state.hand.phase} for seat {turn}"
        before_history = len(state.hand_history)
        view = seat_view(state, turn)
        _assert_knowledge_is_true(view, state, turn)
        action = strategy.choose(view, legal, rng)

        if state.hand.phase is Phase.PICKING:
            position = len(state.hand.passes)
            offers_by_position[position] += 1
            picks_by_position[position] += action.type == "pick"
        elif action.type == "call":
            alone += action.card is None
        elif action.type == "call_under":
            unders += 1

        state, _ = apply_action(state, turn, action)
        actions += 1
        if len(state.hand_history) > before_history:
            result = state.hand_history[-1]
            assert sum(result.deltas) == 0
            assert sum(result.points) + result.buried_points == 120
            leasters += result.kind == "leaster"
            completed += 1
            # A new hand was dealt as part of scoring this one, so check the redeal held.
            _assert_no_rerack_hand(state)
            # Keep the soak linear-time. apply_action deliberately deep-copies the complete
            # (small, real-world) session state, so a synthetic 1,000-hand history would turn
            # this verification into an O(n²) deepcopy benchmark rather than a rules soak.
            if completed < hand_count and completed % 10 == 0:
                state = create_game(rules, seats, rng_seed=seed + completed)
                _assert_no_rerack_hand(state)

        if actions % 100 == 0:
            encoded = full_state_to_dict(state)
            decoded = full_state_from_dict(json.loads(json.dumps(encoded)))
            assert full_state_to_dict(decoded) == encoded

    return {
        "hands": completed,
        "actions": actions,
        "leasters": leasters,
        "alone": alone,
        "unders": unders,
        "picks_by_position": picks_by_position,
        "offers_by_position": offers_by_position,
    }


def main(
    hand_count: int = 1000, strategy_name: str = "random", seed: int = DEFAULT_SEED
) -> None:
    summary = run(hand_count, strategy_name, seed)
    assert summary["leasters"], "Sample contained no leaster; the all-pass path went unexercised"
    hands = summary["hands"]
    print(
        f"Simulated {hands} hands in {summary['actions']} legal actions "
        f"using {strategy_name!r} (seed {seed})"
    )
    picked = hands - summary["leasters"]
    leaster_pct = 100 * summary["leasters"] / hands
    print(f"  leasters : {summary['leasters']:5d}  ({leaster_pct:.1f}% of hands)  target 10-15%")
    # As a share of picked hands, not of all hands — going alone is a choice only a picker makes.
    for label, count in (("alone", summary["alone"]), ("unders", summary["unders"])):
        share = f"{100 * count / picked:.1f}% of picked" if picked else "-"
        print(f"  {label:9s}: {count:5d}  ({share})")
    rates = [
        f"{100 * picked / offered:.0f}%" if offered else "  -"
        for picked, offered in zip(summary["picks_by_position"], summary["offers_by_position"])
    ]
    print(f"  pick rate by seat position (first to last): {' '.join(rates)}")


def _flag(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


if __name__ == "__main__":
    strategy = _flag("--strategy", "random")
    seed = _flag("--seed", str(DEFAULT_SEED))
    consumed = {strategy, seed}
    positional = [
        value for value in sys.argv[1:] if not value.startswith("--") and value not in consumed
    ]
    main(int(positional[0]) if positional else 1000, strategy, int(seed))
