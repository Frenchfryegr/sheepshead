"""Hand strength, as pure functions of a set of cards.

Three different questions get asked of the same six cards — can this take 61, can this duck a
leaster, what shape is it — and they want different answers, so they are three functions over one
shared `shape()`.

Deliberately excluded, and not by accident:

* **Position.** A hand is a hand. A first-seat player needs a *better hand* than a last-seat
  player, which is a statement about the bar, not the cards. The threshold table lives in the
  bidding policy.
* **Playstyle.** Personality shifts thresholds, never valuations. Keeping style out is what lets
  every function here be tested against fixed cards with fixed expected answers.
* **The blind.** `offensive_strength` scores the cards it is handed. A picker gains two cards worth
  ~7.5 points and ~0.9 trump on average, but folding a constant in here *and* setting a threshold
  would double-count it. Thresholds are calibrated against the six-card pre-blind hand, so the
  blind's value is implicit in where the bar sits. Do not "fix" this by adding a blind bonus.

Every constant below is a tuning surface. The weights were fitted to the calibration anchors in
`AI_IMPLEMENTATION.md` §4.3.1, which are encoded as tests — change a weight and the anchors are
what tell you whether you improved anything.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from .cards import Card, Rank, card_points, effective_suit, fail_power, is_trump, trump_power
from .rules import RuleSet

FAIL_SUITS = ("C", "S", "H")

# --- offensive weights -------------------------------------------------------------------

# Indexed by trump_power: 0 = 7D through 13 = QC. The curve is steep at the top on purpose —
# three high queens must outweigh six low diamonds (anchor: "six lowest trump, do not pick").
TRUMP_WEIGHTS = (
    0.8,  # 7D
    0.9,  # 8D
    1.0,  # 9D
    1.2,  # KD
    1.4,  # TD
    1.6,  # AD
    2.4,  # JD
    2.6,  # JH
    2.8,  # JS
    3.0,  # JC
    4.0,  # QD
    4.4,  # QH
    4.8,  # QS
    5.2,  # QC
)

# Length is control, but only when the trump are worth controlling with. Scaled by average trump
# quality so that a fistful of low diamonds cannot out-accumulate genuine strength.
LENGTH_BONUS_PER_TRUMP = 1.4
LENGTH_BONUS_FROM = 3
TYPICAL_TRUMP_WEIGHT = 3.0

# A void is only worth what you have to trump it with, so it scales with trump quality too.
VOID_BONUS = 2.2
SINGLETON_BONUS = 0.8
# The picker wants their one remaining fail suit to be the suit they call, so a second void is
# still an asset — but a third means no fail at all, which is the awkward "under" case, not a
# bonus. Count at most two.
MAX_COUNTED_VOIDS = 2
ALL_THREE_FAILS_PENALTY = 1.5

BARE_ACE_BONUS = 2.4
GUARDED_ACE_BONUS = 1.8
GUARDED_TEN_BONUS = 0.5
BARE_TEN_BONUS = 0.0

# --- leaster weights ---------------------------------------------------------------------

# You follow with your lowest card in a suit, so that card decides whether you duck or get stuck.
LEASTER_SAFE_LOW_BONUS = 1.5
LEASTER_FORCED_WINNER_PENALTY = 2.5
LEASTER_POINT_WEIGHT = 0.05
# You must take a trick to be eligible to win a leaster at all, so some way to win one is
# required — a high trump guarantees it, a couple of moderate trump give you the option.
LEASTER_RELIABLE_WINNER_BONUS = 2.5
LEASTER_MODERATE_TRUMP_BONUS = 1.0
LEASTER_MAX_MODERATE_TRUMP = 3
LEASTER_NO_CAPABILITY_PENALTY = 3.0
# ...but every high trump beyond the first wins tricks you did not want.
LEASTER_EXCESS_HIGH_TRUMP_PENALTY = 1.6

# Trump bands, by trump_power.
_HIGH_TRUMP_FROM = 6  # jacks and queens
_MODERATE_TRUMP_FROM = 3  # KD, TD, AD

# Ranks that cannot duck: playing one both wins the trick and loads it with points.
_FORCED_WINNER_RANKS = frozenset({Rank.ACE, Rank.TEN})


@dataclass(frozen=True)
class HandShape:
    """Structural facts about a set of cards. Counts and groupings, no judgement."""

    trump: tuple[Card, ...]  # high to low
    fail_by_suit: Mapping[str, tuple[Card, ...]]  # fail suits only, high to low
    trump_count: int
    points: int
    void_suits: frozenset[str]
    singleton_suits: frozenset[str]


def shape(cards, ruleset: RuleSet) -> HandShape:
    trump = sorted(
        (card for card in cards if is_trump(card, ruleset)),
        key=lambda card: trump_power(card, ruleset),
        reverse=True,
    )
    fail: dict[str, list[Card]] = {suit: [] for suit in FAIL_SUITS}
    for card in cards:
        suit = effective_suit(card, ruleset)
        if suit in fail:
            fail[suit].append(card)
    for suit in fail:
        # fail_power is safe here: fail_by_suit holds no queens or jacks by construction.
        fail[suit].sort(key=fail_power, reverse=True)

    return HandShape(
        trump=tuple(trump),
        fail_by_suit={suit: tuple(cards) for suit, cards in fail.items()},
        trump_count=len(trump),
        points=sum(card_points(card) for card in cards),
        void_suits=frozenset(suit for suit, held in fail.items() if not held),
        singleton_suits=frozenset(suit for suit, held in fail.items() if len(held) == 1),
    )


def _average_trump_weight(hand: HandShape, ruleset: RuleSet) -> float:
    if not hand.trump:
        return 0.0
    total = sum(TRUMP_WEIGHTS[trump_power(card, ruleset)] for card in hand.trump)
    return total / len(hand.trump)


def offensive_strength(cards, ruleset: RuleSet) -> float:
    """How well this hand can take 61 as the picker. Higher is better, units are arbitrary."""
    hand = shape(cards, ruleset)
    quality = sum(TRUMP_WEIGHTS[trump_power(card, ruleset)] for card in hand.trump)
    average = _average_trump_weight(hand, ruleset)
    scale = min(1.0, average / TYPICAL_TRUMP_WEIGHT)

    length = max(0, hand.trump_count - LENGTH_BONUS_FROM) * LENGTH_BONUS_PER_TRUMP * scale

    structure = 0.0
    for suit in FAIL_SUITS:
        held = hand.fail_by_suit[suit]
        if not held:
            continue
        ranks = {card.rank for card in held}
        if Rank.ACE in ranks:
            structure += BARE_ACE_BONUS if len(held) == 1 else GUARDED_ACE_BONUS
        if Rank.TEN in ranks:
            structure += BARE_TEN_BONUS if len(held) == 1 else GUARDED_TEN_BONUS

    counted_voids = min(len(hand.void_suits), MAX_COUNTED_VOIDS)
    structure += counted_voids * VOID_BONUS * scale
    structure += len(hand.singleton_suits) * SINGLETON_BONUS * scale
    if not hand.void_suits:
        # Holding all three fail suits: no void to exploit and an awkward call.
        structure -= ALL_THREE_FAILS_PENALTY

    return quality + length + structure


def _leaster_trick_capability(hand: HandShape, ruleset: RuleSet) -> float:
    """A leaster hand has to be able to win a trick — taking none loses by ineligibility."""
    powers = [trump_power(card, ruleset) for card in hand.trump]
    high = [power for power in powers if power >= _HIGH_TRUMP_FROM]
    moderate = [power for power in powers if _MODERATE_TRUMP_FROM <= power < _HIGH_TRUMP_FROM]

    if high:
        # One high trump takes a trick whenever you choose; the rest only win unwanted ones.
        capability = LEASTER_RELIABLE_WINNER_BONUS
        capability -= (len(high) - 1) * LEASTER_EXCESS_HIGH_TRUMP_PENALTY
    elif moderate:
        # Moderate trump can trump in when needed and still duck under a queen.
        capability = LEASTER_MODERATE_TRUMP_BONUS * min(len(moderate), LEASTER_MAX_MODERATE_TRUMP)
    elif hand.trump:
        capability = LEASTER_MODERATE_TRUMP_BONUS
    else:
        capability = -LEASTER_NO_CAPABILITY_PENALTY
    return capability


def leaster_strength(cards, ruleset: RuleSet) -> float:
    """How well this hand ducks a leaster. Higher is better — same direction as offence.

    Not `-offensive_strength`. The dominant signal is the *lowest* card held in each suit,
    because that is what you follow with: a lowest card of K/9/8/7 ducks safely, while a lowest
    card of ace or ten both wins the trick and loads it with points.
    """
    hand = shape(cards, ruleset)

    ducking = 0.0
    for suit in FAIL_SUITS:
        held = hand.fail_by_suit[suit]
        if not held:
            # Void: discard from another suit instead. Neither an asset nor a liability.
            continue
        lowest = held[-1]
        if lowest.rank in _FORCED_WINNER_RANKS:
            ducking -= LEASTER_FORCED_WINNER_PENALTY
        else:
            ducking += LEASTER_SAFE_LOW_BONUS

    if hand.trump:
        lowest_trump = trump_power(hand.trump[-1], ruleset)
        if lowest_trump >= _HIGH_TRUMP_FROM:
            ducking -= LEASTER_FORCED_WINNER_PENALTY
        else:
            ducking += LEASTER_SAFE_LOW_BONUS

    return (
        ducking
        + _leaster_trick_capability(hand, ruleset)
        - hand.points * LEASTER_POINT_WEIGHT
    )


def callable_suits(cards, ruleset: RuleSet) -> frozenset[str]:
    """Fail suits whose ace this hand could call under the ordinary rule.

    Mirrors `engine._call_actions()`: a suit qualifies when the hand holds a non-ace fail card of
    it and does not hold the ace. Approximate before picking — the engine also requires the ace to
    be in somebody's hand rather than buried, and picking adds two unknown cards before two are
    buried, either of which can change the answer.

    An empty result does **not** mean the picker must play alone; real rules provide unders and
    calling a ten. See `AI_IMPLEMENTATION.md` Phase 5.
    """
    hand = shape(cards, ruleset)
    suits = set()
    for suit in FAIL_SUITS:
        held = hand.fail_by_suit[suit]
        ranks = {card.rank for card in held}
        if Rank.ACE not in ranks and any(rank != Rank.ACE for rank in ranks):
            suits.add(suit)
    return frozenset(suits)
